# setup.py
from PyInstaller.__main__ import run

if __name__ == "__main__":
    opts = [
        "--name=LinkManager",
        "--onefile",
        "--windowed",
        "app/main.py",
        "--add-data",
        "app/views/resources/qss;app/views/resources/qss",
        "--add-data",
        "app/views/resources/ui_icons;app/views/resources/ui_icons",
    ]
    run(opts)
