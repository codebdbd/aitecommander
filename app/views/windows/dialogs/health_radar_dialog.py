"""Dialog for checking broken local paths and relinking moved targets (Health Radar)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.controllers.ui.dialogs import DialogManager
from app.controllers.ui.undo.commands_links import (
    BatchDeleteLinksCmd,
    BatchRelinkCmd,
)
from app.models.types.link_type import LinkType
from app.models.workers.link_health_worker import (
    LinkHealthWorker,
    expand_local_path,
)
from app.utils.i18n.common import tr as tr_common
from app.utils.ui.qt.combo_helpers import PopupComboBox
from app.views.windows.dialogs.base_dialog import BaseDialog

if TYPE_CHECKING:
    from app.controllers.services.link_health_service import LinkHealthService
    from app.models import Database

logger = logging.getLogger(__name__)


class HealthRadarDialog(BaseDialog):
    """Dialog for scanning local links and batch-relinking moved files/folders."""

    COL_CHECK = 0
    COL_NAME = 1
    COL_TYPE = 2
    COL_CATEGORY = 3
    COL_OLD_PATH = 4
    COL_SUGGESTED = 5

    def __init__(
        self,
        service: LinkHealthService,
        db: Database,
        parent: QWidget | None = None,
    ) -> None:
        self.service = service
        self.db = db
        self._main_window = parent
        self._is_finished = False
        self._issues: list[dict[str, Any]] = []
        self._issues_by_id: dict[int, dict[str, Any]] = {}
        self._updating_selection = False

        super().__init__(parent)

        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.setMinimumWidth(680)
        self.setMinimumHeight(160)
        self.resize(860, 520)

        self._setup_ui()
        self._connect_signals()
        self.retranslateUi()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel(
            QCoreApplication.translate("HealthRadarDialog", "Checking local paths...")
        )
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Filter container
        self.filter_container = QWidget()
        filter_vbox = QVBoxLayout(self.filter_container)
        filter_vbox.setContentsMargins(0, 0, 0, 0)
        filter_vbox.setSpacing(6)

        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        self.search_le = QLineEdit()
        self.search_le.setClearButtonEnabled(True)
        self.search_le.textChanged.connect(self._on_filter_changed)
        search_layout.addWidget(self.search_le)
        filter_vbox.addLayout(search_layout)

        filters_row = QHBoxLayout()
        filters_row.setContentsMargins(0, 0, 0, 0)
        filters_row.setSpacing(8)

        self.status_filter_label = QLabel(
            QCoreApplication.translate("HealthRadarDialog", "Status:")
        )
        filters_row.addWidget(self.status_filter_label)

        self.status_filter_combo = PopupComboBox()
        self.status_filter_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.status_filter_combo.setMinimumWidth(140)
        self.status_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filters_row.addWidget(self.status_filter_combo, 1)

        self.sphere_filter_label = QLabel(
            QCoreApplication.translate("HealthRadarDialog", "Sphere:")
        )
        filters_row.addWidget(self.sphere_filter_label)

        self.sphere_filter_combo = PopupComboBox()
        self.sphere_filter_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.sphere_filter_combo.setMinimumWidth(120)
        self.sphere_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filters_row.addWidget(self.sphere_filter_combo, 1)

        filter_vbox.addLayout(filters_row)
        layout.addWidget(self.filter_container)
        self.filter_container.setVisible(False)

        # Table widget
        row_height = int(app_config.ui.get_row_height())
        self.table_widget = QTableWidget()
        self.table_widget.setObjectName("linksTable")
        self.table_widget.setColumnCount(6)
        self.table_widget.setHorizontalHeaderLabels(
            [
                "",
                QCoreApplication.translate("HealthRadarDialog", "Name"),
                QCoreApplication.translate("HealthRadarDialog", "Type"),
                QCoreApplication.translate("HealthRadarDialog", "Category"),
                QCoreApplication.translate("HealthRadarDialog", "Broken Path"),
                QCoreApplication.translate("HealthRadarDialog", "Suggested Fix / Status"),
            ]
        )
        self.table_widget.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table_widget.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
        )
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setShowGrid(False)
        self.table_widget.setWordWrap(False)
        self.table_widget.setCornerButtonEnabled(False)
        self.table_widget.horizontalHeader().setHighlightSections(False)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.horizontalHeader().setFixedHeight(row_height)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.verticalHeader().setDefaultSectionSize(row_height)
        self.table_widget.setVisible(False)

        self.table_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table_widget.itemChanged.connect(self._on_item_changed)
        self.table_widget.itemSelectionChanged.connect(self._update_buttons_state)

        header = self.table_widget.horizontalHeader()
        header.setMinimumSectionSize(36)
        header.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_CATEGORY, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.COL_OLD_PATH, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.COL_SUGGESTED, QHeaderView.ResizeMode.Stretch)

        self.table_widget.setColumnWidth(self.COL_CHECK, 40)
        self.table_widget.setColumnWidth(self.COL_NAME, 150)
        self.table_widget.setColumnWidth(self.COL_CATEGORY, 150)
        self.table_widget.setColumnWidth(self.COL_OLD_PATH, 220)

        self.header_checkbox = QCheckBox(header)
        self.header_checkbox.setStyleSheet(
            "QCheckBox { margin: 0; padding: 0; background: transparent; } "
            "QCheckBox::indicator { subcontrol-origin: padding; subcontrol-position: center; margin: 0; padding: 0; }"
        )
        self.header_checkbox.setTristate(False)
        self.header_checkbox.stateChanged.connect(self._on_header_checkbox_toggled)
        header.geometriesChanged.connect(self._update_header_checkbox_pos)
        self.table_widget.horizontalScrollBar().valueChanged.connect(
            self._update_header_checkbox_pos
        )
        self._update_header_checkbox_pos()

        layout.addWidget(self.table_widget, 1)

        # Bottom action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.locate_button = QPushButton()
        self.locate_button.setEnabled(False)
        self.locate_button.clicked.connect(self._on_locate_clicked)
        btn_layout.addWidget(self.locate_button)

        self.relink_button = QPushButton()
        self.relink_button.setEnabled(False)
        self.relink_button.clicked.connect(self._on_relink_selected)
        btn_layout.addWidget(self.relink_button)

        self.delete_button = QPushButton()
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._on_delete_selected)
        btn_layout.addWidget(self.delete_button)

        btn_layout.addStretch(1)

        self.rescan_button = QPushButton()
        self.rescan_button.setEnabled(False)
        self.rescan_button.clicked.connect(self._on_rescan_clicked)
        btn_layout.addWidget(self.rescan_button)

        self.cancel_button = QPushButton()
        self.cancel_button.clicked.connect(self._on_cancel_or_close)
        btn_layout.addWidget(self.cancel_button)

        layout.addLayout(btn_layout)

    def _connect_signals(self) -> None:
        self.service.progress.connect(self._on_progress)
        self.service.finished.connect(self._on_finished)
        self.service.error.connect(self._on_error)

    def retranslateUi(self) -> None:
        if not hasattr(self, "table_widget") or self.table_widget is None:
            return

        self.setWindowTitle(
            QCoreApplication.translate("HealthRadarDialog", "Local Path Health Radar")
        )
        self.search_le.setPlaceholderText(
            QCoreApplication.translate(
                "HealthRadarDialog", "Search by name, category, or path..."
            )
        )
        self.status_filter_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Status:")
        )
        self.sphere_filter_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Sphere:")
        )

        # Preserve status filter selection
        current_status = self.status_filter_combo.currentData() or "ALL"
        self.status_filter_combo.blockSignals(True)
        self.status_filter_combo.clear()
        self.status_filter_combo.addItem(
            QCoreApplication.translate("HealthRadarDialog", "All"), "ALL"
        )
        self.status_filter_combo.addItem(
            QCoreApplication.translate("HealthRadarDialog", "Auto-Fix Found"),
            LinkHealthWorker.STATUS_FIX_FOUND,
        )
        self.status_filter_combo.addItem(
            QCoreApplication.translate("HealthRadarDialog", "Not Found"),
            LinkHealthWorker.STATUS_NOT_FOUND,
        )
        self.status_filter_combo.addItem(
            QCoreApplication.translate("HealthRadarDialog", "Drive Offline"),
            LinkHealthWorker.STATUS_DRIVE_OFFLINE,
        )
        self.status_filter_combo.addItem(
            QCoreApplication.translate("HealthRadarDialog", "Duplicate Exists"),
            LinkHealthWorker.STATUS_DUPLICATE_EXISTS,
        )
        idx = self.status_filter_combo.findData(current_status)
        self.status_filter_combo.setCurrentIndex(max(0, idx))
        self.status_filter_combo.blockSignals(False)

        # Preserve sphere filter selection
        current_sphere = self.sphere_filter_combo.currentData() or "ALL"
        self._rebuild_sphere_combo(selected_data=current_sphere)

        self.table_widget.setHorizontalHeaderLabels(
            [
                "",
                QCoreApplication.translate("HealthRadarDialog", "Name"),
                QCoreApplication.translate("HealthRadarDialog", "Type"),
                QCoreApplication.translate("HealthRadarDialog", "Category"),
                QCoreApplication.translate("HealthRadarDialog", "Broken Path"),
                QCoreApplication.translate("HealthRadarDialog", "Suggested Fix / Status"),
            ]
        )
        self.header_checkbox.setToolTip(
            QCoreApplication.translate("HealthRadarDialog", "Select All / Deselect All")
        )

        self.locate_button.setText(
            QCoreApplication.translate("HealthRadarDialog", "Locate...")
        )
        self.locate_button.setToolTip(
            QCoreApplication.translate(
                "HealthRadarDialog",
                "Manually select the moved target on disk and auto-resolve sibling links",
            )
        )
        self.relink_button.setText(
            QCoreApplication.translate("HealthRadarDialog", "Relink Selected")
        )
        self.relink_button.setToolTip(
            QCoreApplication.translate(
                "HealthRadarDialog",
                "Update paths for checked links (supports Ctrl+Z Undo)",
            )
        )
        self.delete_button.setText(
            QCoreApplication.translate("HealthRadarDialog", "Delete Selected")
        )
        self.rescan_button.setText(
            QCoreApplication.translate("HealthRadarDialog", "Rescan")
        )
        self.cancel_button.setText(
            tr_common("Close") if self._is_finished else tr_common("Cancel")
        )

        if self._is_finished:
            self._refresh_table_rows()
            self._update_summary_status()

    def _update_header_checkbox_pos(self) -> None:
        if not hasattr(self, "header_checkbox") or not hasattr(self, "table_widget"):
            return
        header = self.table_widget.horizontalHeader()
        sec_pos = header.sectionViewportPosition(self.COL_CHECK)
        sec_size = header.sectionSize(self.COL_CHECK)
        cb_size = self.header_checkbox.sizeHint()
        x = sec_pos + max(0, (sec_size - cb_size.width()) // 2)
        y = max(0, (header.height() - cb_size.height()) // 2)
        self.header_checkbox.setGeometry(x, y, cb_size.width(), cb_size.height())

    def _rebuild_sphere_combo(self, selected_data: str = "ALL") -> None:
        self.sphere_filter_combo.blockSignals(True)
        self.sphere_filter_combo.clear()
        self.sphere_filter_combo.addItem(
            QCoreApplication.translate("HealthRadarDialog", "All"), "ALL"
        )
        spheres = sorted(
            {
                str(item.get("hierarchy", {}).get("sphere_name") or "")
                for item in self._issues
                if item.get("hierarchy", {}).get("sphere_name")
            }
        )
        for sp_name in spheres:
            self.sphere_filter_combo.addItem(sp_name, sp_name)
        idx = self.sphere_filter_combo.findData(selected_data)
        self.sphere_filter_combo.setCurrentIndex(max(0, idx))
        self.sphere_filter_combo.blockSignals(False)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            pct = int((current / total) * 100)
            self.progress_bar.setValue(pct)
        else:
            self.progress_bar.setValue(100)
        self.status_label.setText(message)

    def _on_finished(self, issues: list[dict[str, Any]]) -> None:
        self._is_finished = True
        self.progress_bar.setValue(100)
        self.cancel_button.setText(tr_common("Close"))
        self.rescan_button.setEnabled(True)

        self._issues = list(issues or [])
        self._issues_by_id = {int(item["id"]): item for item in self._issues}

        if not self._issues:
            self.filter_container.setVisible(False)
            self.table_widget.setVisible(False)
            self.status_label.setText(
                QCoreApplication.translate(
                    "HealthRadarDialog",
                    "All local paths are valid! No broken links found.",
                )
            )
            self._update_buttons_state()
            return

        self._rebuild_sphere_combo()
        self.filter_container.setVisible(True)
        self.table_widget.setVisible(True)
        self._update_header_checkbox_pos()
        self._populate_table()
        self._update_summary_status()
        self._update_buttons_state()

    def _on_error(self, error_msg: str) -> None:
        self._is_finished = True
        self.cancel_button.setText(tr_common("Close"))
        self.rescan_button.setEnabled(True)
        self.status_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Error: {0}").format(
                error_msg
            )
        )
        DialogManager.show_error(
            self,
            error_msg,
            QCoreApplication.translate("HealthRadarDialog", "Health Check Error"),
        )

    def _format_type_label(self, link_type: str) -> str:
        mapping = {
            LinkType.FILE.value: QCoreApplication.translate("HealthRadarDialog", "File"),
            LinkType.FOLDER.value: QCoreApplication.translate(
                "HealthRadarDialog", "Folder"
            ),
            LinkType.PROGRAM.value: QCoreApplication.translate(
                "HealthRadarDialog", "Program"
            ),
            LinkType.SCRIPT.value: QCoreApplication.translate(
                "HealthRadarDialog", "Script"
            ),
        }
        return mapping.get(link_type, link_type)

    def _format_status_cell(self, item: dict[str, Any]) -> tuple[str, QColor | None]:
        status = str(item.get("status") or "")
        suggested = str(item.get("suggested_url") or "")
        if status == LinkHealthWorker.STATUS_FIX_FOUND and suggested:
            return f"➔ {suggested}", QColor("#2ea043")
        if status == LinkHealthWorker.STATUS_DUPLICATE_EXISTS and suggested:
            return (
                QCoreApplication.translate(
                    "HealthRadarDialog",
                    "Duplicate target already in category: {0}",
                ).format(suggested),
                QColor("#d29922"),
            )
        if status == LinkHealthWorker.STATUS_DRIVE_OFFLINE:
            return (
                QCoreApplication.translate(
                    "HealthRadarDialog", "Drive or network share is offline"
                ),
                QColor("#8b949e"),
            )
        return (
            QCoreApplication.translate(
                "HealthRadarDialog", "File or folder not found"
            ),
            QColor("#f85149"),
        )

    def _populate_table(self) -> None:
        self._updating_selection = True
        try:
            self.table_widget.setRowCount(0)
            self.table_widget.setRowCount(len(self._issues))
            for row_idx, item in enumerate(self._issues):
                link_id = int(item["id"])
                status = str(item.get("status") or "")
                suggested = str(item.get("suggested_url") or "")

                # Column 0: Checkbox
                chk_item = QTableWidgetItem()
                chk_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                chk_item.setData(Qt.ItemDataRole.UserRole, link_id)
                is_fixable = (
                    status == LinkHealthWorker.STATUS_FIX_FOUND and bool(suggested)
                )
                chk_item.setCheckState(
                    Qt.CheckState.Checked if is_fixable else Qt.CheckState.Unchecked
                )
                self.table_widget.setItem(row_idx, self.COL_CHECK, chk_item)

                # Column 1: Name
                name_item = QTableWidgetItem(str(item.get("name") or ""))
                name_item.setData(Qt.ItemDataRole.UserRole, link_id)
                name_item.setToolTip(str(item.get("name") or ""))
                self.table_widget.setItem(row_idx, self.COL_NAME, name_item)

                # Column 2: Type
                type_label = self._format_type_label(str(item.get("type") or ""))
                type_item = QTableWidgetItem(type_label)
                self.table_widget.setItem(row_idx, self.COL_TYPE, type_item)

                # Column 3: Category Path
                cat_path = str(item.get("category_path") or "")
                cat_item = QTableWidgetItem(cat_path)
                cat_item.setToolTip(cat_path)
                self.table_widget.setItem(row_idx, self.COL_CATEGORY, cat_item)

                # Column 4: Broken Path
                old_url = str(item.get("url") or "")
                old_item = QTableWidgetItem(old_url)
                old_item.setToolTip(old_url)
                self.table_widget.setItem(row_idx, self.COL_OLD_PATH, old_item)

                # Column 5: Suggested Fix / Status
                status_text, color = self._format_status_cell(item)
                sug_item = QTableWidgetItem(status_text)
                sug_item.setToolTip(suggested or status_text)
                if color is not None:
                    sug_item.setForeground(color)
                self.table_widget.setItem(row_idx, self.COL_SUGGESTED, sug_item)
        finally:
            self._updating_selection = False

        self._apply_filters()
        self._sync_header_checkbox()

    def _refresh_table_rows(self) -> None:
        """Refresh text and status colors on existing rows without losing check states."""
        self._updating_selection = True
        try:
            for row_idx in range(self.table_widget.rowCount()):
                chk_item = self.table_widget.item(row_idx, self.COL_CHECK)
                if chk_item is None:
                    continue
                link_id = int(chk_item.data(Qt.ItemDataRole.UserRole) or 0)
                item = self._issues_by_id.get(link_id)
                if not item:
                    continue
                type_item = self.table_widget.item(row_idx, self.COL_TYPE)
                if type_item is not None:
                    type_item.setText(self._format_type_label(str(item.get("type") or "")))

                sug_item = self.table_widget.item(row_idx, self.COL_SUGGESTED)
                if sug_item is not None:
                    status_text, color = self._format_status_cell(item)
                    sug_item.setText(status_text)
                    sug_item.setToolTip(str(item.get("suggested_url") or status_text))
                    if color is not None:
                        sug_item.setForeground(color)
        finally:
            self._updating_selection = False

    def _on_filter_changed(self) -> None:
        self._apply_filters()
        self._sync_header_checkbox()
        self._update_buttons_state()

    def _apply_filters(self) -> None:
        query = self.search_le.text().strip().lower()
        status_filter = str(self.status_filter_combo.currentData() or "ALL")
        sphere_filter = str(self.sphere_filter_combo.currentData() or "ALL")

        for row_idx in range(self.table_widget.rowCount()):
            chk_item = self.table_widget.item(row_idx, self.COL_CHECK)
            if chk_item is None:
                continue
            link_id = int(chk_item.data(Qt.ItemDataRole.UserRole) or 0)
            item = self._issues_by_id.get(link_id)
            if not item:
                self.table_widget.setRowHidden(row_idx, True)
                continue

            visible = True
            if status_filter != "ALL" and item.get("status") != status_filter:
                visible = False
            if visible and sphere_filter != "ALL":
                sp_name = str(item.get("hierarchy", {}).get("sphere_name") or "")
                if sp_name != sphere_filter:
                    visible = False
            if visible and query:
                haystack = " ".join(
                    [
                        str(item.get("name") or ""),
                        str(item.get("url") or ""),
                        str(item.get("suggested_url") or ""),
                        str(item.get("category_path") or ""),
                    ]
                ).lower()
                if query not in haystack:
                    visible = False

            self.table_widget.setRowHidden(row_idx, not visible)

    def _on_header_checkbox_toggled(self, state: int) -> None:
        if self._updating_selection:
            return
        target_state = (
            Qt.CheckState.Checked
            if state == Qt.CheckState.Checked.value
            else Qt.CheckState.Unchecked
        )
        self._updating_selection = True
        try:
            for row_idx in range(self.table_widget.rowCount()):
                if self.table_widget.isRowHidden(row_idx):
                    continue
                chk_item = self.table_widget.item(row_idx, self.COL_CHECK)
                if chk_item is not None:
                    chk_item.setCheckState(target_state)
        finally:
            self._updating_selection = False
        self._update_buttons_state()

    def _sync_header_checkbox(self) -> None:
        if self._updating_selection:
            return
        visible_count = 0
        checked_count = 0
        for row_idx in range(self.table_widget.rowCount()):
            if self.table_widget.isRowHidden(row_idx):
                continue
            chk_item = self.table_widget.item(row_idx, self.COL_CHECK)
            if chk_item is None:
                continue
            visible_count += 1
            if chk_item.checkState() == Qt.CheckState.Checked:
                checked_count += 1

        self.header_checkbox.blockSignals(True)
        self.header_checkbox.setChecked(
            visible_count > 0 and checked_count == visible_count
        )
        self.header_checkbox.blockSignals(False)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_selection:
            return
        if item.column() == self.COL_CHECK:
            self._sync_header_checkbox()
            self._update_buttons_state()

    def _get_checked_items(self) -> list[dict[str, Any]]:
        checked: list[dict[str, Any]] = []
        for row_idx in range(self.table_widget.rowCount()):
            if self.table_widget.isRowHidden(row_idx):
                continue
            chk_item = self.table_widget.item(row_idx, self.COL_CHECK)
            if chk_item is not None and chk_item.checkState() == Qt.CheckState.Checked:
                link_id = int(chk_item.data(Qt.ItemDataRole.UserRole) or 0)
                issue = self._issues_by_id.get(link_id)
                if issue is not None:
                    checked.append(issue)
        return checked

    def _get_current_row_issue(self) -> dict[str, Any] | None:
        row_idx = self.table_widget.currentRow()
        if row_idx < 0:
            checked = self._get_checked_items()
            return checked[0] if len(checked) == 1 else None
        chk_item = self.table_widget.item(row_idx, self.COL_CHECK)
        if chk_item is None:
            return None
        link_id = int(chk_item.data(Qt.ItemDataRole.UserRole) or 0)
        return self._issues_by_id.get(link_id)

    def _update_summary_status(self) -> None:
        total_issues = len(self._issues)
        fix_count = sum(
            1
            for item in self._issues
            if item.get("status") == LinkHealthWorker.STATUS_FIX_FOUND
            and item.get("suggested_url")
        )
        self.status_label.setText(
            QCoreApplication.translate(
                "HealthRadarDialog",
                "Found {0} broken local paths ({1} with automatic fix ready).",
            ).format(total_issues, fix_count)
        )

    def _update_buttons_state(self) -> None:
        if not self._is_finished:
            self.locate_button.setEnabled(False)
            self.relink_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return

        checked = self._get_checked_items()
        relinkable = [
            item
            for item in checked
            if item.get("status") == LinkHealthWorker.STATUS_FIX_FOUND
            and item.get("suggested_url")
        ]
        self.locate_button.setEnabled(self._get_current_row_issue() is not None)
        self.relink_button.setEnabled(len(relinkable) > 0)
        self.delete_button.setEnabled(len(checked) > 0)

    def _on_item_double_clicked(self, _item: QTableWidgetItem) -> None:
        self._on_locate_clicked()

    def _on_locate_clicked(self) -> None:
        issue = self._get_current_row_issue()
        if issue is None:
            return

        old_url = str(issue.get("url") or "")
        link_type = str(issue.get("type") or LinkType.FILE.value)

        start_dir = ""
        expanded = expand_local_path(old_url)
        if expanded:
            cur = Path(os.path.normpath(expanded)).parent
            while cur != cur.parent:
                try:
                    if cur.is_dir():
                        start_dir = str(cur)
                        break
                except OSError:
                    pass
                cur = cur.parent

        if link_type == LinkType.FOLDER.value:
            chosen = QFileDialog.getExistingDirectory(
                self,
                QCoreApplication.translate("HealthRadarDialog", "Locate Moved Folder"),
                start_dir,
            )
        else:
            chosen, _ = QFileDialog.getOpenFileName(
                self,
                QCoreApplication.translate("HealthRadarDialog", "Locate Moved File"),
                start_dir,
            )

        if not chosen:
            return

        chosen_norm = os.path.normpath(chosen)
        self.apply_manual_location(int(issue["id"]), chosen_norm)

    def apply_manual_location(self, link_id: int, chosen_path: str) -> list[int]:
        """Set the target path for ``link_id`` and propagate folder relocation to siblings."""
        issue = self._issues_by_id.get(int(link_id))
        if issue is None:
            return []

        old_url = str(issue.get("url") or "")
        issue["suggested_url"] = chosen_path
        issue["status"] = LinkHealthWorker.STATUS_FIX_FOUND

        propagated_ids = self.service.propagate_relink(
            self._issues,
            old_url,
            chosen_path,
        )
        all_updated = {int(link_id)} | set(propagated_ids)

        self._updating_selection = True
        try:
            for row_idx in range(self.table_widget.rowCount()):
                chk_item = self.table_widget.item(row_idx, self.COL_CHECK)
                if chk_item is None:
                    continue
                rid = int(chk_item.data(Qt.ItemDataRole.UserRole) or 0)
                if rid in all_updated:
                    r_issue = self._issues_by_id.get(rid)
                    if (
                        r_issue
                        and r_issue.get("status") == LinkHealthWorker.STATUS_FIX_FOUND
                    ):
                        chk_item.setCheckState(Qt.CheckState.Checked)
        finally:
            self._updating_selection = False

        self._refresh_table_rows()
        self._sync_header_checkbox()
        self._update_summary_status()
        self._update_buttons_state()
        return sorted(all_updated)

    def _on_relink_selected(self) -> None:
        checked = self._get_checked_items()
        relinkable = [
            item
            for item in checked
            if item.get("status") == LinkHealthWorker.STATUS_FIX_FOUND
            and item.get("suggested_url")
        ]
        if not relinkable:
            return

        old_links: list[dict[str, Any]] = []
        new_links: list[dict[str, Any]] = []
        fixed_ids: set[int] = set()

        for item in relinkable:
            link_id = int(item["id"])
            raw_link_data = dict(item.get("link_data") or {})
            raw_link_data["id"] = link_id
            old_links.append(dict(raw_link_data))

            updated_data = dict(raw_link_data)
            updated_data["url"] = str(item["suggested_url"])
            new_links.append(updated_data)
            fixed_ids.add(link_id)

        cmd = BatchRelinkCmd(old_links, new_links, self._main_window, db=self.db)
        undo_stack = getattr(self._main_window, "undo_stack", None)
        if undo_stack is not None:
            undo_stack.push(cmd)
        else:
            cmd.redo()

        self._remove_issue_ids(fixed_ids)
        self.status_label.setText(
            QCoreApplication.translate(
                "HealthRadarDialog",
                "Relinked {0} paths (press Ctrl+Z in main window to undo).",
            ).format(len(fixed_ids))
        )

    def _on_delete_selected(self) -> None:
        checked = self._get_checked_items()
        if not checked:
            return

        confirmed = DialogManager.ask_confirmation(
            self,
            QCoreApplication.translate(
                "HealthRadarDialog",
                "Delete {0} selected links? (You can undo this with Ctrl+Z)",
            ).format(len(checked)),
            QCoreApplication.translate("HealthRadarDialog", "Delete Links"),
        )
        if not confirmed:
            return

        links_to_delete: list[dict[str, Any]] = []
        deleted_ids: set[int] = set()
        for item in checked:
            link_id = int(item["id"])
            raw_link_data = dict(item.get("link_data") or {})
            raw_link_data["id"] = link_id
            links_to_delete.append(raw_link_data)
            deleted_ids.add(link_id)

        cmd = BatchDeleteLinksCmd(links_to_delete, self._main_window)
        if getattr(cmd, "db", None) is None:
            cmd.db = self.db
        undo_stack = getattr(self._main_window, "undo_stack", None)
        if undo_stack is not None:
            undo_stack.push(cmd)
        else:
            cmd.redo()

        self._remove_issue_ids(deleted_ids)
        self.status_label.setText(
            QCoreApplication.translate(
                "HealthRadarDialog",
                "Deleted {0} links (press Ctrl+Z in main window to undo).",
            ).format(len(deleted_ids))
        )

    def _remove_issue_ids(self, removed_ids: set[int]) -> None:
        self._issues = [
            item for item in self._issues if int(item["id"]) not in removed_ids
        ]
        for rid in removed_ids:
            self._issues_by_id.pop(rid, None)

        self._populate_table()
        self._update_buttons_state()

    def _on_rescan_clicked(self) -> None:
        if self.service.is_running():
            return
        self._is_finished = False
        self._issues.clear()
        self._issues_by_id.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Checking local paths...")
        )
        self.cancel_button.setText(tr_common("Cancel"))
        self.rescan_button.setEnabled(False)
        self._update_buttons_state()
        self.service.start_check()

    def _on_cancel_or_close(self) -> None:
        if not self._is_finished and self.service.is_running():
            self.service.cancel_check()
        self.close()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.service.is_running():
            self.service.cancel_check()
        self.service.set_dialog(None)
        super().closeEvent(event)
