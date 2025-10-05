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
    title: str = "Выбрать иконку",
    file_filter: str | None = None,
) -> tuple[str | None, QIcon | None]:
    """Открывает диалог выбора иконки, копирует её в user_icons_dir (без дублей)
    и возвращает (имя_файла, QIcon). Если отменено — (None, None).
    """
    start_dir = str(user_icons_dir)

    # Формируем фильтр по конфигурации, если явно не передан
    if not file_filter:
        exts = list(app_config.get_supported_icon_formats())
        # Убедимся, что расширения начинаются с точки и составим шаблоны *.ext
        patterns = [f"*{ext if ext.startswith('.') else '.' + ext}" for ext in exts]
        # Человекочитаемая подпись
        file_filter = "Изображения (" + " ".join(patterns) + ")"

    path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)
    if not path:
        return None, None

    fname = copy_icon_smart(path, user_icons_dir, avoid_duplicates=True)
    dest_path = user_icons_dir / fname
    icon = create_icon_from_path(str(dest_path))
    return fname, icon
