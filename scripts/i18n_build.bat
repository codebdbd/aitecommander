@echo off
echo Starting i18n compilation...

REM Create i18n directory if it doesn't exist
if not exist "i18n" mkdir i18n

REM Compile all .ts files to .qm files
echo Compiling translations...
lrelease i18n/*.ts

if %errorlevel% neq 0 (
    echo ERROR: Failed to compile translations
    pause
    exit /b 1
)

echo Translation compilation completed successfully!
echo Files created:
echo   - i18n/app_en.qm
echo   - i18n/app_uk.qm
echo   - i18n/app_ru.qm
echo   - i18n/app_fr.qm
echo   - i18n/app_es.qm
echo   - i18n/app_de.qm
echo.
echo Translation files are ready for deployment.
echo.
pause
