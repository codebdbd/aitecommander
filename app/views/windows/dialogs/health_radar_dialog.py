"""Dialog for checking broken local paths and relinking moved targets."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
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
from app.services.theme_registry import theme_registry
from app.utils.i18n.common import tr as tr_common
from app.utils.ui.icon.path_service import get_current_theme
from app.utils.ui.qt.combo_helpers import PopupComboBox
from app.views.windows.dialogs.base_dialog import BaseDialog
from app.views.windows.dialogs.link_dialog.icon_utils import (
    get_cached_icon,
    get_cached_icon_with_fallback,
)

if TYPE_CHECKING:
    from app.controllers.services.link_health_service import LinkHealthService
    from app.models import Database

logger = logging.getLogger(__name__)


class HealthRadarDialog(BaseDialog):
    """Dialog for scanning local links and batch-relinking moved files/folders."""

    COL_CHECK = 0
    COL_NAME = 1
    COL_OLD_PATH = 2
    COL_SUGGESTED = 3

    # Backwards-compatibility column aliases
    COL_TYPE = COL_NAME
    COL_CATEGORY = COL_NAME

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

        # Category hierarchy tracking for cascade filters
        self._hierarchy: dict[str, dict[str, list[str]]] = {}
        self._sphere_icon_paths: dict[str, str] = {}
        self._section_icon_paths: dict[tuple[str, str], str] = {}
        self._category_icon_paths: dict[tuple[str, str, str], str] = {}

        super().__init__(parent)

        self.setModal(True)
        # Start in fixed compact progress mode (matches BadUrlCleanupDialog)
        self.setFixedSize(500, 140)

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

        # Filter container (hidden during scan, shown on results if issues found)
        self.filter_container = QWidget()
        filter_vbox = QVBoxLayout(self.filter_container)
        filter_vbox.setContentsMargins(0, 0, 0, 0)
        filter_vbox.setSpacing(6)

        # Row 1: Search bar
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(8)
        self.search_le = QLineEdit()
        self.search_le.setClearButtonEnabled(True)
        self.search_le.textChanged.connect(self._on_filter_changed)
        search_layout.addWidget(self.search_le)
        filter_vbox.addLayout(search_layout)

        # Row 2: Cascade dropdowns (Status, Sphere, Section, Category)
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
        self.status_filter_combo.setMinimumWidth(120)
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
        self.sphere_filter_combo.setMinimumWidth(90)
        self.sphere_filter_combo.currentIndexChanged.connect(self._on_sphere_changed)
        filters_row.addWidget(self.sphere_filter_combo, 1)

        self.section_filter_label = QLabel(
            QCoreApplication.translate("HealthRadarDialog", "Section:")
        )
        filters_row.addWidget(self.section_filter_label)

        self.section_filter_combo = PopupComboBox()
        self.section_filter_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.section_filter_combo.setMinimumWidth(90)
        self.section_filter_combo.currentIndexChanged.connect(self._on_section_changed)
        filters_row.addWidget(self.section_filter_combo, 1)

        self.category_filter_label = QLabel(
            QCoreApplication.translate("HealthRadarDialog", "Category:")
        )
        filters_row.addWidget(self.category_filter_label)

        self.category_filter_combo = PopupComboBox()
        self.category_filter_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.category_filter_combo.setMinimumWidth(90)
        self.category_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filters_row.addWidget(self.category_filter_combo, 1)

        filter_vbox.addLayout(filters_row)
        layout.addWidget(self.filter_container)
        self.filter_container.setVisible(False)

        # Table widget (4 columns matching BadUrlCleanupDialog)
        row_height = int(app_config.ui.get_row_height())
        self.table_widget = QTableWidget()
        self.table_widget.setObjectName("linksTable")
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(
            [
                "",
                QCoreApplication.translate("HealthRadarDialog", "Name"),
                QCoreApplication.translate("HealthRadarDialog", "Broken Path"),
                QCoreApplication.translate(
                    "HealthRadarDialog", "Suggested Fix / Status"
                ),
            ]
        )
        self.table_widget.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table_widget.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setShowGrid(False)
        self.table_widget.setWordWrap(False)
        self.table_widget.setCornerButtonEnabled(False)
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.table_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table_widget.itemChanged.connect(self._on_item_changed)
        self.table_widget.itemSelectionChanged.connect(self._update_buttons_state)

        header = self.table_widget.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(True)
        header.setFixedHeight(row_height)
        header.setMinimumSectionSize(36)
        header.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(
            self.COL_OLD_PATH, QHeaderView.ResizeMode.Interactive
        )
        header.setSectionResizeMode(self.COL_SUGGESTED, QHeaderView.ResizeMode.Stretch)

        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.verticalHeader().setDefaultSectionSize(row_height)
        self.table_widget.setVisible(False)

        self.table_widget.setColumnWidth(self.COL_CHECK, 40)
        self.table_widget.setColumnWidth(self.COL_NAME, 200)
        self.table_widget.setColumnWidth(self.COL_OLD_PATH, 280)

        # Tristate header checkbox inside column 0
        self.header_checkbox = QCheckBox(header)
        self.header_checkbox.setStyleSheet(
            "QCheckBox { margin: 0; padding: 0; background: transparent; } "
            "QCheckBox::indicator { subcontrol-origin: padding; subcontrol-position: center; margin: 0; padding: 0; }"
        )
        self.header_checkbox.setTristate(True)
        self.header_checkbox.clicked.connect(self._on_header_checkbox_clicked)
        header.sectionClicked.connect(self._on_header_section_clicked)
        header.geometriesChanged.connect(self._update_header_checkbox_pos)
        self.table_widget.horizontalScrollBar().valueChanged.connect(
            self._update_header_checkbox_pos
        )
        self._update_header_checkbox_pos()

        layout.addWidget(self.table_widget, 1)

        # Bottom action row
        self.button_box = QWidget()
        btn_layout = QHBoxLayout(self.button_box)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        self.selection_info_label = QLabel("")
        self.selection_info_label.setVisible(False)
        btn_layout.addWidget(self.selection_info_label)

        btn_layout.addStretch(1)

        min_btn_w = app_config.ui.get_fixed_button_width()

        self.locate_button = QPushButton()
        self.locate_button.setEnabled(False)
        self.locate_button.setVisible(False)
        self.locate_button.clicked.connect(self._on_locate_clicked)
        self.adjust_button_width(self.locate_button, min_width=min_btn_w)
        btn_layout.addWidget(self.locate_button)

        self.relink_button = QPushButton()
        self.relink_button.setEnabled(False)
        self.relink_button.setVisible(False)
        self.relink_button.clicked.connect(self._on_relink_selected)
        self.adjust_button_width(self.relink_button, min_width=min_btn_w)
        btn_layout.addWidget(self.relink_button)

        self.delete_button = QPushButton()
        self.delete_button.setEnabled(False)
        self.delete_button.setVisible(False)
        self.delete_button.clicked.connect(self._on_delete_selected)
        self.adjust_button_width(self.delete_button, min_width=min_btn_w)
        btn_layout.addWidget(self.delete_button)

        self.rescan_button = QPushButton()
        self.rescan_button.setEnabled(False)
        self.rescan_button.setVisible(False)
        self.rescan_button.clicked.connect(self._on_rescan_clicked)
        self.adjust_button_width(self.rescan_button, min_width=min_btn_w)
        btn_layout.addWidget(self.rescan_button)

        self.cancel_button = QPushButton(tr_common("Cancel"))
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.adjust_button_width(self.cancel_button, min_width=min_btn_w)
        btn_layout.addWidget(self.cancel_button)

        self.close_button = QPushButton(QCoreApplication.translate("HealthRadarDialog", "Close"))
        self.close_button.setVisible(False)
        self.close_button.clicked.connect(self.accept)
        self.adjust_button_width(self.close_button, min_width=min_btn_w)
        btn_layout.addWidget(self.close_button)

        layout.addWidget(self.button_box)

    def _connect_signals(self) -> None:
        self.service.progress.connect(self._on_progress)
        self.service.finished.connect(self._on_finished)
        self.service.error.connect(self._on_error)

    def retranslateUi(self) -> None:
        if not hasattr(self, "table_widget") or self.table_widget is None:
            return

        self.setWindowTitle(
            QCoreApplication.translate("HealthRadarDialog", "Check Local Paths")
        )
        self.search_le.setPlaceholderText(
            QCoreApplication.translate("HealthRadarDialog", "Search by name or path...")
        )
        self.status_filter_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Status:")
        )
        self.sphere_filter_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Sphere:")
        )
        self.section_filter_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Section:")
        )
        self.category_filter_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Category:")
        )

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

        self.table_widget.setHorizontalHeaderLabels(
            [
                "",
                QCoreApplication.translate("HealthRadarDialog", "Name"),
                QCoreApplication.translate("HealthRadarDialog", "Broken Path"),
                QCoreApplication.translate(
                    "HealthRadarDialog", "Suggested Fix / Status"
                ),
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
        self.rescan_button.setText(
            QCoreApplication.translate("HealthRadarDialog", "Rescan")
        )
        self.cancel_button.setText(tr_common("Cancel"))
        self.close_button.setText(QCoreApplication.translate("HealthRadarDialog", "Close"))

        if self._is_finished:
            self._populate_filter_combos()
            self._refresh_table_rows()
            self._update_buttons_state()

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

    def _on_header_section_clicked(self, logical_index: int) -> None:
        if logical_index == self.COL_CHECK:
            self._on_header_checkbox_clicked()

    def _on_header_checkbox_clicked(self) -> None:
        has_unchecked = False
        has_visible = False
        for row in range(self.table_widget.rowCount()):
            if not self.table_widget.isRowHidden(row):
                has_visible = True
                item = self.table_widget.item(row, self.COL_CHECK)
                if item and item.checkState() != Qt.CheckState.Checked:
                    has_unchecked = True
                    break
        if not has_visible:
            return
        new_state = Qt.CheckState.Checked if has_unchecked else Qt.CheckState.Unchecked
        self._updating_selection = True
        try:
            for row in range(self.table_widget.rowCount()):
                if not self.table_widget.isRowHidden(row):
                    item = self.table_widget.item(row, self.COL_CHECK)
                    if item:
                        item.setCheckState(new_state)
        finally:
            self._updating_selection = False
        self._sync_header_checkbox()
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
        if visible_count == 0 or checked_count == 0:
            self.header_checkbox.setCheckState(Qt.CheckState.Unchecked)
        elif checked_count == visible_count:
            self.header_checkbox.setCheckState(Qt.CheckState.Checked)
        else:
            self.header_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        self.header_checkbox.blockSignals(False)

    def _build_hierarchy(self) -> None:
        self._hierarchy.clear()
        self._sphere_icon_paths.clear()
        self._section_icon_paths.clear()
        self._category_icon_paths.clear()

        for item in self._issues:
            h = item.get("hierarchy") or {}
            sphere = str(h.get("sphere_name") or "").strip()
            section = str(h.get("section_name") or "").strip()
            category = str(h.get("category_name") or "").strip()

            if not sphere:
                continue
            if sphere not in self._hierarchy:
                self._hierarchy[sphere] = {}
            if section and section not in self._hierarchy[sphere]:
                self._hierarchy[sphere][section] = []
            if (
                section
                and category
                and category not in self._hierarchy[sphere][section]
            ):
                self._hierarchy[sphere][section].append(category)

            s_icon = str(h.get("sphere_icon_path") or "")
            sec_icon = str(h.get("section_icon_path") or "")
            cat_icon = str(h.get("category_icon_path") or "")

            if sphere:
                self._sphere_icon_paths.setdefault(sphere, s_icon)
            if sphere and section:
                self._section_icon_paths.setdefault((sphere, section), sec_icon)
            if sphere and section and category:
                self._category_icon_paths.setdefault(
                    (sphere, section, category), cat_icon
                )

    def _populate_filter_combos(self) -> None:
        all_text = QCoreApplication.translate("HealthRadarDialog", "All")

        # 1. Sphere combo
        curr_sphere = self.sphere_filter_combo.currentData() or "ALL"
        self.sphere_filter_combo.blockSignals(True)
        self.sphere_filter_combo.clear()
        self.sphere_filter_combo.addItem(all_text, "ALL")
        for sphere in sorted(self._hierarchy.keys()):
            icon_path = self._sphere_icon_paths.get(sphere, "")
            icon = get_cached_icon_with_fallback(
                icon_path,
                "sphere",
                entity_data={"name": sphere, "icon_path": icon_path},
            )
            if icon:
                self.sphere_filter_combo.addItem(icon, sphere, sphere)
            else:
                self.sphere_filter_combo.addItem(sphere, sphere)
        idx = self.sphere_filter_combo.findData(curr_sphere)
        self.sphere_filter_combo.setCurrentIndex(max(0, idx))
        self.sphere_filter_combo.blockSignals(False)

        # 2. Section and Category combos
        self._update_section_and_category_combos()

    def _update_section_and_category_combos(self) -> None:
        all_text = QCoreApplication.translate("HealthRadarDialog", "All")
        sphere = self.sphere_filter_combo.currentData()

        # Section combo
        curr_sec = self.section_filter_combo.currentData() or "ALL"
        self.section_filter_combo.blockSignals(True)
        self.section_filter_combo.clear()
        self.section_filter_combo.addItem(all_text, "ALL")

        if sphere != "ALL" and sphere in self._hierarchy:
            for section in sorted(self._hierarchy[sphere].keys()):
                icon = get_cached_icon(
                    self._section_icon_paths.get((sphere, section), "")
                )
                if icon:
                    self.section_filter_combo.addItem(icon, section, section)
                else:
                    self.section_filter_combo.addItem(section, section)
        else:
            all_sections: dict[str, str] = {}
            for sp_name, sp_data in self._hierarchy.items():
                for sec in sp_data.keys():
                    all_sections.setdefault(
                        sec, self._section_icon_paths.get((sp_name, sec), "")
                    )
            for section, icon_path in sorted(all_sections.items()):
                icon = get_cached_icon(icon_path)
                if icon:
                    self.section_filter_combo.addItem(icon, section, section)
                else:
                    self.section_filter_combo.addItem(section, section)

        idx = self.section_filter_combo.findData(curr_sec)
        self.section_filter_combo.setCurrentIndex(max(0, idx))
        self.section_filter_combo.blockSignals(False)

        self._update_category_combo()

    def _update_category_combo(self) -> None:
        all_text = QCoreApplication.translate("HealthRadarDialog", "All")
        sphere = self.sphere_filter_combo.currentData()
        section = self.section_filter_combo.currentData()

        curr_cat = self.category_filter_combo.currentData() or "ALL"
        self.category_filter_combo.blockSignals(True)
        self.category_filter_combo.clear()
        self.category_filter_combo.addItem(all_text, "ALL")

        if sphere != "ALL" and section != "ALL" and sphere in self._hierarchy:
            cats = self._hierarchy[sphere].get(section, [])
            for category in sorted(cats):
                icon = get_cached_icon(
                    self._category_icon_paths.get((sphere, section, category), "")
                )
                if icon:
                    self.category_filter_combo.addItem(icon, category, category)
                else:
                    self.category_filter_combo.addItem(category, category)
        elif sphere != "ALL" and sphere in self._hierarchy:
            all_cats: dict[str, str] = {}
            for sec_name, categories in self._hierarchy[sphere].items():
                for cat in categories:
                    all_cats.setdefault(
                        cat, self._category_icon_paths.get((sphere, sec_name, cat), "")
                    )
            for category, icon_path in sorted(all_cats.items()):
                icon = get_cached_icon(icon_path)
                if icon:
                    self.category_filter_combo.addItem(icon, category, category)
                else:
                    self.category_filter_combo.addItem(category, category)
        else:
            all_cats: dict[str, str] = {}
            for sp_name, sp_data in self._hierarchy.items():
                for sec_name, categories in sp_data.items():
                    for cat in categories:
                        all_cats.setdefault(
                            cat,
                            self._category_icon_paths.get((sp_name, sec_name, cat), ""),
                        )
            for category, icon_path in sorted(all_cats.items()):
                icon = get_cached_icon(icon_path)
                if icon:
                    self.category_filter_combo.addItem(icon, category, category)
                else:
                    self.category_filter_combo.addItem(category, category)

        idx = self.category_filter_combo.findData(curr_cat)
        self.category_filter_combo.setCurrentIndex(max(0, idx))
        self.category_filter_combo.blockSignals(False)

    def _on_sphere_changed(self) -> None:
        self._update_section_and_category_combos()
        self._on_filter_changed()

    def _on_section_changed(self) -> None:
        self._update_category_combo()
        self._on_filter_changed()

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
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.close_button.setVisible(True)
        self.rescan_button.setVisible(True)
        self.rescan_button.setEnabled(True)

        self._issues = list(issues or [])
        self._issues_by_id = {int(item["id"]): item for item in self._issues}

        if not self._issues:
            # No issues found: stay in compact dialog mode
            self.setFixedSize(500, 140)
            self.table_widget.setRowCount(0)
            self.filter_container.setVisible(False)
            self.table_widget.setVisible(False)
            self.selection_info_label.setVisible(False)
            self.locate_button.setVisible(False)
            self.relink_button.setVisible(False)
            self.delete_button.setVisible(False)
            self.status_label.setVisible(True)
            self.status_label.setText(
                QCoreApplication.translate(
                    "HealthRadarDialog",
                    "All local paths are valid! No broken links found.",
                )
            )
            return

        # Issues found: expand window to comfortable size and display results
        self.setMinimumWidth(680)
        self.setMinimumHeight(350)
        self.setMaximumSize(16777215, 16777215)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.show()
        self.resize(960, 540)

        # Status message hides at top, content appears below
        self.status_label.setVisible(False)
        self._build_hierarchy()
        self._populate_filter_combos()

        self.filter_container.setVisible(True)
        self.table_widget.setVisible(True)
        self.selection_info_label.setVisible(True)
        self.locate_button.setVisible(True)
        self.relink_button.setVisible(True)
        self.delete_button.setVisible(True)

        self._populate_table()
        self._update_header_checkbox_pos()
        self._update_buttons_state()

    def _on_error(self, error_msg: str) -> None:
        self._is_finished = True
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.close_button.setVisible(True)
        self.rescan_button.setVisible(True)
        self.rescan_button.setEnabled(True)
        self.table_widget.setVisible(False)
        self.filter_container.setVisible(False)
        self.status_label.setVisible(True)
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
            LinkType.FILE.value: QCoreApplication.translate(
                "HealthRadarDialog", "File"
            ),
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

    def _get_error_color(self, status: str) -> QColor:
        tokens = theme_registry.get_theme_tokens(get_current_theme())
        if status == LinkHealthWorker.STATUS_FIX_FOUND:
            return QColor(tokens.get("status_success", "#2ea043"))
        if status == LinkHealthWorker.STATUS_DUPLICATE_EXISTS:
            return QColor(tokens.get("status_warning", "#d29922"))
        if status == LinkHealthWorker.STATUS_DRIVE_OFFLINE:
            return QColor(tokens.get("status_info", "#8b949e"))
        return QColor(tokens.get("status_error", "#f85149"))

    def _format_status_cell(self, item: dict[str, Any]) -> tuple[str, QColor]:
        status = str(item.get("status") or "")
        suggested = str(item.get("suggested_url") or "")
        color = self._get_error_color(status)
        if status == LinkHealthWorker.STATUS_FIX_FOUND and suggested:
            return f"➔ {suggested}", color
        if status == LinkHealthWorker.STATUS_DUPLICATE_EXISTS and suggested:
            return (
                QCoreApplication.translate(
                    "HealthRadarDialog",
                    "Duplicate target already in category: {0}",
                ).format(suggested),
                color,
            )
        if status == LinkHealthWorker.STATUS_DRIVE_OFFLINE:
            return (
                QCoreApplication.translate(
                    "HealthRadarDialog", "Drive or network share is offline"
                ),
                color,
            )
        return (
            QCoreApplication.translate("HealthRadarDialog", "File or folder not found"),
            color,
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
                name = str(item.get("name") or "")
                cat_path = str(item.get("category_path") or "")
                link_type = str(item.get("type") or "")
                type_label = self._format_type_label(link_type)

                # Column 0: Checkbox
                chk_item = QTableWidgetItem()
                chk_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                chk_item.setData(Qt.ItemDataRole.UserRole, link_id)
                is_fixable = status == LinkHealthWorker.STATUS_FIX_FOUND and bool(
                    suggested
                )
                chk_item.setCheckState(
                    Qt.CheckState.Checked if is_fixable else Qt.CheckState.Unchecked
                )
                self.table_widget.setItem(row_idx, self.COL_CHECK, chk_item)

                # Column 1: Name (rich tooltip with Category & Type)
                name_item = QTableWidgetItem(name)
                name_item.setData(Qt.ItemDataRole.UserRole, link_id)
                tooltip_parts = [name]
                if type_label:
                    tooltip_parts.append(f"{self.tr('Type:')} {type_label}")
                if cat_path:
                    tooltip_parts.append(f"{self.tr('Category:')} {cat_path}")
                name_item.setToolTip("\n".join(tooltip_parts))
                self.table_widget.setItem(row_idx, self.COL_NAME, name_item)

                # Column 2: Broken Path
                old_url = str(item.get("url") or "")
                old_item = QTableWidgetItem(old_url)
                old_item.setToolTip(old_url)
                self.table_widget.setItem(row_idx, self.COL_OLD_PATH, old_item)

                # Column 3: Suggested Fix / Status
                status_text, color = self._format_status_cell(item)
                sug_item = QTableWidgetItem(status_text)
                sug_item.setToolTip(suggested or status_text)
                sug_item.setForeground(color)
                self.table_widget.setItem(row_idx, self.COL_SUGGESTED, sug_item)
        finally:
            self._updating_selection = False

        self._apply_filters()
        self._sync_header_checkbox()

    def _refresh_table_rows(self) -> None:
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
                name_item = self.table_widget.item(row_idx, self.COL_NAME)
                if name_item is not None:
                    name = str(item.get("name") or "")
                    cat_path = str(item.get("category_path") or "")
                    type_label = self._format_type_label(str(item.get("type") or ""))
                    tooltip_parts = [name]
                    if type_label:
                        tooltip_parts.append(f"{self.tr('Type:')} {type_label}")
                    if cat_path:
                        tooltip_parts.append(f"{self.tr('Category:')} {cat_path}")
                    name_item.setToolTip("\n".join(tooltip_parts))

                sug_item = self.table_widget.item(row_idx, self.COL_SUGGESTED)
                if sug_item is not None:
                    status_text, color = self._format_status_cell(item)
                    sug_item.setText(status_text)
                    sug_item.setToolTip(str(item.get("suggested_url") or status_text))
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
        section_filter = str(self.section_filter_combo.currentData() or "ALL")
        category_filter = str(self.category_filter_combo.currentData() or "ALL")

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

            h = item.get("hierarchy") or {}
            if visible and sphere_filter != "ALL":
                if str(h.get("sphere_name") or "") != sphere_filter:
                    visible = False
            if visible and section_filter != "ALL":
                if str(h.get("section_name") or "") != section_filter:
                    visible = False
            if visible and category_filter != "ALL":
                if str(h.get("category_name") or "") != category_filter:
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

    def _update_buttons_state(self) -> None:
        if not self._is_finished:
            self.locate_button.setEnabled(False)
            self.relink_button.setEnabled(False)
            self.delete_button.setEnabled(False)
            return

        visible_count = 0
        for row_idx in range(self.table_widget.rowCount()):
            if not self.table_widget.isRowHidden(row_idx):
                visible_count += 1

        checked = self._get_checked_items()
        checked_count = len(checked)
        total_count = len(self._issues)

        # Update selection info counter (Selected: X of Y (total: Z))
        self.selection_info_label.setText(
            QCoreApplication.translate(
                "HealthRadarDialog", "Selected: {0} of {1} (total: {2})"
            ).format(checked_count, visible_count, total_count)
        )

        relinkable = [
            item
            for item in checked
            if item.get("status") == LinkHealthWorker.STATUS_FIX_FOUND
            and item.get("suggested_url")
        ]
        relink_count = len(relinkable)

        # Dynamic action button labels with counts
        if relink_count > 0:
            self.relink_button.setText(
                QCoreApplication.translate("HealthRadarDialog", "Relink ({0})").format(
                    relink_count
                )
            )
        else:
            self.relink_button.setText(
                QCoreApplication.translate("HealthRadarDialog", "Relink")
            )

        if checked_count > 0:
            self.delete_button.setText(
                QCoreApplication.translate("HealthRadarDialog", "Delete ({0})").format(
                    checked_count
                )
            )
        else:
            self.delete_button.setText(
                QCoreApplication.translate("HealthRadarDialog", "Delete")
            )

        self.locate_button.setEnabled(self._get_current_row_issue() is not None)
        self.relink_button.setEnabled(relink_count > 0)
        self.delete_button.setEnabled(checked_count > 0)

    def _on_context_menu(self, pos) -> None:
        item = self.table_widget.itemAt(pos)
        if not item:
            return
        row = item.row()
        chk_item = self.table_widget.item(row, self.COL_CHECK)
        if not chk_item:
            return
        link_id = int(chk_item.data(Qt.ItemDataRole.UserRole) or 0)
        issue = self._issues_by_id.get(link_id)
        if not issue:
            return

        menu = QMenu(self)

        locate_act = QAction(
            QCoreApplication.translate("HealthRadarDialog", "Locate..."), self
        )
        locate_act.triggered.connect(lambda: self._locate_issue(issue))
        menu.addAction(locate_act)

        open_folder_act = QAction(
            QCoreApplication.translate(
                "HealthRadarDialog", "Open Existing Parent Folder in Explorer"
            ),
            self,
        )
        open_folder_act.triggered.connect(
            lambda: self._open_existing_parent_in_explorer(issue)
        )
        menu.addAction(open_folder_act)

        menu.addSeparator()

        copy_act = QAction(
            QCoreApplication.translate("HealthRadarDialog", "Copy Path"), self
        )
        copy_act.triggered.connect(
            lambda: QApplication.clipboard().setText(str(issue.get("url") or ""))
        )
        menu.addAction(copy_act)

        menu.exec(self.table_widget.viewport().mapToGlobal(pos))

    def _open_existing_parent_in_explorer(self, issue: dict[str, Any]) -> None:
        url = str(issue.get("url") or "")
        expanded = expand_local_path(url)
        if not expanded:
            return
        cur = Path(os.path.normpath(expanded))
        if not cur.is_dir():
            cur = cur.parent
        while cur != cur.parent:
            try:
                if cur.is_dir():
                    os.startfile(str(cur))
                    return
            except OSError:
                pass
            cur = cur.parent

    def _on_item_double_clicked(self, _item: QTableWidgetItem) -> None:
        self._on_locate_clicked()

    def _on_locate_clicked(self) -> None:
        issue = self._get_current_row_issue()
        if issue is not None:
            self._locate_issue(issue)

    def _locate_issue(self, issue: dict[str, Any]) -> None:
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

    def _remove_issue_ids(self, removed_ids: set[int]) -> None:
        self._issues = [
            item for item in self._issues if int(item["id"]) not in removed_ids
        ]
        for rid in removed_ids:
            self._issues_by_id.pop(rid, None)

        if not self._issues:
            self._on_finished([])
            return

        self._build_hierarchy()
        self._populate_filter_combos()
        self._populate_table()
        self._update_buttons_state()

    def _on_rescan_clicked(self) -> None:
        if self.service.is_running():
            return
        self._is_finished = False
        self._issues.clear()
        self._issues_by_id.clear()

        # Revert to compact mode
        self.setFixedSize(500, 140)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMinMaxButtonsHint)
        self.show()

        self.table_widget.setVisible(False)
        self.filter_container.setVisible(False)
        self.selection_info_label.setVisible(False)
        self.locate_button.setVisible(False)
        self.relink_button.setVisible(False)
        self.delete_button.setVisible(False)
        self.close_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.cancel_button.setEnabled(True)
        self.rescan_button.setEnabled(False)

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText(
            QCoreApplication.translate("HealthRadarDialog", "Checking local paths...")
        )
        self.service.start_check()

    def _on_cancel_clicked(self) -> None:
        if not self._is_finished and self.service.is_running():
            self.service.cancel_check()
            self.status_label.setText(
                QCoreApplication.translate("HealthRadarDialog", "Cancelling...")
            )
            self.cancel_button.setEnabled(False)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if not self._is_finished and self.service.is_running():
            reply = DialogManager.show_custom(
                self,
                QMessageBox.Icon.Question,
                QCoreApplication.translate("HealthRadarDialog", "Cancel Check"),
                QCoreApplication.translate(
                    "HealthRadarDialog", "Local path check is still running. Cancel it?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.service.cancel_check()
                self.service.set_dialog(None)
                event.accept()
            else:
                event.ignore()
                return

        self.service.set_dialog(None)
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_header_checkbox_pos()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._update_header_checkbox_pos()
