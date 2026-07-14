@echo off
cd /d "%~dp0"

if not exist ".venv" (
    echo Error: .venv folder not found.
    echo Please create a virtual environment first:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

call .venv\Scripts\activate

echo Starting Aite Commander...
python -m app.main
