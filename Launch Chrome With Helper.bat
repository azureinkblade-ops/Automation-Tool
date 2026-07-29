@echo off
cd /d "%~dp0"

set "CHROME_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" set "CHROME_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_EXE%" set "CHROME_EXE=chrome"
set "HELPER_PROFILE=%LOCALAPPDATA%\AzureInkbladeAutomationChrome"

echo Checking Chrome helper bridge...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:9222/json/version' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% EQU 0 (
  echo Helper bridge already running. Keeping your logged-in Chrome session.
  goto done
)

echo Starting Chrome with Azure Inkblade helper extension and debug bridge...
echo Chrome executable: %CHROME_EXE%
echo Helper profile: %HELPER_PROFILE%
start "" "%CHROME_EXE%" --user-data-dir="%HELPER_PROFILE%" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --remote-allow-origins=* --disable-background-mode --load-extension="%CD%\chrome-helper" "http://127.0.0.1:8765/"
ping 127.0.0.1 -n 4 >nul

:done
