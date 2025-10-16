# setup.py
from PyInstaller.__main__ import run

if __name__ == "__main__":
    opts = [
        "--name=LinkManager",
        "--onefile",
        "--windowed",
        "app/main.py",
        "--add-data",
        "app/resources/qss;app/resources/qss",
        "--add-data",
        "app/resources/ui_icons;app/resources/ui_icons",
    ]
    run(opts)
