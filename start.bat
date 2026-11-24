@echo off
title VyaparVoice AI - Server Launcher
echo ========================================================
echo  VyaparVoice AI (व्यापार-Voice) - Bharat Operations Copilot
echo ========================================================
echo Starting server on http://localhost:5000 ...
cd /d "%~dp0backend"
python app.py
pause
