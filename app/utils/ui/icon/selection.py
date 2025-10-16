import shutil
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog, QWidget

from app.config_data import app_config


def choose_icon_and_copy(
    parent: QWidget,
    user_icons_dir: Path,
    title: str = "Select Icon",
    file_filter: str | None = None,
) -> tuple[str | None, QIcon | None]:
    """Opens icon selection dialog, copies it to user_icons_dir and returns (filename, QIcon)."""
    start_dir = str(user_icons_dir)

    if not file_filter:
        exts = list(app_config.get_supported_icon_formats())
        patterns = [f"*{ext if ext.startswith('.') else '.' + ext}" for ext in exts]
        file_filter = "Images (" + " ".join(patterns) + ")"

    path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)
    if not path:
        return None, None

    src = Path(path)
    user_icons_dir.mkdir(parents=True, exist_ok=True)
    dst = user_icons_dir / src.name
    
    counter = 1
    while dst.exists():
        dst = user_icons_dir / f"{src.stem}_{counter}{src.suffix}"
        counter += 1
    
    shutil.copy2(src, dst)
    icon = QIcon(str(dst))
    return dst.name, icon
