# Установка lrelease для компиляции переводов

## Проблема
`lrelease` не включен в PyQt6. Нужен для компиляции `.ts` → `.qm` файлов.

## Решение: Скачать только lrelease.exe

### Вариант 1: Через Qt Online Installer (рекомендуется)

1. **Скачать Qt Online Installer:**
   https://www.qt.io/download-qt-installer

2. **Запустить установщик:**
   - Создать бесплатный Qt аккаунт
   - Выбрать "Custom Installation"
   - Выбрать только: **Qt 6.x → Developer and Designer Tools → Qt Linguist**
   - Размер: ~50 МБ (вместо полных 3+ ГБ)

3. **Добавить в PATH:**
   ```
   C:\Qt\6.x.x\msvc2019_64\bin
   ```
   Или скопировать `lrelease.exe` в `i18n/` директорию

### Вариант 2: Прямая ссылка на бинарники

1. **Скачать Qt binaries:**
   https://download.qt.io/official_releases/qt/6.5/6.5.3/single/

2. **Извлечь только lrelease.exe:**
   - Из архива: `qt-everywhere-src-6.5.3.zip`
   - Путь: `qttools/bin/lrelease.exe`

3. **Скопировать в проект:**
   ```
   B:\osteen path\i18n\lrelease.exe
   ```

### Вариант 3: Через Chocolatey (Windows)

```powershell
choco install qt-creator-tools
```

### Вариант 4: Скачать готовый lrelease.exe

Можно найти готовый `lrelease.exe` в интернете и скопировать в `i18n/`.

**Проверка после установки:**
```bash
lrelease -version
# или
.\i18n\lrelease.exe -version
```

---

## После установки

Запустите компиляцию:
```bash
python i18n\update_and_report.py --compile
```

Или вручную:
```bash
lrelease i18n\app_en.ts -qm i18n\app_en.qm
lrelease i18n\app_uk.ts -qm i18n\app_uk.qm
```
