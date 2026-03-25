@echo off
REM RefundFish Web UI Startup Script

echo ================================
echo RefundFish - Web UI
echo ================================
echo.

REM Install dependencies if needed
pip install -r requirements.txt

REM Start Flask app
echo Starting web server...
echo Open browser to: http://localhost:5000
echo.

python app.py

pause
