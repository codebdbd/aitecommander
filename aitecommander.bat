@echo off
cd /d "D:\01_Codebdbd\01_projects\aitecommander"
call venv\Scripts\activate
:: Установка необходимых зависимостей
python -m pip install pywin32 beautifulsoup4
python -m app.main
pause