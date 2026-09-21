@echo off
rem Windows launcher: creates a virtual environment on first run, then starts the app.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python app.py %*
