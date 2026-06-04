@echo off
REM Start the swing backend API on http://localhost:8000
cd /d %~dp0
set PYTHONPATH=.
python server.py
