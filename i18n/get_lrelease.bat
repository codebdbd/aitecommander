@echo off

REM Скрипт для загрузки lrelease.exe через разные методы

echo Загрузка lrelease.exe...
echo.

echo Метод 1: Используем curl...
curl --version >nul 2>&1
if %errorlevel% equ 0 (
    curl -L https://github.com/thurask/Qt-Linguist/releases/download/v6.9.2/lrelease.exe -o lrelease.exe
    goto :check
)

echo Метод 2: Используем PowerShell...
powershell -Command "[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/thurask/Qt-Linguist/releases/download/v6.9.2/lrelease.exe' -OutFile 'lrelease.exe'"
if exist lrelease.exe goto :check

echo Метод 3: Используем bitsadmin...
bitsadmin /transfer download /download /priority normal https://github.com/thurask/Qt-Linguist/releases/download/v6.9.2/lrelease.exe lrelease.exe

echo.
:check
if exist lrelease.exe (
    echo Успешно скачано!
    .\lrelease.exe -version
) else (
    echo Ошибка скачивания!
    echo Откройте в браузере:
    echo https://github.com/thurask/Qt-Linguist/releases/download/v6.9.2/lrelease.exe
    echo и сохраните в эту папку
)

echo.
pause
