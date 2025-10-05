"""Dialog to restore the database from a backup."""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QDialogButtonBox, QListWidget, QListWidgetItem, QVBoxLayout

from app.config_data import app_config
from i18n.locale_utils import format_datetime, format_decimal

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


def _tr(text: str) -> str:
    return QCoreApplication.translate("RestoreDbDialog", text)


def _arg(template: str, *args: str) -> str:
    result = template
    for idx, value in enumerate(args, 1):
        result = result.replace(f"%{idx}", value)
    return result


@dataclass
class BackupMeta:
    kind: str
    path: Optional[Path] = None
    timestamp: Optional[datetime.datetime] = None
    size_bytes: int = 0
    message: Optional[str] = None


class RestoreDbDialog(BaseDialog):
    """Dialog that allows restoring the database from backups."""

    def __init__(self, backup_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)

        self.resize(500, 300)
        self.setModal(True)

        self.paths = app_config.paths
        self.backup_dir = backup_dir or self.paths.get_backups_dir()
        self.selected_backup: Optional[Path] = None

        self._init_ui()
        self._load_backups()
        
        # Connect to language change signal
        from i18n.language_service import LanguageService
        LanguageService.instance().languageChanged.connect(self._on_language_changed)
        self.destroyed.connect(self._disconnect_language_service)
        
        self.retranslateUi()
    
    def _on_language_changed(self, _lang_code: str) -> None:
        self.retranslateUi()
    
    def _disconnect_language_service(self) -> None:
        try:
            from i18n.language_service import LanguageService
            LanguageService.instance().languageChanged.disconnect(self._on_language_changed)
        except Exception:
            pass

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.list_widget)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.list_widget.currentRowChanged.connect(self._update_ok_state)
        self.list_widget.itemDoubleClicked.connect(self.accept)

    def _load_backups(self) -> None:
        self.list_widget.clear()
        self.list_widget.setEnabled(True)

        added = 0

        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.error("Failed to create backups directory: %s", exc)
            self._show_placeholder("error", message=str(exc))
            self._update_ok_state()
            return

        logger.debug("Searching for backups in: %s", self.backup_dir)

        backups = sorted(self.backup_dir.glob("links_*.db"), reverse=True)
        logger.debug("Found %s automatic backups", len(backups))

        single_backup_path = self.paths.get_db_backup_path()
        single_exists = single_backup_path.exists() and single_backup_path.stat().st_size > 0

        if single_exists:
            if self._add_backup_item(single_backup_path, kind="single", highlight=True):
                added += 1

        for backup in backups:
            if backup == single_backup_path:
                continue
            try:
                if backup.stat().st_size == 0:
                    logger.warning("Empty backup file skipped: %s", backup.name)
                    continue
                if self._add_backup_item(backup, kind="auto"):
                    added += 1
            except Exception as exc:
                logger.warning("Failed to process backup %s: %s", backup.name, exc)

        if added == 0:
            logger.info("No backups available")
            self._show_placeholder("placeholder")
        else:
            self.list_widget.setCurrentRow(0)

        self._update_ok_state()

    def _add_backup_item(self, path: Path, *, kind: str, highlight: bool = False) -> bool:
        size_bytes = path.stat().st_size
        if size_bytes == 0:
            return False

        timestamp = self._parse_timestamp(path.name)
        if timestamp is None:
            timestamp = datetime.datetime.fromtimestamp(path.stat().st_mtime)

        meta = BackupMeta(kind=kind, path=path, timestamp=timestamp, size_bytes=size_bytes)

        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, meta)

        if highlight:
            font = item.font()
            font.setBold(True)
            item.setFont(font)

        self.list_widget.addItem(item)
        self._update_item_text(item)
        return True

    def _show_placeholder(self, kind: str, message: str | None = None) -> None:
        self.list_widget.clear()
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(Qt.ItemDataRole.UserRole, BackupMeta(kind=kind, message=message))
        self.list_widget.addItem(item)
        self.list_widget.setEnabled(False)
        self._update_item_text(item)

    def _parse_timestamp(self, filename: str) -> Optional[datetime.datetime]:
        base = filename.replace("links_", "").replace(".db", "")
        for pattern in ("%Y%m%d_%H%M%S_%f", "%Y%m%d_%H%M%S", "%Y-%m-%d_%H-%M-%S"):
            try:
                return datetime.datetime.strptime(base, pattern)
            except ValueError:
                continue
        return None

    def _update_item_text(self, item: QListWidgetItem) -> None:
        meta = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(meta, BackupMeta):
            return

        if meta.kind in {"single", "auto"} and meta.path is not None:
            timestamp_text = (
                format_datetime(meta.timestamp)
                if isinstance(meta.timestamp, datetime.datetime)
                else _tr("Unknown time")
            )
            size_mb = meta.size_bytes / (1024 * 1024) if meta.size_bytes else 0
            size_text = format_decimal(size_mb, precision=1)
            if meta.kind == "single":
                text = _arg(
                    _tr("%1 — created before current database (%2, %3 MB)"),
                    meta.path.name,
                    timestamp_text,
                    size_text,
                )
            else:
                text = _arg(
                    _tr("%1 — %2 (%3 MB)"),
                    meta.path.name,
                    timestamp_text,
                    size_text,
                )
            item.setText(text)
        elif meta.kind == "placeholder":
            item.setText(_tr("No backups found"))
        elif meta.kind == "error":
            if meta.message:
                item.setText(_arg(_tr("Failed to scan backups: %1"), meta.message))
            else:
                item.setText(_tr("Failed to scan backups"))

    def _refresh_items(self) -> None:
        for index in range(self.list_widget.count()):
            self._update_item_text(self.list_widget.item(index))

    def retranslateUi(self) -> None:
        self.setWindowTitle(_tr("Restore Database from Backup"))
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if ok_btn is not None:
            ok_btn.setText(_tr("Restore"))
        if cancel_btn is not None:
            cancel_btn.setText(_tr("Cancel"))
        self.list_widget.setAccessibleName(_tr("Backups list"))
        self._refresh_items()

    def get_selected_backup(self) -> Optional[Path]:
        if not self.list_widget.isEnabled():
            return None
        item = self.list_widget.currentItem()
        if item is None:
            return None
        meta = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(meta, BackupMeta):
            return meta.path
        return None

    def _update_ok_state(self) -> None:
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setEnabled(self.get_selected_backup() is not None)

    def accept(self) -> None:
        selected_backup = self.get_selected_backup()
        if not selected_backup:
            self.show_warning(
                _tr("No backup selected."),
                _tr("Backup selection required"),
                informative_text=_tr(
                    "Choose a file from the list and press \"Restore\". "
                    "If the list is empty, check the backups directory."
                ),
            )
            return

        size_mb = selected_backup.stat().st_size / (1024 * 1024)
        reply = self.ask_confirmation(
            _tr("Restore the database from the selected backup?"),
            _tr("Database restoration"),
            informative_text=_tr(
                "The current database will be completely replaced by the selected backup. "
                "This action cannot be undone. Create a backup first if necessary."
            ),
            details=_arg(
                _tr("Path: %1\nName: %2\nSize: %3 MB"),
                str(selected_backup),
                selected_backup.name,
                format_decimal(size_mb, precision=1),
            ),
        )
        if reply:
            self.selected_backup = selected_backup
            super().accept()

    def get_result(self) -> Optional[Path]:
        return self.selected_backup
