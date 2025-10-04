@echo off
REM Скрипт для обновления файлов переводов

echo Generating translation files...
pylupdate6 app.pro

echo.
echo Translation files generated: app_en.ts, app_uk.ts
echo.
echo Next steps:
echo 1. Edit translations in Qt Linguist: linguist app_en.ts
echo 2. Compile translations: lrelease app_en.ts -qm app_en.qm
echo 3. Compile translations: lrelease app_uk.ts -qm app_uk.qm
echo.
pause
