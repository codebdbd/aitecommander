@echo off
REM Скрипт для компиляции файлов переводов в бинарный формат

echo Compiling English translations...
lrelease app_en.ts -qm app_en.qm

echo Compiling Ukrainian translations...
lrelease app_uk.ts -qm app_uk.qm

echo.
echo Translation files compiled successfully!
echo - app_en.qm
echo - app_uk.qm
echo.
pause
