from pathlib import Path

from PyQt6.QtCore import QThread
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QFileDialog, QWidget

from .file_service import IconFileService


def choose_icon_and_copy(
    parent: QWidget,
    user_icons_dir: Path,
    title: str = "Select Icon",
    file_filter: str | None = None,
) -> tuple[str | None, QIcon | None]:
    """Opens icon selection dialog, copies it to user_icons_dir and returns (filename, QIcon).
    
    This function handles UI (dialog) only. File operations are delegated to IconFileService.
    
    Note:
        Must be called from GUI thread as it creates QIcon.
        
    Raises:
        RuntimeError: If called from non-GUI thread.
        ValueError: If selected file is not a valid icon.
        OSError: If file copy operation fails.
    """
    # Thread safety check: QIcon must be created only in GUI thread
    app = QApplication.instance()
    if app and QThread.currentThread() != app.thread():
        raise RuntimeError("choose_icon_and_copy must be called from GUI thread")
    
    # Initialize file service
    file_service = IconFileService(user_icons_dir)
    
    # Prepare file filter
    if not file_filter:
        file_filter = file_service.get_supported_formats_filter()
    
    # Open dialog
    start_dir = str(user_icons_dir)
    path, _ = QFileDialog.getOpenFileName(parent, title, start_dir, file_filter)
    if not path:
        return None, None
    
    # Delegate file operations to service
    try:
        dst = file_service.copy_icon_to_user_dir(Path(path), user_icons_dir)
    except (FileNotFoundError, ValueError, OSError) as e:
        # Re-raise with context
        raise type(e)(f"Failed to copy icon: {e}") from e
    
    # QIcon creation is safe here as we verified GUI thread at function start
    icon = QIcon(str(dst))
    return dst.name, icon
