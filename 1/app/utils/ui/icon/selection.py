from pathlib import Path

from PyQt6.QtCore import QEventLoop, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from app.config_data import app_config

# Reuse existing operations
from app.utils.ui.icon.icon_operations.converters import copy_icon_smart
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path


class IconCopyWorker(QThread):
    """Worker thread for copying icons without blocking GUI."""

    finished = pyqtSignal(str, QIcon)  # filename, icon
    error = pyqtSignal(str)  # error message

    def __init__(self, src_path: str, dest_dir: Path, avoid_duplicates: bool = True):
        super().__init__()
        self.src_path = src_path
        self.dest_dir = dest_dir
        self.avoid_duplicates = avoid_duplicates

    def run(self):
        """Execute icon copying in background thread."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info("[ICON_SELECT] Worker started: src=%s, dest_dir=%s", 
                       self.src_path, self.dest_dir)
            # Heavy I/O operations in background thread
            fname = copy_icon_smart(self.src_path, self.dest_dir, self.avoid_duplicates)
            logger.info("[ICON_SELECT] copy_icon_smart returned: %s", fname)
            dest_path = self.dest_dir / fname
            
            # Clear cache for this path to ensure fresh icon is loaded
            # (important when replacing existing icon with same filename)
            from app.utils.ui.icon.cache_manager import invalidate
            cache_key = f"abspath::{str(dest_path)}"
            logger.info("[ICON_SELECT] Invalidating cache for: %s", cache_key)
            invalidate(cache_key)
            
            # QIcon creation is safe in worker thread (uses QImage internally)
            logger.info("[ICON_SELECT] Creating icon from: %s", dest_path)
            icon = create_icon_from_path(str(dest_path))
            logger.info("[ICON_SELECT] Icon created, isNull=%s", icon.isNull())
            self.finished.emit(fname, icon)
            logger.info("[ICON_SELECT] Worker finished successfully")
        except Exception as e:
            logger.error("[ICON_SELECT] Worker exception: %s", e, exc_info=True)
            self.error.emit(str(e))


def choose_icon_and_copy(
    parent,
    user_icons_dir: Path,
    title: str = "Select Icon",
    file_filter: str | None = None,
) -> tuple[str | None, QIcon | None]:
    import logging
    logger = logging.getLogger(__name__)
    """Opens icon selection dialog using non-blocking QFileDialog instance.

    Copies selected icon to user_icons_dir (without duplicates) and returns
    (filename, QIcon). If cancelled — (None, None).

    This approach avoids deadlock when called from modal dialogs by:
    1. Creating a QFileDialog instance with exec() instead of static method
    2. Running heavy I/O operations (copy, hash, convert) in background thread

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
    logger.info("[ICON_SELECT] Showing QFileDialog...")
    result = dialog.exec()
    logger.info("[ICON_SELECT] QFileDialog closed with result: %s (Accepted=%s)", 
               result, QFileDialog.DialogCode.Accepted)
    
    if result != QFileDialog.DialogCode.Accepted:
        logger.info("[ICON_SELECT] User cancelled file selection")
        return None, None

    selected_files = dialog.selectedFiles()
    logger.info("[ICON_SELECT] Selected files: %s", selected_files)
    if not selected_files:
        logger.warning("[ICON_SELECT] No files selected despite Accepted result")
        return None, None

    path = selected_files[0]
    logger.info("[ICON_SELECT] Selected path: %s", path)
    if not path:
        logger.warning("[ICON_SELECT] Selected path is empty")
        return None, None

    # Run heavy I/O operations in background thread to avoid GUI freeze
    worker = IconCopyWorker(path, user_icons_dir, avoid_duplicates=True)

    # Create local event loop to wait for worker completion
    loop = QEventLoop()
    result_fname = None
    result_icon = None
    error_msg = None

    def on_finished(fname: str, icon: QIcon):
        nonlocal result_fname, result_icon
        result_fname = fname
        result_icon = icon
        loop.quit()

    def on_error(msg: str):
        nonlocal error_msg
        error_msg = msg
        loop.quit()

    worker.finished.connect(on_finished)
    worker.error.connect(on_error)
    worker.start()

    # Wait for worker to complete (non-blocking for GUI)
    loop.exec()

    # Clean up worker
    worker.wait()

    if error_msg:
        # Show error to user
        logger.error("[ICON_SELECT] Worker error: %s", error_msg)
        QMessageBox.warning(
            parent, "Icon Selection Error", f"Failed to copy icon: {error_msg}"
        )
        return None, None

    logger.info("[ICON_SELECT] SUCCESS: fname=%s, icon.isNull=%s", 
               result_fname, result_icon.isNull() if result_icon else "N/A")
    return result_fname, result_icon
