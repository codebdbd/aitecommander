# Скрипт для автоматической загрузки lrelease.exe
$ErrorActionPreference = "Stop"

# URL для скачивания
$url = "https://github.com/thurask/Qt-Linguist/releases/download/v6.9.2/lrelease.exe"

# Путь для сохранения
$output = "lrelease.exe"

# Загружаем файл
try {
    Write-Host "Скачивание lrelease.exe..." -ForegroundColor Cyan
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    
    # Используем разные методы скачивания
    try {
        # Метод 1: Standard Invoke-WebRequest
        Invoke-WebRequest -Uri $url -OutFile $output -UserAgent "Mozilla/5.0"
    }
    catch {
        # Метод 2: WebClient
        try {
            (New-Object System.Net.WebClient).DownloadFile($url, $output)
        }
        catch {
            # Метод 3: BITS
            try {
                Start-BitsTransfer -Source $url -Destination $output
            }
            catch {
                Write-Host "Все методы скачивания не сработали" -ForegroundColor Red
                throw
            }
        }
    }
    
    Write-Host "Успешно скачано!" -ForegroundColor Green
}
catch {
    Write-Host "Ошибка скачивания: $_" -ForegroundColor Red
    Write-Host "Альтернативный вариант:"
    Write-Host "1. Откройте в браузере: https://github.com/thurask/Qt-Linguist/releases/download/v6.9.2/lrelease.exe"
    Write-Host "2. Сохраните файл в папку i18n"
    exit 1
}

# Проверяем файл
if (Test-Path $output) {
    Write-Host "Проверка файла..." -ForegroundColor Cyan
    try {
        $version = & ".\$output" -version 2>&1
        Write-Host "Версия: $version" -ForegroundColor Green
    }
    catch {
        Write-Host "Файл скачан, но не запускается: $_" -ForegroundColor Yellow
        Write-Host "Попробуйте скачать вручную"
    }
}
else {
    Write-Host "Файл не найден после скачивания" -ForegroundColor Red
    exit 1
}
