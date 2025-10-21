"""Helper functions for asynchronous DB operations.

UI code is separated; functions return status and messages instead of showing dialogs directly.
"""

import logging
from typing import Any, Callable, Optional

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QWidget

from app.views.windows.dialogs.async_operation_dialog import AsyncOperationDialog

logger = logging.getLogger(__name__)

_TR_CONTEXT = "AsyncHelpers"


def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)


def run_async_import(
    db,
    data: list,
    parent: Optional[QWidget] = None,
    on_success: Optional[Callable] = None,
    title: str = "Import data",
    cancelable: bool = False,
) -> tuple[bool, Optional[str], Optional[dict]]:
    """Run asynchronous import with a progress dialog.

    Returns a tuple (success, message, stats) instead of showing QMessageBox.

    Args:
        db: Database instance
        data: Data to import
        parent: Parent widget
        on_success: Callback on success (receives stats)
        title: Dialog title
        cancelable: Whether the operation can be cancelled

    Returns:
        Tuple[bool, Optional[str], Optional[dict]]: (success, message, stats)

    Example:
        >>> success, msg, stats = run_async_import(db, data, parent=self)
        >>> if success and msg:
        ...     QMessageBox.information(self, _tr("Import"), msg)
    """
    result_stats = None
    result_message = None
    result_success = False
    dialog = AsyncOperationDialog(
        title=_tr(title),
        message=_tr("Importing data structure..."),
        cancelable=cancelable,
        parent=parent,
    )

    def on_finished(stats):
        nonlocal result_stats, result_message, result_success
        dialog.on_finished(stats)

        result_stats = stats
        result_success = True
        result_message = (
            _tr("Imported:") + "\n"
            "• " + _tr("Spheres") + f": {stats.get('spheres', 0)}\n"
            f"• " + _tr("Sections") + f": {stats.get('sections', 0)}\n"
            f"• " + _tr("Categories") + f": {stats.get('categories', 0)}\n"
            f"• " + _tr("Links") + f": {stats.get('links', 0)}"
        )

        if on_success:
            on_success(stats)

    def on_error(e, tb):
        nonlocal result_message, result_success
        dialog.on_error(e, tb)

        result_success = False
        result_message = _tr("Failed to import data:") + f"\n{str(e)}"

    # Start asynchronous import
    db.import_full_structure_async(
        data,
        on_finished=on_finished,
        on_error=on_error,
        on_progress=dialog.update_progress,
    )
    dialog.exec()

    return result_success, result_message, result_stats


def run_async_export(
    db,
    parent: Optional[QWidget] = None,
    on_success: Optional[Callable] = None,
    title: str = "Export data",
) -> tuple[bool, Optional[str], Any]:
    """Run asynchronous export with a progress dialog.

    Returns (success, message, exported_data) instead of showing QMessageBox.

    Args:
        db: Database instance
        parent: Parent widget
        on_success: Callback on success (receives result)
        title: Dialog title

    Returns:
        Tuple[bool, Optional[str], Any]: (success, message, exported_data)
    """
    result_success = False
    result_message: Optional[str] = None
    result_data: Any = None

    dialog = AsyncOperationDialog(
        title=_tr(title),
        message=_tr("Exporting data structure..."),
        cancelable=False,
        parent=parent,
    )

    def on_finished(result):
        nonlocal result_data, result_success, result_message
        result_data = result
        result_success = True
        dialog.on_finished(result)

        if result:
            count = (
                len(result.get("spheres", []))
                + len(result.get("sections", []))
                + len(result.get("categories", []))
                + len(result.get("links", []))
            )
            result_message = _tr("Exported %1 records").replace("%1", str(count))

    def on_error(e, tb):
        nonlocal result_success, result_message
        dialog.on_error(e, tb)

        result_success = False
        result_message = _tr("Failed to export data:") + f"\n{str(e)}"

    # Start asynchronous export
    db.export_full_structure_async(
        on_error=on_error, on_progress=dialog.update_progress
    )

    dialog.exec()
    return result_success, result_message, result_data


def run_async_backup(
    db, parent: Optional[QWidget] = None
) -> tuple[bool, Optional[str]]:
    """Run asynchronous backup.

    Returns (success, message) instead of showing QMessageBox.

    Args:
        db: Database instance
        parent: Parent widget
        on_success: Callback on success

    Returns:
        Tuple[bool, Optional[str]]: (success, message)

    Example:
        >>> success, msg = run_async_backup(db, parent=self)
        >>> if success and msg:
        ...     QMessageBox.information(self, "Backup", msg)
    """
    result_success = False
    result_message = None

    def on_finished(result):
        nonlocal result_success, result_message
        backup_file = result.get("backup_filename", _tr("unknown"))
        logger.info(f"Backup created: {backup_file}")

        result_success = True
        result_message = _tr("Backup created:") + f"\n{backup_file}"

    def on_error(e, tb):
        nonlocal result_success, result_message
        logger.error(f"Backup error: {e}")

        result_success = False
        result_message = _tr("Failed to create backup:") + f"\n{str(e)}"

    # Start asynchronous backup (without dialog)
    db.backup_async(on_finished=on_finished, on_error=on_error)

    return result_success, result_message
