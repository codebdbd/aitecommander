@echo off
echo Starting i18n extraction...

REM Create i18n directory if it doesn't exist
if not exist "i18n" mkdir i18n

REM Extract translations for all supported languages
echo Extracting translations...
pylupdate6 -recursive app -ts i18n/app_en.ts i18n/app_uk.ts i18n/app_ru.ts i18n/app_fr.ts i18n/app_es.ts i18n/app_de.ts

if %errorlevel% neq 0 (
    echo ERROR: Failed to extract translations
    pause
    exit /b 1
)

echo Translation extraction completed successfully!
echo Files updated:
echo   - i18n/app_en.ts
echo   - i18n/app_uk.ts
echo   - i18n/app_ru.ts
echo   - i18n/app_fr.ts
echo   - i18n/app_es.ts
echo   - i18n/app_de.ts
echo.
echo Next steps:
echo 1. Open .ts files in Qt Linguist to add translations
echo 2. Run i18n_build.bat to compile .qm files
echo.
pause
