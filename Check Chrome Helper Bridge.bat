@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:9222/json/version' -TimeoutSec 5; Write-Host 'Chrome helper bridge is READY'; Write-Host $r.Browser; Write-Host $r.webSocketDebuggerUrl } catch { Write-Host 'Chrome helper bridge is NOT reachable'; Write-Host $_.Exception.Message }"
pause
