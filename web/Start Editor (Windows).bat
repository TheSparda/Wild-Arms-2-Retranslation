@echo off
rem Serves the WA2 Translation Editor locally and opens it. Nothing leaves your machine.
cd /d "%~dp0"
start "" http://localhost:8478/
python -m http.server 8478
