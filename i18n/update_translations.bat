@echo off
REM Скрипт для обновления файлов переводов
REM Использует новый синтаксис pylupdate6

echo ========================================
echo  Updating Translation Files
echo ========================================
echo.

REM Use Python helper script (recommended)
python update_and_report.py --update

echo.
echo ========================================
echo Translation files updated!
echo ========================================
echo.
echo Next steps:
echo 1. Edit translations in Qt Linguist:
echo    linguist app_en.ts
echo    linguist app_uk.ts
echo.
echo 2. Compile translations:
echo    compile_translations.bat
echo.
echo 3. Or use automated workflow:
echo    python update_and_report.py --all
echo.
pause
