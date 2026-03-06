@echo off
echo Starting Ant Colony Finance with Real-Time Dashboard...
echo.

REM Start WebSocket server in background
start "WebSocket Server" cmd /k "cd /d %~dp0 && .venv\Scripts\activate && python websocket_server.py"
timeout /t 2 /nobreak >nul

REM Start dashboard server in background
start "Dashboard Server" cmd /k "cd /d %~dp0 && .venv\Scripts\activate && python serve_dashboard.py"
timeout /t 2 /nobreak >nul

REM Start colony in foreground
echo.
echo Starting colony in paper trading mode...
echo.
call .venv\Scripts\activate
python main.py --paper

pause
