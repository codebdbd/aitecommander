from pathlib import Path
from typing import Optional, Tuple

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog, QWidget

# Reuse existing operations
from app.utils.ui.icon.icon_operations.converters import copy_icon_smart
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path


def choose_icon_and_copy(
    parent: QWidget,
    user_icons_dir: Path,
    title: str = "Выбрать иконку",
    file_filter: str = "Изображения (*.png *.ico *.jpg *.svg)",
) -> Tuple[Optional[str], Optional[QIcon]]:
    """Открывает диалог выбора иконки, копирует её в user_icons_dir (без дублей)
    и возвращает (имя_файла, QIcon). Если отменено — (None, None).
    """
    start_dir = str(user_icons_dir)
    path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)
    if not path:
        return None, None

    fname = copy_icon_smart(path, user_icons_dir, avoid_duplicates=True)
    dest_path = user_icons_dir / fname
    icon = create_icon_from_path(str(dest_path))
    return fname, icon
