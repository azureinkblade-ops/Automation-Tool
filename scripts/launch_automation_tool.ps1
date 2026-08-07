param([switch]$UpdateFirst, [switch]$NoChromeHelper, [int]$Port = 8765)

$ErrorActionPreference = "Stop"

function Write-Banner {
  param([string]$Text)
  Write-Host "============================================================" -ForegroundColor Cyan
  Write-Host $Text -ForegroundColor Cyan
  Write-Host "============================================================" -ForegroundColor Cyan
}

function Normalize-Root {
  param([string]$Path)
  if ([string]::IsNullOrEmpty($Path)) { return "" }
  try {
    $resolved = (Resolve-Path $Path).Path
  } catch {
    $resolved = $Path
  }
  return $resolved.TrimEnd('\').ToLowerInvariant()
}

$Root = Resolve-Path "$PSScriptRoot\.."
$RootPath = $Root.Path
$AppPy = Join-Path $RootPath "app.py"
$HelperDir = Join-Path $RootPath "chrome-helper"
$BundledPy = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$GpuPython = Join-Path $RootPath ".venv-gpu\Scripts\python.exe"
$ChromePort = 9222
$HelperProfile = "$env:LOCALAPPDATA\AzureInkbladeAutomationChrome"

Write-Banner "Automation Tool startup"

$GitBranch = "unknown"
$GitCommit = "unknown"
try {
  $GitBranch = (git -C $RootPath rev-parse --abbrev-ref HEAD 2>$null).Trim()
  if (-not $GitBranch) { $GitBranch = "unknown" }
} catch { $GitBranch = "unknown" }
try {
  $GitCommit = (git -C $RootPath rev-parse --short HEAD 2>$null).Trim()
  if (-not $GitCommit) { $GitCommit = "unknown" }
} catch { $GitCommit = "unknown" }

$ChosenPython = $BundledPy
if (-not (Test-Path $ChosenPython)) {
  if (Test-Path $GpuPython) {
    $ChosenPython = $GpuPython
  } else {
    $ChosenPython = "py"
  }
}

$HelperEnabled = -not $NoChromeHelper
$HelperState = if ($HelperEnabled) { "ENABLED" } else { "DISABLED" }

Write-Host ("Root:          {0}" -f $RootPath)
Write-Host ("Branch:        {0}" -f $GitBranch)
Write-Host ("Commit:        {0}" -f $GitCommit)
Write-Host ("Python:        {0}" -f $ChosenPython)
Write-Host ("App port:      {0}" -f $Port)
Write-Host ("Chrome helper: {0}" -f $HelperState)
Write-Host ("Chrome CDP:    127.0.0.1:{0}" -f $ChromePort)
Write-Host ("App URL:       http://127.0.0.1:{0}" -f $Port)
Write-Host ""

if ($UpdateFirst) {
  Write-Host "Attempting git pull --ff-only (best effort)..." -ForegroundColor Yellow
  try {
    git -C $RootPath pull --ff-only 2>&1 | ForEach-Object { Write-Host ("  {0}" -f $_) }
    Write-Host "git pull finished." -ForegroundColor Green
  } catch {
    Write-Host ("  git pull failed (continuing): {0}" -f $_.Exception.Message) -ForegroundColor Red
  }
  Write-Host ""
}

function Get-ListenerPid {
  param([int]$PortNum)
  try {
    $conn = Get-NetTCPConnection -LocalPort $PortNum -State Listen -ErrorAction SilentlyContinue
    if ($conn) { return ($conn | Select-Object -First 1).OwningProcess }
  } catch { }
  return $null
}

function Get-RuntimeProvenance {
  param([int]$PortNum)
  try {
    $resp = Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/api/runtime-provenance" -f $PortNum) -TimeoutSec 3 -ErrorAction Stop
    return $resp
  } catch {
    return $null
  }
}

function Test-AppHealthy {
  param([int]$PortNum)
  try {
    $r = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/api/health" -f $PortNum) -TimeoutSec 3 -ErrorAction Stop
    return ($r.StatusCode -eq 200)
  } catch {
    try {
      $r2 = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/" -f $PortNum) -TimeoutSec 3 -ErrorAction Stop
      return ($r2.StatusCode -eq 200)
    } catch { return $false }
  }
}

function Test-PortFree {
  param([int]$PortNum)
  $pid2 = Get-ListenerPid $PortNum
  return ($null -eq $pid2)
}

$stalePid = Get-ListenerPid $Port
if ($null -ne $stalePid) {
  Write-Host ("Port {0} is occupied by PID {1}. Querying provenance..." -f $Port, $stalePid) -ForegroundColor Yellow
  $prov = Get-RuntimeProvenance $Port
  if ($null -eq $prov) {
    Write-Host ""
    Write-Host ("ERROR: Port {0} occupied by an app WITHOUT /api/runtime-provenance (likely stale)." -f $Port) -ForegroundColor Red
    Write-Host "Free the port or stop that process, then relaunch." -ForegroundColor Red
    exit 1
  }
  $existingRoot = Normalize-Root $prov.root
  $launchedRoot = Normalize-Root $RootPath
  $sameCheckout = ($existingRoot -eq $launchedRoot) -and ($prov.commit -eq $GitCommit) -and ($prov.commit -ne "unknown")
  if ($sameCheckout) {
    Write-Host ("Reusing existing app (same checkout, PID {0}, commit {1})." -f $stalePid, $prov.commit) -ForegroundColor Green
    $reuseApp = $true
  } else {
    Write-Host "Stale instance detected:" -ForegroundColor Red
    Write-Host ("  PID:    {0}" -f $stalePid)
    Write-Host ("  Root:   {0}" -f $prov.root)
    Write-Host ("  Branch: {0}" -f $prov.branch)
    Write-Host ("  Commit: {0}" -f $prov.commit)
    Write-Host ("Stopping stale instance and starting the requested checkout...") -ForegroundColor Yellow
    try { Stop-Process -Id $stalePid -Force -ErrorAction Stop } catch { }
    $waited = 0
    while (($waited -lt 10) -and (-not (Test-PortFree $Port))) {
      Start-Sleep -Seconds 1
      $waited++
    }
    if (-not (Test-PortFree $Port)) {
      Write-Host ("ERROR: Port {0} did not release after stopping PID {1}." -f $Port, $stalePid) -ForegroundColor Red
      exit 1
    }
    $reuseApp = $false
  }
} else {
  $reuseApp = $false
}

$appProcess = $null
if (-not $reuseApp) {
  Write-Host ("Starting app on port {0}..." -f $Port) -ForegroundColor Green
  $env:AUTOMATION_TOOL_PORT = "$Port"
  if ($ChosenPython -eq "py") {
    $appProcess = Start-Process -FilePath "py" -ArgumentList @("`"$AppPy`"") -PassThru -WindowStyle Hidden
  } else {
    $appProcess = Start-Process -FilePath $ChosenPython -ArgumentList @("`"$AppPy`"") -PassThru -WindowStyle Hidden
  }
  Write-Host ("  App PID: {0}" -f $appProcess.Id)
} else {
  Write-Host "App already running; skipping start." -ForegroundColor Green
}

Write-Host "Waiting for app health..." -ForegroundColor Yellow
$healthy = $false
$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
  if (Test-AppHealthy $Port) { $healthy = $true; break }
  if (($null -ne $appProcess) -and $appProcess.HasExited) {
    Write-Host "ERROR: App process exited before becoming healthy." -ForegroundColor Red
    exit 1
  }
  Start-Sleep -Seconds 1
}
if (-not $healthy) {
  Write-Host ("ERROR: App did not become healthy on port {0} within 30s." -f $Port) -ForegroundColor Red
  exit 1
}
Write-Host ("App:               READY  http://127.0.0.1:{0}" -f $Port) -ForegroundColor Green

$cdpReady = $false
$extStatus = "UNKNOWN"
if ($HelperEnabled) {
  function Get-ChromeExe {
    $candidates = @(
      "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
      "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
    )
    foreach ($c in $candidates) {
      if (Test-Path $c) { return $c }
    }
    $onPath = (Get-Command chrome.exe -ErrorAction SilentlyContinue)
    if ($onPath) { return $onPath.Source }
    return $null
  }

  function Test-Cdp {
    try {
      $v = Invoke-RestMethod -Uri "http://127.0.0.1:$ChromePort/json/version" -TimeoutSec 3 -ErrorAction Stop
      return $true
    } catch { return $false }
  }

  $cdpReady = Test-Cdp
  if ($cdpReady) {
    Write-Host "Chrome CDP already reachable; keeping existing session." -ForegroundColor Green
  } else {
    $chromeExe = Get-ChromeExe
    if (-not $chromeExe) {
      Write-Host "ERROR: chrome.exe not found; cannot start Chrome helper." -ForegroundColor Red
      $extStatus = "FAILED"
    } else {
      Write-Host ("Launching Chrome with helper from {0}..." -f $chromeExe) -ForegroundColor Green
      $cdpArgs = @(
        "--user-data-dir=`"$HelperProfile`"",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=$ChromePort",
        "--remote-allow-origins=*",
        "--disable-background-mode",
        "--load-extension=`"$HelperDir`"",
        "http://127.0.0.1:$Port/"
      )
      try {
        Start-Process -FilePath $chromeExe -ArgumentList $cdpArgs -WindowStyle Normal
      } catch {
        Write-Host ("ERROR: Failed to launch Chrome: {0}" -f $_.Exception.Message) -ForegroundColor Red
        $extStatus = "FAILED"
      }
      $cdpDeadline = (Get-Date).AddSeconds(20)
      while ((Get-Date) -lt $cdpDeadline) {
        if (Test-Cdp) { $cdpReady = $true; break }
        Start-Sleep -Seconds 1
      }
    }
  }

  if (-not $cdpReady) {
    if ($extStatus -ne "FAILED") {
      Write-Host "Chrome helper did not start correctly on port $ChromePort." -ForegroundColor Red
      $extStatus = "FAILED"
    }
  } else {
    $cdpReadyText = "READY  127.0.0.1:$ChromePort"
    $extStatus = "UNKNOWN"
    try {
      $list = Invoke-RestMethod -Uri "http://127.0.0.1:$ChromePort/json/list" -TimeoutSec 3 -ErrorAction Stop
      $found = $false
      foreach ($target in $list) {
        $u = (($target.url -or "") + (($target | Get-Member -Name 'title') -and $target.title) + ($target | ConvertTo-Json -Compress))
        if ($u -match "chrome-helper" -or $u -match "AzureInkbladeDraftHelper") { $found = $true; break }
      }
      if ($found) { $extStatus = "LOADED" }
    } catch { $extStatus = "UNKNOWN" }
  }
} else {
  Write-Host "Chrome helper disabled by -NoChromeHelper; skipping Chrome launch." -ForegroundColor Yellow
  $extStatus = "DISABLED"
}

if ($HelperEnabled) {
  if ($cdpReady) {
    Write-Host ("Chrome CDP:        READY  127.0.0.1:{0}" -f $ChromePort) -ForegroundColor Green
  } else {
    Write-Host ("Chrome CDP:        DOWN  127.0.0.1:{0}" -f $ChromePort) -ForegroundColor Red
  }
  Write-Host ("Chrome helper ext: {0}" -f $extStatus)
  if ($cdpReady) {
    Write-Host "Facebook/X:        READY (CDP 9222 present)"
  } else {
    Write-Host "Facebook/X:        BLOCKED (CDP 9222 not present)"
  }
} else {
  Write-Host "Chrome helper ext: DISABLED"
  Write-Host "Facebook/X:        BLOCKED (helper disabled)"
}

Write-Host ""
Write-Host "Opening UI: http://127.0.0.1:$Port/" -ForegroundColor Cyan
Start-Process "http://127.0.0.1:$Port/"

if ($null -ne $appProcess) {
  Write-Host ""
  Write-Host "Launcher is holding the app process. Close this window to stop the session." -ForegroundColor Yellow
  try {
    $appProcess.WaitForExit()
  } catch {
    Wait-Process -Id $appProcess.Id -ErrorAction SilentlyContinue
  }
} else {
  Write-Host ""
  Write-Host "App was reused from an existing instance. Launcher will now exit; close the app separately if needed." -ForegroundColor Yellow
}
