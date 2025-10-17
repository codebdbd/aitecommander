# Сборка приложения — Quick Start

## Для разработчиков

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Запустить приложение
python main.py
```

## Для упаковки (PyInstaller)

```bash
# 1. Установить зависимости для сборки
pip install -r requirements.txt
pip install pyinstaller

# 2. Сгенерировать ресурсы
python scripts/generate_icons_qrc.py
pyrcc6 app/resources/icons.qrc -o app/resources/icons_rc.py

# 3. Собрать бинарь
pyinstaller pyinstaller.spec

# 4. Запустить
dist/OsteenPath.exe  # Windows
dist/OsteenPath      # Linux/macOS
```

## Подробная документация

См. [docs/PACKAGING.md](docs/PACKAGING.md)
