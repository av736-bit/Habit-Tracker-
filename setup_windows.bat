@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m venv .venv) else (python -m venv .venv)
if errorlevel 1 (
 echo Python 3.10+ must be installed first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo Setup complete. Edit .env with your credentials if you want iCloud/Outlook syncing.
echo Then double-click run_windows.bat.
pause
