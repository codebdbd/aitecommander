"""Dialog for cleaning up unlinked (orphaned) icons."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.i18n.common import tr as tr_common
from app.views.windows.dialogs.base_dialog import BaseDialog

if TYPE_CHECKING:
    from app.services.icon_reference_service import IconReferenceService

logger = logging.getLogger(__name__)


class CleanIconsDialog(BaseDialog):
    """Dialog for inspecting and deleting unlinked icon files."""

    def __init__(self, service: IconReferenceService, parent: QWidget | None = None) -> None:
        self.service = service
        self._stats: dict = {}
        self._is_cleaned = False

        self.title_label: QLabel | None = None
        self.stats_label: QLabel | None = None
        self.status_label: QLabel | None = None
        self.age_checkbox: QCheckBox | None = None
        self.clean_button: QPushButton | None = None
        self.close_button: QPushButton | None = None

        super().__init__(parent)

        self.setModal(True)
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)

        self._refresh_stats()
        self._setup_ui()
        self.retranslateUi()

    def _refresh_stats(self) -> None:
        try:
            self._stats = self.service.get_stats()
        except Exception as e:
            logger.error("Failed to retrieve icon stats: %s", e)
            self._stats = {
                "total_files": 0,
                "total_size_mb": 0.0,
                "orphaned_count": 0,
                "orphaned_size_mb": 0.0,
            }

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.title_label = QLabel(self)
        title_font = self.title_label.font()
        title_font.setPointSize(title_font.pointSize() + 2)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        self.stats_label = QLabel(self)
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)

        self.age_checkbox = QCheckBox(self)
        self.age_checkbox.setChecked(False)
        layout.addWidget(self.age_checkbox)

        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # Buttons block
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(8)
        buttons_layout.addStretch(1)

        self.clean_button = QPushButton(self)
        self.clean_button.clicked.connect(self._on_clean_clicked)
        buttons_layout.addWidget(self.clean_button)

        self.close_button = QPushButton(self)
        self.close_button.clicked.connect(self._on_close_clicked)
        buttons_layout.addWidget(self.close_button)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

        self._update_button_visibility()

    def _update_button_visibility(self) -> None:
        orphans = self._stats.get("orphaned_count", 0)
        if orphans > 0 and not self._is_cleaned:
            if self.clean_button:
                self.clean_button.setVisible(True)
                self.clean_button.setEnabled(True)
            if self.age_checkbox:
                self.age_checkbox.setVisible(True)
        else:
            if self.clean_button:
                self.clean_button.setVisible(False)
            if self.age_checkbox:
                self.age_checkbox.setVisible(False)

    def retranslateUi(self) -> None:
        """Update localized texts without any trailing ellipses."""
        self.setWindowTitle(self.tr("Clean Icons"))
        if self.title_label:
            self.title_label.setText(self.tr("Clean Icons"))

        if self.age_checkbox:
            self.age_checkbox.setText(self.tr("Delete only files older than 24 hours"))

        orphans = self._stats.get("orphaned_count", 0)
        orphans_mb = self._stats.get("orphaned_size_mb", 0.0)
        total_files = self._stats.get("total_files", 0)
        total_mb = self._stats.get("total_size_mb", 0.0)

        if self.stats_label:
            if self._is_cleaned:
                self.stats_label.setText(self.tr("Icons cleanup completed successfully."))
            elif orphans > 0:
                stats_text = (
                    self.tr("Total icons in folder: {0} ({1} MB)").format(total_files, total_mb)
                    + "\n"
                    + self.tr("Unlinked icons found: {0} ({1} MB)").format(orphans, orphans_mb)
                    + "\n\n"
                    + self.tr("Do you want to permanently delete these unlinked icon files?")
                )
                self.stats_label.setText(stats_text)
            else:
                self.stats_label.setText(
                    self.tr("All icons in the folder are in use.")
                    + "\n"
                    + self.tr("No unlinked icons found.")
                )

        if self.clean_button:
            self.clean_button.setText(self.tr("Clean Icons"))

        if self.close_button:
            if orphans > 0 and not self._is_cleaned:
                self.close_button.setText(tr_common("Cancel"))
            else:
                self.close_button.setText(tr_common("Close"))

    def _on_clean_clicked(self) -> None:
        """Execute cleanup with wait cursor."""
        min_age = 24 if (self.age_checkbox and self.age_checkbox.isChecked()) else 0
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.service.cleanup_orphaned_icons(dry_run=False, min_age_hours=min_age)
            logger.info("Cleaned orphaned icons: %s", result)
        except Exception as e:
            logger.error("Error cleaning orphaned icons: %s", e)
            result = {"deleted": 0, "kept": 0, "errors": 1}
        finally:
            QApplication.restoreOverrideCursor()

        self._is_cleaned = True
        self._refresh_stats()
        self._update_button_visibility()

        deleted = result.get("deleted", 0)
        errors = result.get("errors", 0)

        if self.status_label:
            if errors > 0:
                msg = self.tr("Deleted: {0}, errors: {1}").format(deleted, errors)
            else:
                msg = self.tr("Deleted: {0} icon file(s)").format(deleted)
            self.status_label.setText(msg)
            self.status_label.show()

        self.retranslateUi()

    def _on_close_clicked(self) -> None:
        if self._is_cleaned:
            self.accept()
        else:
            self.reject()
