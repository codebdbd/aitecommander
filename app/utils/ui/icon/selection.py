from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog, QWidget

from app.config_data import app_config

# Reuse existing operations
from app.utils.ui.icon.icon_operations.converters import copy_icon_smart
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path


def choose_icon_and_copy(
    parent: QWidget,
    user_icons_dir: Path,
    title: str = "Select Icon",
    file_filter: str | None = None,
) -> tuple[str | None, QIcon | None]:
    """Opens icon selection dialog, copies it to user_icons_dir (without duplicates)
    and returns (filename, QIcon). If cancelled — (None, None).
    """
    start_dir = str(user_icons_dir)

    # Form filter by configuration if not explicitly passed
    if not file_filter:
        exts = list(app_config.get_supported_icon_formats())
        # Ensure extensions start with a dot and compose *.ext patterns
        patterns = [f"*{ext if ext.startswith('.') else '.' + ext}" for ext in exts]
        # Human-readable label
        file_filter = "Images (" + " ".join(patterns) + ")"

    path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)
    if not path:
        return None, None

    fname = copy_icon_smart(path, user_icons_dir, avoid_duplicates=True)
    dest_path = user_icons_dir / fname
    icon = create_icon_from_path(str(dest_path))
    return fname, icon
