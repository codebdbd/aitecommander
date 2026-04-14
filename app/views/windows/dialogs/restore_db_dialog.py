"""Dialog used to restore the application database from backups."""

import datetime
import logging
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.i18n.common import tr as tr_common
from app.views.common.retranslatable import ReTranslatable

from .base_dialog import BaseDialog

_LIST_ITEM_TEMPLATES: dict[str, str] = {
    "no_backups": "Резервные копии не найдены",
    "single_backup": "{timestamp} | {backup_name} ({size} МБ)",
    "auto_backup_with_timestamp": "{timestamp} | {backup_name} ({size} МБ)",
    "auto_backup_without_timestamp": "{backup_name} ({size} МБ)",
    "error": "Ошибка: {details}",
}

logger = logging.getLogger(__name__)


class RestoreDbDialog(BaseDialog):
    """Dialog that lets the user pick and restore a database backup."""

    def __init__(self, backup_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)

        width, height = app_config.ui.get_restore_db_dialog_size()
        self.resize(width, height)
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

        self.list_widget = QListWidget(self)
        layout.addWidget(self.list_widget)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        self.buttons.button(QDialogButtonBox.StandardButton.Ok)

        self.buttons.button(QDialogButtonBox.StandardButton.Cancel)

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.list_widget.currentRowChanged.connect(self._update_ok_state)
        self.list_widget.itemDoubleClicked.connect(self.accept)

    def _populate_list(self) -> None:
        """Populate available backups in the list widget."""
        self.list_widget.clear()

        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Scanning backup directory: %s", self.backup_dir)

            backups = self._get_backup_files()
            logger.debug("Backups discovered: %s", len(backups))

            single_backup_path = self.paths.get_db_backup_path()
            single_backup_exists = (
                single_backup_path.exists() and single_backup_path.stat().st_size > 0
            )

            if not backups and not single_backup_exists:
                self._show_no_backups_message()
            else:
                if single_backup_exists:
                    self._add_single_backup_item(single_backup_path)

                if backups:
                    self._populate_backup_list(backups)
                else:
                    if single_backup_exists and self.list_widget.count() > 0:
                        self.list_widget.setEnabled(True)
                        self.list_widget.setCurrentRow(0)
                        self._update_ok_state()

        except Exception as e:
            logger.error("Failed to list database backups: %s", e)
            self._show_error_message(self.tr("Failed to list database backups: {error}").format(error=str(e)))

    def _show_no_backups_message(self) -> None:
        """Display an empty-state entry when no backups exist."""
        item = self._create_list_item("no_backups")
        self.list_widget.addItem(item)
        self.list_widget.setEnabled(False)
        logger.info("No backups found")

    def _add_single_backup_item(self, backup_path: Path) -> None:
        """Insert the standalone ``links.db.bak`` backup with a highlighted row."""
        try:
            if backup_path.stat().st_size == 0:
                logger.warning("Empty backup file encountered: %s", backup_path.name)
                return

            stat = backup_path.stat()
            creation_time = datetime.datetime.fromtimestamp(stat.st_mtime)
            time_str = creation_time.strftime("%d.%m.%Y %H:%M")

            size_mb = backup_path.stat().st_size / (1024 * 1024)
            item = self._create_list_item(
                "single_backup",
                backup_name=backup_path.name,
                timestamp=time_str,
                size=f"{size_mb:.1f}",
                font_bold=True,
            )

            self.list_widget.addItem(item)

            logger.debug("Added single backup entry: %s", backup_path.name)

        except Exception as e:
            logger.warning("Failed to handle backup file %s: %s", backup_path.name, e)

    def _populate_backup_list(self, backups: list) -> None:
        """Append discovered backup files to the list."""
        for backup in backups:
            try:
                if backup.stat().st_size == 0:
                    logger.warning("Empty backup file encountered: %s", backup.name)
                    continue

                dt_str = self._parse_datetime(backup.name)
                size_mb = backup.stat().st_size / (1024 * 1024)

                if dt_str:
                    item = self._create_list_item(
                        "auto_backup_with_timestamp",
                        backup_name=backup.name,
                        timestamp=dt_str,
                        size=f"{size_mb:.1f}",
                    )
                else:
                    item = self._create_list_item(
                        "auto_backup_without_timestamp",
                        backup_name=backup.name,
                        size=f"{size_mb:.1f}",
                    )

                self.list_widget.addItem(item)
                logger.debug("Added backup entry: %s", backup.name)

            except Exception as e:
                logger.warning("Failed to process backup file %s: %s", backup.name, e)
                continue

        if self.list_widget.count() > 0:
            self.list_widget.setEnabled(True)
            self.list_widget.setCurrentRow(0)
        else:
            self._show_no_backups_message()

        self._update_ok_state()

    def _show_error_message(self, message: str) -> None:
        """Display an error row when the backup directory cannot be listed."""
        item = self._create_list_item(
            "error",
            details=message,
        )
        self.list_widget.addItem(item)
        self.list_widget.setEnabled(False)

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
        if not self.list_widget.isEnabled():
            return None

        row = self.list_widget.currentRow()
        if row < 0:
            return None

        try:
            single_backup_path = self.paths.get_db_backup_path()
            single_backup_exists = (
                single_backup_path.exists() and single_backup_path.stat().st_size > 0
            )

            backups = self._get_backup_files()
            valid_backups = [b for b in backups if b.stat().st_size > 0]

            if single_backup_exists:
                if row == 0:
                    logger.info(
                        "Single backup selected: %s", single_backup_path.name
                    )
                    return single_backup_path
                else:
                    adjusted_row = row - 1
                    if adjusted_row >= len(valid_backups):
                        logger.warning("Backup index is out of range: %s", row)
                        return None

                    selected = valid_backups[adjusted_row]
                    logger.info(
                        "Automatic backup selected: %s", selected.name
                    )
                    return selected
            else:
                if row >= len(valid_backups):
                    logger.warning("Backup index is out of range: %s", row)
                    return None

                selected = valid_backups[row]
                logger.info("Backup selected: %s", selected.name)
                return selected

        except Exception as e:
            logger.error("Failed to resolve selected backup: %s", e)
            return None

    def _get_backup_files(self) -> list[Path]:
        backups = []
        for path in self.backup_dir.glob("aite_bd_*.db"):
            if path.is_file():
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
            self.list_widget.isEnabled()
            and self.list_widget.currentRow() >= 0
            and self.list_widget.count() > 0
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

        # Обновляем существующие элементы списка
        if hasattr(self, "list_widget"):
            for index in range(self.list_widget.count()):
                item = self.list_widget.item(index)
                self._apply_item_translation(item)

    def _create_list_item(
        self, template_key: str, font_bold: bool = False, **format_kwargs: Any
    ) -> QListWidgetItem:
        sanitized_kwargs = self._sanitize_format_kwargs(format_kwargs)

        item = QListWidgetItem()
        item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "template_key": template_key,
                "format_kwargs": sanitized_kwargs,
                "font_bold": font_bold,
            },
        )
        self._apply_item_translation(item)
        return item

    def _apply_item_translation(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        template_key = data.get("template_key", "")
        format_kwargs = data.get("format_kwargs", {})

        try:
            template = _LIST_ITEM_TEMPLATES.get(template_key)
            if template is None:
                logger.warning("Unknown list item template key: %s", template_key)
                template = template_key
            if format_kwargs:
                template = template.format(**format_kwargs)
            item.setText(template)
        except Exception:
            fallback_template = template if template is not None else template_key
            if format_kwargs and isinstance(fallback_template, str):
                try:
                    item.setText(fallback_template.format(**format_kwargs))
                except Exception:
                    item.setText(str(fallback_template))
            else:
                item.setText(str(fallback_template))

        font_bold = bool(data.get("font_bold"))
        font = item.font()
        font.setBold(font_bold)
        item.setFont(font)

    @staticmethod
    def _sanitize_format_kwargs(format_kwargs: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in format_kwargs.items():
            if isinstance(value, str):
                sanitized[key] = value.replace("{", "{{").replace("}", "}}").strip()
            else:
                sanitized[key] = value
        return sanitized
