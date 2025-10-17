# Упаковка приложения для дистрибуции

Модуль `app.utils.ui.icon` полностью готов к упаковке с **PyInstaller** и **Briefcase**.

---

## Подготовка

### 1. Генерация Qt ресурсов

```bash
# Сгенерировать icons.qrc из ui_icons/
python scripts/generate_icons_qrc.py

# Скомпилировать в Python модуль
pyrcc6 app/resources/icons.qrc -o app/resources/icons_rc.py
```

**Результат:** Все иконки упакованы в `icons_rc.py` и будут встроены в бинарь.

---

## PyInstaller

### Сборка

```bash
# Установка
pip install pyinstaller

# Сборка (используется pyinstaller.spec)
pyinstaller pyinstaller.spec
```

### Что включено автоматически

- ✅ Qt плагины: `platforms`, `imageformats`, `iconengines`, `svg`
- ✅ Hidden imports: `PyQt6.QtSvg`, `PIL.Image`, `app.resources.icons_rc`
- ✅ Custom hook: `hooks/hook-app.utils.ui.icon.py`
- ✅ QRC ресурсы встроены в бинарь

### Тестирование

```bash
# Windows
dist\OsteenPath.exe

# Linux/macOS
dist/OsteenPath
```

### Проверка иконок

После запуска проверьте:
1. SVG иконки отображаются
2. Переключение тем (light/dark) работает
3. Кэш функционирует
4. Нет ошибок в логах

---

## Briefcase

### Конфигурация

Добавьте в `pyproject.toml`:

```toml
[tool.briefcase.app.osteenpath]
formal_name = "Osteen Path"
sources = ["app"]
requires = [
    "PyQt6>=6.5.0",
    "Pillow>=10.0.0",
]

[tool.briefcase.app.osteenpath.macOS]
icon = "app/resources/app_icon"

[tool.briefcase.app.osteenpath.windows]
icon = "app/resources/app_icon"

[tool.briefcase.app.osteenpath.linux]
icon = "app/resources/app_icon"
```

### Сборка

```bash
# Установка
pip install briefcase

# Создание проекта
briefcase create

# Сборка
briefcase build

# Запуск
briefcase run

# Упаковка
briefcase package
```

---

## Структура упакованного приложения

### PyInstaller (onefile)

```
dist/
└── OsteenPath.exe          # Всё встроено (иконки в QRC)
```

### Briefcase

```
macOS/
└── Osteen Path.app/
    └── Contents/
        ├── MacOS/
        │   └── Osteen Path
        └── Resources/
            └── app_packages/
                └── app/
                    └── resources/
                        └── icons_rc.py

Windows/
└── Osteen Path/
    └── Osteen Path.exe

Linux/
└── Osteen Path/
    └── usr/
        └── bin/
            └── osteenpath
```

---

## Troubleshooting

### Иконки не загружаются

**Проблема:** Пустые иконки или ошибки загрузки

**Решение:**
1. Проверьте что `icons_rc.py` импортируется:
   ```python
   import app.resources.icons_rc
   print("QRC available:", _QRC_AVAILABLE)
   ```

2. Проверьте Qt плагины:
   ```python
   from PyQt6.QtCore import QLibraryInfo
   print(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
   ```

3. Проверьте логи:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

### SVG не отображаются

**Проблема:** PNG работают, SVG нет

**Решение:**
- Убедитесь что плагин `svg` включён в `.spec`:
  ```python
  a.datas += collect_qt_plugins('PyQt6', ['svg'])
  ```

### Крэши при создании QIcon

**Проблема:** Segmentation fault или Access Violation

**Решение:**
- Проверьте что QIcon создаётся в GUI-потоке
- Запустите тесты:
  ```bash
  pytest tests/test_icon_thread_safety.py -v
  ```

### Большой размер бинаря

**Проблема:** Exe/app слишком большой (>100 MB)

**Решение:**
1. Исключите ненужные модули в `.spec`:
   ```python
   excludes=['tkinter', 'matplotlib', 'numpy']
   ```

2. Используйте UPX компрессию:
   ```python
   upx=True
   ```

3. Проверьте что не дублируются Qt библиотеки

---

## CI/CD

### GitHub Actions пример

```yaml
name: Build Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller pyrcc6
      
      - name: Generate resources
        run: |
          python scripts/generate_icons_qrc.py
          pyrcc6 app/resources/icons.qrc -o app/resources/icons_rc.py
      
      - name: Build
        run: pyinstaller pyinstaller.spec
      
      - name: Upload
        uses: actions/upload-artifact@v3
        with:
          name: OsteenPath-Windows
          path: dist/OsteenPath.exe
```

---

## Чеклист перед релизом

- [ ] Сгенерированы QRC ресурсы
- [ ] Запущены все тесты (`pytest`)
- [ ] Проверена типизация (`mypy app/utils/ui/icon --strict`)
- [ ] Собран бинарь (`pyinstaller pyinstaller.spec`)
- [ ] Протестирован упакованный бинарь
- [ ] Проверены иконки (SVG + PNG)
- [ ] Проверено переключение тем
- [ ] Проверена работа на чистой системе (без Python)
- [ ] Размер бинаря приемлем (<50 MB для onefile)

---

**Готово к продакшену:** ✅  
**Дата:** 2025-10-17
