"""Тонкая точка входа для PyInstaller/`python main.py`. Вся бизнес-логика инициализации/cleanup — в app/main."""
import sys
from app.main import main

if __name__ == "__main__":
    sys.exit(main())
