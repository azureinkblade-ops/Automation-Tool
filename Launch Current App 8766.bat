@echo off
call powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launch_automation_tool.ps1" -Port 8766
pause
