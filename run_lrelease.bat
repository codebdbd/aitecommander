@echo off
setlocal
set "QT_BIN=%~dp0.venv\Lib\site-packages\qt6_applications\Qt\bin"
set "PATH=%QT_BIN%;%PATH%"
"%QT_BIN%\lrelease.exe" "%~dp0i18n\app.pro"
