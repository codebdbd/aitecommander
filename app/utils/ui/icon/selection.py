from pathlib import Path
from typing import Optional, Tuple

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
    file_filter: Optional[str] = None,
) -> Tuple[Optional[str], Optional[QIcon]]:
    """Opens icon selection dialog, copies to user_icons_dir (without duplicates)
    and returns (filename, QIcon). If cancelled — (None, None).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    start_dir = str(user_icons_dir)
    logger.info("[ICON_COPY] Starting icon selection, dir=%s", start_dir)

    # Form filter by configuration if not explicitly passed
    if not file_filter:
        exts = list(app_config.get_supported_icon_formats())
        # Ensure extensions start with a dot and compose *.ext patterns
        patterns = [f"*{ext if ext.startswith('.') else '.' + ext}" for ext in exts]
        # Human-readable label
        file_filter = "Images (" + " ".join(patterns) + ")"

    logger.info("[ICON_COPY] Opening QFileDialog...")
    path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)
    logger.info("[ICON_COPY] QFileDialog closed, selected path: %s", path)
    
    if not path:
        logger.info("[ICON_COPY] No file selected, returning None")
        return None, None

    logger.info("[ICON_COPY] Calling copy_icon_smart...")
    fname = copy_icon_smart(path, user_icons_dir, avoid_duplicates=True)
    logger.info("[ICON_COPY] copy_icon_smart returned: %s", fname)
    
    dest_path = user_icons_dir / fname
    logger.info("[ICON_COPY] Creating icon from: %s", dest_path)
    icon = create_icon_from_path(str(dest_path))
    logger.info("[ICON_COPY] Icon created, isNull=%s", icon.isNull())
    
    return fname, icon
