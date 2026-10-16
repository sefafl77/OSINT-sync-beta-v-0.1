@echo off
setlocal
chcp 65001 >nul
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Setup belum tersedia. Jalankan scripts\install-codex.ps1 dahulu.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -X utf8 "%~dp0cti.py" %*
if errorlevel 1 pause
