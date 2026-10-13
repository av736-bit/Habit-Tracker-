@echo off
cd /d "%~dp0"
echo Installing or verifying requirements...
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo Could not install required packages. Check Python and your internet connection.
    pause
    exit /b 1
)
echo Starting Momentum Habit Tracker...
py -m streamlit run app.py
pause
