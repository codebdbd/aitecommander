"""Dialog used to restore the application database from backups."""

import datetime
import logging
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.i18n.common import tr as tr_common
from app.views.common.retranslatable import ReTranslatable

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


class RestoreDbDialog(BaseDialog):
    """Dialog that lets the user pick and restore a database backup."""

    def __init__(self, backup_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)

        width, height = app_config.ui.get_restore_db_dialog_size()
        self.resize(max(width, 580), max(height, 320))
        self.setMinimumWidth(500)
        self.setMinimumHeight(240)
        self.setModal(True)

        self.paths = app_config.paths
        self.backup_dir = backup_dir or self.paths.get_backups_dir()
        self.selected_backup = None

        self._init_ui()
        self._populate_list()

        ReTranslatable.__init__(self)

    def _init_ui(self) -> None:
        """Initialise dialog widgets and wiring."""
        layout = QVBoxLayout(self)

        row_height = int(app_config.ui.get_row_height())
        self.table_widget = QTableWidget(self)
        self.table_widget.setObjectName("backupsTable")
        self.table_widget.setColumnCount(3)
        self.table_widget.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table_widget.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setShowGrid(False)
        self.table_widget.setWordWrap(False)
        self.table_widget.setCornerButtonEnabled(False)

        header = self.table_widget.horizontalHeader()
        header.setHighlightSections(False)
        header.setFixedHeight(row_height)
        header.setDefaultSectionSize(row_height)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.verticalHeader().setDefaultSectionSize(row_height)

        layout.addWidget(self.table_widget)
        self.list_widget = self.table_widget

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        self.buttons.button(QDialogButtonBox.StandardButton.Ok)

        self.buttons.button(QDialogButtonBox.StandardButton.Cancel)

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.table_widget.itemSelectionChanged.connect(self._update_ok_state)
        self.table_widget.itemDoubleClicked.connect(self.accept)

    def _populate_list(self) -> None:
        """Populate available backups in the table widget."""
        self.table_widget.setRowCount(0)

        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Scanning backup directory: %s", self.backup_dir)

            backups = self._get_backup_files()
            logger.debug("Backups discovered: %s", len(backups))

            if not backups:
                self._show_no_backups_message()
            else:
                self._populate_backup_list(backups)
                if self.table_widget.rowCount() > 0:
                    self.table_widget.setEnabled(True)
                    self.table_widget.selectRow(0)
                else:
                    self._show_no_backups_message()
                self._update_ok_state()

        except Exception as e:
            logger.error("Failed to list database backups: %s", e)
            self._show_error_message(self.tr("Failed to list database backups: {error}").format(error=str(e)))

    def _show_no_backups_message(self) -> None:
        """Display an empty-state entry when no backups exist."""
        self.table_widget.setRowCount(1)
        self.table_widget.setSpan(0, 0, 1, 3)
        item = QTableWidgetItem(
            QCoreApplication.translate("RestoreDbDialog", "No backups found")
        )
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.table_widget.setItem(0, 0, item)
        self.table_widget.setEnabled(False)
        logger.info("No backups found")

    def _populate_backup_list(self, backups: list) -> None:
        """Append discovered backup files to the table."""
        for backup in backups:
            try:
                if backup.stat().st_size == 0:
                    logger.warning("Empty backup file encountered: %s", backup.name)
                    continue

                dt_str = self._parse_datetime(backup.name)
                if not dt_str:
                    try:
                        dt_str = datetime.datetime.fromtimestamp(backup.stat().st_mtime).strftime("%d.%m.%Y %H:%M:%S")
                    except Exception:
                        dt_str = "-"
                size_mb = backup.stat().st_size / (1024 * 1024)

                self._add_table_row(
                    backup_path=backup,
                    timestamp=dt_str,
                    backup_name=backup.name,
                    size_str=f"{size_mb:.1f} MB",
                    font_bold=False,
                )

                logger.debug("Added backup entry: %s", backup.name)

            except Exception as e:
                logger.warning("Failed to process backup file %s: %s", backup.name, e)
                continue

        if self.table_widget.rowCount() > 0:
            self.table_widget.setEnabled(True)
            self.table_widget.selectRow(0)
        else:
            self._show_no_backups_message()

        self._update_ok_state()

    def _show_error_message(self, message: str) -> None:
        """Display an error row when the backup directory cannot be listed."""
        self.table_widget.setRowCount(1)
        self.table_widget.setSpan(0, 0, 1, 3)
        item = QTableWidgetItem(message)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.table_widget.setItem(0, 0, item)
        self.table_widget.setEnabled(False)

    def _add_table_row(
        self,
        backup_path: Path,
        timestamp: str,
        backup_name: str,
        size_str: str,
        font_bold: bool = False,
    ) -> None:
        """Append a single structured backup row to the table."""
        row = self.table_widget.rowCount()
        self.table_widget.insertRow(row)

        dt_item = QTableWidgetItem(timestamp)
        dt_item.setData(Qt.ItemDataRole.UserRole, backup_path)

        name_item = QTableWidgetItem(backup_name)
        name_item.setData(Qt.ItemDataRole.UserRole, backup_path)

        size_item = QTableWidgetItem(size_str)
        size_item.setData(Qt.ItemDataRole.UserRole, backup_path)
        size_item.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        dt_item.setToolTip(timestamp)
        name_item.setToolTip(backup_name)
        size_item.setToolTip(size_str)

        for item in (dt_item, name_item, size_item):
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            if font_bold:
                font = item.font()
                font.setBold(True)
                item.setFont(font)

        self.table_widget.setItem(row, 0, dt_item)
        self.table_widget.setItem(row, 1, name_item)
        self.table_widget.setItem(row, 2, size_item)

    def _parse_datetime(self, filename: str) -> Optional[str]:
        """Parse a timestamp from a backup filename."""
        try:
            base = filename.replace("aite_bd_", "").replace("links_", "").replace(".db", "")

            formats = [
                "%Y%m%d_%H%M%S_%f",
                "%Y%m%d_%H%M%S",
                "%Y-%m-%d_%H-%M-%S",
            ]

            for fmt in formats:
                try:
                    dt = datetime.datetime.strptime(base, fmt)
                    return dt.strftime("%d.%m.%Y %H:%M:%S")
                except ValueError:
                    continue

            logger.debug("Could not parse backup timestamp from filename: %s", filename)
            return None

        except Exception as e:
            logger.debug("Failed to parse date from %s: %s", filename, e)
            return None

    def get_selected_backup(self) -> Optional[Path]:
        """Return the filesystem path for the selected backup entry."""
        if not self.table_widget.isEnabled():
            return None

        row = self.table_widget.currentRow()
        if row < 0:
            return None

        item = self.table_widget.item(row, 0)
        if item is None:
            return None

        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, Path) and path.exists() and path.stat().st_size > 0:
            return path
        return None

    def _get_backup_files(self) -> list[Path]:
        backups: list[Path] = []
        for pattern in ("aite_bd_*.db", "aite_bd_*.zip", "*.bak"):
            for path in self.backup_dir.glob(pattern):
                if path.is_file() and path.stat().st_size > 0:
                    backups.append(path)
        try:
            backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            logger.debug("Failed to sort backups by mtime", exc_info=True)
        return backups

    def _update_ok_state(self) -> None:
        """Enable or disable the OK button based on current selection state."""
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        enabled = (
            self.table_widget.isEnabled()
            and self.table_widget.currentRow() >= 0
            and self.get_selected_backup() is not None
        )
        ok_btn.setEnabled(enabled)

    def accept(self) -> None:
        """Confirm the selected backup and close the dialog when valid."""
        selected_backup = self.get_selected_backup()

        if not selected_backup:
            self.show_warning(
                self.tr("No backup selected."),
                self.tr("Backup selection required"),
                informative_text=self.tr(
                    "Select a file from the list and click 'Restore'. If the list is empty, verify the backup directory."
                ),
            )
            return

        self.selected_backup = selected_backup
        super().accept()

    def get_result(self) -> Optional[Path]:
        """Return the chosen backup path after the dialog closes."""
        return self.selected_backup

    def retranslateUi(self) -> None:
        """Refresh UI strings when the application language changes."""
        if not hasattr(self, "buttons"):
            return

        self.setWindowTitle(tr_common("Restore Database"))

        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText(QCoreApplication.translate("RestoreDbDialog", "Restore"))

        cancel_btn = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText(tr_common("Cancel"))

        self.equalize_button_box(self.buttons, min_width=app_config.ui.get_fixed_button_width())

        if hasattr(self, "table_widget"):
            self.table_widget.setHorizontalHeaderLabels([
                QCoreApplication.translate("RestoreDbDialog", "Date"),
                QCoreApplication.translate("RestoreDbDialog", "Backup"),
                QCoreApplication.translate("RestoreDbDialog", "Size"),
            ])
