from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog

from app.config_data import app_config

# Reuse existing operations
from app.utils.ui.icon.icon_operations.converters import copy_icon_smart
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path


def choose_icon_and_copy(
    parent,
    user_icons_dir: Path,
    title: str = "Select Icon",
    file_filter: str | None = None,
) -> tuple[str | None, QIcon | None]:
    """Opens icon selection dialog using non-blocking QFileDialog instance.
    
    Copies selected icon to user_icons_dir (without duplicates) and returns
    (filename, QIcon). If cancelled — (None, None).
    
    This approach avoids deadlock when called from modal dialogs by creating
    a QFileDialog instance with exec() instead of using the static
    getOpenFileName() method.
    
    Args:
        parent: Parent widget (can be a modal dialog)
        user_icons_dir: Directory to copy selected icon to
        title: Dialog window title
        file_filter: File filter string (auto-generated if None)
    
    Returns:
        Tuple of (filename, QIcon) or (None, None) if cancelled
    """
    start_dir = str(user_icons_dir)

    # Form filter by configuration if not explicitly passed
    if not file_filter:
        exts = list(app_config.get_supported_icon_formats())
        # Ensure extensions start with a dot and compose *.ext patterns
        patterns = [f"*{ext if ext.startswith('.') else '.' + ext}" for ext in exts]
        # Human-readable label
        file_filter = "Images (" + " ".join(patterns) + ")"

    # Create QFileDialog instance instead of using static method
    # This prevents deadlock when parent is a modal dialog
    dialog = QFileDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setNameFilter(file_filter)
    dialog.setDirectory(start_dir)
    
    # Use exec() instead of static getOpenFileName()
    # This creates a proper nested event loop that works correctly
    # with modal parent dialogs
    if dialog.exec() != QFileDialog.DialogCode.Accepted:
        return None, None
    
    selected_files = dialog.selectedFiles()
    if not selected_files:
        return None, None
    
    path = selected_files[0]
    if not path:
        return None, None

    # Copy icon to user directory, avoiding duplicates
    fname = copy_icon_smart(path, user_icons_dir, avoid_duplicates=True)
    dest_path = user_icons_dir / fname
    icon = create_icon_from_path(str(dest_path))
    
    return fname, icon
