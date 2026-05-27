@echo off
cd /d "%~dp0"
git -c safe.directory="%CD%" remote get-url origin >nul 2>nul
if errorlevel 1 git -c safe.directory="%CD%" remote add origin https://github.com/azureinkblade-ops/Automation-tool.git
git -c safe.directory="%CD%" branch -M main
git -c safe.directory="%CD%" add .
git -c safe.directory="%CD%" commit -m "Update automation tool"
git -c safe.directory="%CD%" push -u origin main
pause
