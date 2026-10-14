@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
 start "Momentum Reminders" /MIN ".venv\Scripts\pythonw.exe" "%~dp0reminder_agent.py"
 echo Started the Windows reminder agent in the background.
) else (
 echo Run setup_windows.bat first.
)
pause
