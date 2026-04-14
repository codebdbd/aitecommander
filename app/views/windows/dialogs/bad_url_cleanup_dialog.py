"""Dialog for checking and removing unreachable URLs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    QCoreApplication,
    QObject,
    QRunnable,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.core.worker_manager import WorkerManager
from app.utils.i18n.common import tr as tr_common
from app.views.windows.dialogs.base_dialog import BaseDialog
from app.views.windows.dialogs.link_dialog.icon_utils import get_cached_icon

if TYPE_CHECKING:
    from app.controllers.services.bad_url_check_service import BadUrlCheckService
    from app.models.database import Database

logger = logging.getLogger(__name__)

_TR_CONTEXT = "BadUrlCleanupDialog"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class _DeleteLinksWorkerSignals(QObject):
    """Signals for the asynchronous delete worker."""

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)


class _DeleteLinksWorker(QRunnable):
    """Background worker that removes links from the database in batches."""

    def __init__(self, db, link_ids: list[int], batch_size: int = 200):
        super().__init__()
        self.db = db
        self.link_ids = list(link_ids)
        self.batch_size = max(1, batch_size)
        self.signals = _DeleteLinksWorkerSignals()

    def run(self) -> None:
        deleted_ids: list[int] = []
        try:
            total = len(self.link_ids)
            if total == 0:
                self.signals.finished.emit(deleted_ids)
                return

            connection = self.db.connection
            processed = 0

            for start in range(0, total, self.batch_size):
                chunk = self.link_ids[start : start + self.batch_size]
                placeholders = ",".join("?" * len(chunk))
                query = f"DELETE FROM link WHERE id IN ({placeholders})"
                connection.execute(query, chunk)
                connection.commit()

                deleted_ids.extend(chunk)
                processed += len(chunk)
                self.signals.progress.emit(processed, total)

            self.signals.finished.emit(deleted_ids)
        except Exception as exc:
            try:
                self.db.connection.rollback()
            except Exception:
                pass
            logger.error("DeleteLinksWorker failed: %s", exc, exc_info=True)
            self.signals.error.emit(str(exc))


class BadUrlCleanupDialog(BaseDialog):
    """Dialog for checking and removing unreachable web links.

    Shows URL check progress and table with unreachable links.
    Allows selecting and deleting unreachable links from database.
    """

    def __init__(
        self,
        service: BadUrlCheckService,
        db: Database,
        parent=None,
    ):
        """
        Args:
            service: URL check service
            db: Database instance for link deletion
        """
        # Initialize attributes BEFORE QDialog.__init__ (which calls retranslateUi)
        self.service = service
        self.db = db
        self._is_finished = False
        self._bad_urls = []
        self._domain_groups = {}  # {domain: [bad_url_info, ...]}
        self._filter_enabled = False
        # Hierarchy: {sphere: {section: [category, ...]}}
        self._hierarchy = {}
        self._sphere_icon_paths: dict[str, str] = {}
        self._section_icon_paths: dict[tuple[str, str], str] = {}
        self._category_icon_paths: dict[tuple[str, str, str], str] = {}
        self._delete_in_progress = False
        self._current_delete_worker: _DeleteLinksWorker | None = None
        self._pending_deletion_ids: list[int] = []
        
        # Batching for table updates
        self._pending_bad_urls: list[tuple[dict, str]] = []  # [(bad_url_info, domain), ...]
        self._batch_size = 50  # Add rows in batches of 50
        self._last_table_update_time = 0.0
        self._table_update_throttle_ms = 200  # Update table max 5 times/second
        
        super().__init__(parent)

        self.setModal(True)
        min_w, min_h = app_config.ui.get_bad_url_cleanup_dialog_min_size()
        self.setMinimumWidth(min_w)
        self.setMinimumHeight(min_h)
        self.setWindowTitle(tr_common("Bad URL Cleanup"))

        self._setup_ui()
        self._connect_signals()
    def _setup_ui(self):
        """Setup UI components."""
        layout = QVBoxLayout(self)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        # Status label
        self.status_label = QLabel(QCoreApplication.translate("BadUrlCleanupDialog", "Checking web links for availability..."))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Filters (visible from start)
        filter_layout = QHBoxLayout()
        
        # Error type filter
        from PyQt6.QtWidgets import QComboBox
        error_label = QLabel(QCoreApplication.translate("BadUrlCleanupDialog", "Error:"))
        filter_layout.addWidget(error_label)
        
        self.error_filter_combo = QComboBox()
        self.error_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "🟢 All"), "ALL")
        self.error_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "🔴 DNS Failed"), "DNS Resolution Failed")
        self.error_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "🟡 404 Not Found"), "404 Not Found")
        self.error_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "🔵 No SSL"), "No SSL (HTTP only)")
        self.error_filter_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.error_filter_combo.setCurrentIndex(0)
        self.error_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.error_filter_combo)
        
        # Sphere filter
        sphere_label = QLabel(QCoreApplication.translate("BadUrlCleanupDialog", "Sphere:"))
        filter_layout.addWidget(sphere_label)
        
        self.sphere_filter_combo = QComboBox()
        self.sphere_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "All"), "ALL")
        self.sphere_filter_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.sphere_filter_combo.currentIndexChanged.connect(self._on_sphere_changed)
        filter_layout.addWidget(self.sphere_filter_combo)
        
        # Section filter
        section_label = QLabel(QCoreApplication.translate("BadUrlCleanupDialog", "Section:"))
        filter_layout.addWidget(section_label)
        
        self.section_filter_combo = QComboBox()
        self.section_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "All"), "ALL")
        self.section_filter_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.section_filter_combo.currentIndexChanged.connect(self._on_section_changed)
        filter_layout.addWidget(self.section_filter_combo)
        
        # Category filter
        category_label = QLabel(QCoreApplication.translate("BadUrlCleanupDialog", "Category:"))
        filter_layout.addWidget(category_label)
        
        self.category_filter_combo = QComboBox()
        self.category_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "All"), "ALL")
        self.category_filter_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.category_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.category_filter_combo)
        
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        # Table with unreachable URLs (visible from start, empty)
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(5)
        self.table_widget.setHorizontalHeaderLabels(
            [
                QCoreApplication.translate("BadUrlCleanupDialog", "Select"),
                QCoreApplication.translate("BadUrlCleanupDialog", "Domain"),
                QCoreApplication.translate("BadUrlCleanupDialog", "URL"),
                QCoreApplication.translate("BadUrlCleanupDialog", "Error"),
                QCoreApplication.translate("BadUrlCleanupDialog", "Category"),
            ]
        )
        self.table_widget.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.horizontalHeader().setStretchLastSection(False)
        self.table_widget.setVisible(True)  # Показываем сразу
        self.table_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self._on_context_menu)
        
        # Настраиваем режимы изменения размера колонок (один раз)
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Select
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Domain
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)           # URL (растягивается)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Error
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)       # Category (можно менять)
        
        layout.addWidget(self.table_widget)

        # Selection buttons (скрыты до завершения)
        selection_layout = QHBoxLayout()
        self.select_all_button = QPushButton(QCoreApplication.translate("BadUrlCleanupDialog", "Select All"))
        self.select_all_button.clicked.connect(self._on_select_all)
        self.select_all_button.setVisible(False)
        selection_layout.addWidget(self.select_all_button)

        self.select_none_button = QPushButton(QCoreApplication.translate("BadUrlCleanupDialog", "Select None"))
        self.select_none_button.clicked.connect(self._on_select_none)
        self.select_none_button.setVisible(False)
        selection_layout.addWidget(self.select_none_button)

        selection_layout.addStretch()
        layout.addLayout(selection_layout)

        # Selection info
        self.selection_info_label = QLabel("")
        self.selection_info_label.setVisible(False)
        layout.addWidget(self.selection_info_label)

        # Action buttons
        self.button_box = QDialogButtonBox()

        # Cancel button (during check)
        self.cancel_button = QPushButton(tr_common("Cancel"))
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        self.button_box.addButton(
            self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole
        )

        # Delete button (after completion)
        self.delete_button = QPushButton(QCoreApplication.translate("BadUrlCleanupDialog", "Delete Selected"))
        self.delete_button.clicked.connect(self._on_delete_clicked)
        self.delete_button.setVisible(False)
        self.button_box.addButton(
            self.delete_button, QDialogButtonBox.ButtonRole.DestructiveRole
        )

        # Close button (after completion)
        self.close_button = QPushButton(QCoreApplication.translate("BadUrlCleanupDialog", "Close"))
        self.close_button.clicked.connect(self.accept)
        self.close_button.setVisible(False)
        self.button_box.addButton(
            self.close_button, QDialogButtonBox.ButtonRole.AcceptRole
        )
        
        layout.addWidget(self.button_box)
    
    def _connect_signals(self):
        """Connect signals."""
        # Connect service signals (button signals already connected in _setup_ui)
        self.service.progress.connect(self._on_progress)
        self.service.bad_url_found.connect(self._on_bad_url_found)
        self.service.finished.connect(self._on_finished)
        self.service.error.connect(self._on_error)
    
    def _on_item_double_clicked(self, item: QTableWidgetItem):
        """Handle double-click on table item - open URL in browser."""
        row = item.row()
        url_item = self.table_widget.item(row, 2)  # URL column
        
        if not url_item:
            return
        
        url = url_item.text()
        
        # Open URL in browser
        import webbrowser
        webbrowser.open(url)
    
    def _on_context_menu(self, pos):
        """Handle right-click context menu."""
        # Get item at position
        item = self.table_widget.itemAt(pos)
        if not item:
            return
        
        row = item.row()
        url_item = self.table_widget.item(row, 2)  # URL column
        
        if not url_item:
            return
        
        url = url_item.text()
        
        # Show context menu
        import webbrowser

        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QApplication, QMenu
        
        menu = QMenu(self)
        
        open_action = QAction(QCoreApplication.translate("BadUrlCleanupDialog", "Open in Browser"), self)
        open_action.triggered.connect(lambda: webbrowser.open(url))
        menu.addAction(open_action)
        
        copy_action = QAction(QCoreApplication.translate("BadUrlCleanupDialog", "Copy URL"), self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(url))
        menu.addAction(copy_action)
        
        menu.exec(self.table_widget.viewport().mapToGlobal(pos))

    def _on_progress(self, current: int, total: int, message: str):
        """Progress handler."""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)

        self.status_label.setText(message)

    def _on_bad_url_found(self, bad_url_info: dict):
        """Handler for unreachable URL found."""
        # Add to list
        self._bad_urls.append(bad_url_info)

        # Group by domain
        domain = bad_url_info.get("domain", "unknown")
        if domain not in self._domain_groups:
            self._domain_groups[domain] = []
        self._domain_groups[domain].append(bad_url_info)

        # Build hierarchy (don't update combos yet)
        self._build_hierarchy(bad_url_info)
        
        # Add to pending batch
        self._pending_bad_urls.append((bad_url_info, domain))
        
        # Flush batch if size threshold reached OR time threshold passed
        import time
        current_time = time.time() * 1000  # milliseconds
        time_since_last_update = current_time - self._last_table_update_time
        
        if len(self._pending_bad_urls) >= self._batch_size or \
           time_since_last_update >= self._table_update_throttle_ms:
            self._flush_pending_table_updates()
            self._last_table_update_time = current_time

    def _build_hierarchy(self, bad_url_info: dict):
        """Build hierarchy from category path."""
        category_path = bad_url_info.get("category_path", "")
        
        # Parse path
        parts = [p.strip() for p in category_path.split("/")]
        
        if len(parts) >= 3:
            sphere, section, category = parts[0], parts[1], parts[2]
            
            # Build hierarchy
            if sphere not in self._hierarchy:
                self._hierarchy[sphere] = {}
            
            if section not in self._hierarchy[sphere]:
                self._hierarchy[sphere][section] = []

            if category not in self._hierarchy[sphere][section]:
                self._hierarchy[sphere][section].append(category)

            hierarchy_meta = bad_url_info.get("hierarchy") or {}
            sphere_label = hierarchy_meta.get("sphere_name") or sphere
            section_label = hierarchy_meta.get("section_name") or section
            category_label = hierarchy_meta.get("category_name") or category

            try:
                sphere_label = str(sphere_label)
                section_label = str(section_label)
                category_label = str(category_label)
            except Exception:
                sphere_label = sphere
                section_label = section
                category_label = category

            sphere_icon = hierarchy_meta.get("sphere_icon_path") or ""
            section_icon = hierarchy_meta.get("section_icon_path") or ""
            category_icon = hierarchy_meta.get("category_icon_path") or ""

            if sphere_label:
                self._sphere_icon_paths.setdefault(sphere_label, sphere_icon)
            if sphere_label and section_label:
                self._section_icon_paths.setdefault(
                    (sphere_label, section_label), section_icon
                )
            if sphere_label and section_label and category_label:
                self._category_icon_paths.setdefault(
                    (sphere_label, section_label, category_label), category_icon
                )

    def _populate_filter_combos(self):
        """Populate filter combos from hierarchy after check is finished."""
        # Add all spheres
        for sphere in sorted(self._hierarchy.keys()):
            icon = get_cached_icon(self._sphere_icon_paths.get(sphere, ""))
            if icon:
                self.sphere_filter_combo.addItem(icon, sphere, sphere)
            else:
                self.sphere_filter_combo.addItem(sphere, sphere)
        
        # Add all sections
        all_sections: dict[str, str] = {}
        for sphere_name, sphere_data in self._hierarchy.items():
            for section in sphere_data.keys():
                all_sections.setdefault(
                    section, self._section_icon_paths.get((sphere_name, section), "")
                )
        for section, icon_path in sorted(all_sections.items()):
            icon = get_cached_icon(icon_path)
            if icon:
                self.section_filter_combo.addItem(icon, section, section)
            else:
                self.section_filter_combo.addItem(section, section)
        
        # Add all categories
        all_categories: dict[str, str] = {}
        for sphere_name, sphere_data in self._hierarchy.items():
            for section_name, categories in sphere_data.items():
                for category in categories:
                    key = (sphere_name, section_name, category)
                    all_categories.setdefault(
                        category, self._category_icon_paths.get(key, "")
                    )
        for category, icon_path in sorted(all_categories.items()):
            icon = get_cached_icon(icon_path)
            if icon:
                self.category_filter_combo.addItem(icon, category, category)
            else:
                self.category_filter_combo.addItem(category, category)

    def _on_sphere_changed(self):
        """Sphere filter changed - update sections."""
        sphere = self.sphere_filter_combo.currentData()
        
        # Clear sections and categories
        self.section_filter_combo.clear()
        self.section_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "All"), "ALL")
        self.category_filter_combo.clear()
        self.category_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "All"), "ALL")
        
        if sphere != "ALL" and sphere in self._hierarchy:
            # Add sections for this sphere
            for section in sorted(self._hierarchy[sphere].keys()):
                icon = get_cached_icon(
                    self._section_icon_paths.get((sphere, section), "")
                )
                if icon:
                    self.section_filter_combo.addItem(icon, section, section)
                else:
                    self.section_filter_combo.addItem(section, section)
        else:
            # Add all sections
            all_sections = set()
            for sphere_data in self._hierarchy.values():
                all_sections.update(sphere_data.keys())
            for section in sorted(all_sections):
                icon = None
                for sphere_name in self._hierarchy.keys():
                    icon = get_cached_icon(
                        self._section_icon_paths.get((sphere_name, section), "")
                    )
                    if icon:
                        break
                if icon:
                    self.section_filter_combo.addItem(icon, section, section)
                else:
                    self.section_filter_combo.addItem(section, section)

        self._apply_filter()
    
    def _on_section_changed(self):
        """Section filter changed - update categories."""
        sphere = self.sphere_filter_combo.currentData()
        section = self.section_filter_combo.currentData()
        
        # Clear categories
        self.category_filter_combo.clear()
        self.category_filter_combo.addItem(QCoreApplication.translate("BadUrlCleanupDialog", "All"), "ALL")
        
        if section != "ALL":
            # Find categories for this section
            categories = set()
            if sphere != "ALL" and sphere in self._hierarchy:
                if section in self._hierarchy[sphere]:
                    categories.update(self._hierarchy[sphere][section])
            else:
                # Search in all spheres
                for sphere_data in self._hierarchy.values():
                    if section in sphere_data:
                        categories.update(sphere_data[section])
            
            for category in sorted(categories):
                icon = None
                if sphere != "ALL" and sphere in self._hierarchy:
                    icon = get_cached_icon(
                        self._category_icon_paths.get((sphere, section, category), "")
                    )
                else:
                    for sphere_name, sections in self._hierarchy.items():
                        if section in sections:
                            icon = get_cached_icon(
                                self._category_icon_paths.get(
                                    (sphere_name, section, category), ""
                                )
                            )
                            if icon:
                                break
                if icon:
                    self.category_filter_combo.addItem(icon, category, category)
                else:
                    self.category_filter_combo.addItem(category, category)
        else:
            # Add all categories
            all_categories = set()
            if sphere != "ALL" and sphere in self._hierarchy:
                for section_data in self._hierarchy[sphere].values():
                    all_categories.update(section_data)
            else:
                for sphere_data in self._hierarchy.values():
                    for section_data in sphere_data.values():
                        all_categories.update(section_data)
            
            for category in sorted(all_categories):
                icon = None
                if sphere != "ALL" and sphere in self._hierarchy:
                    for section_name in self._hierarchy[sphere].keys():
                        icon = get_cached_icon(
                            self._category_icon_paths.get(
                                (sphere, section_name, category), ""
                            )
                        )
                        if icon:
                            break
                else:
                    for sphere_name, sections in self._hierarchy.items():
                        for section_name in sections.keys():
                            icon = get_cached_icon(
                                self._category_icon_paths.get(
                                    (sphere_name, section_name, category), ""
                                )
                            )
                            if icon:
                                break
                        if icon:
                            break
                if icon:
                    self.category_filter_combo.addItem(icon, category, category)
                else:
                    self.category_filter_combo.addItem(category, category)
        
        self._apply_filter()
    
    def _on_filter_changed(self):
        """Filter change handler."""
        self._apply_filter()

    def _apply_filter(self):
        """Apply all filters to table."""
        error_filter = self.error_filter_combo.currentData()
        sphere_filter = self.sphere_filter_combo.currentData()
        section_filter = self.section_filter_combo.currentData()
        category_filter = self.category_filter_combo.currentData()
        
        # Show/hide rows based on all filters
        for row in range(self.table_widget.rowCount()):
            error_item = self.table_widget.item(row, 3)  # Колонка Error
            category_item = self.table_widget.item(row, 4)  # Колонка Category
            
            if not error_item or not category_item:
                continue
                
            error = error_item.text()
            category_path = category_item.text()
            
            # Check error filter
            error_match = True
            if error_filter != "ALL":
                error_match = error == error_filter
            # If "ALL" - always True
            
            # Check structure filters
            structure_match = True
            if sphere_filter != "ALL" or section_filter != "ALL" or category_filter != "ALL":
                parts = [p.strip() for p in category_path.split("/")]
                
                if len(parts) >= 3:
                    sphere, section, category = parts[0], parts[1], parts[2]
                    
                    if sphere_filter != "ALL" and sphere != sphere_filter:
                        structure_match = False
                    if section_filter != "ALL" and section != section_filter:
                        structure_match = False
                    if category_filter != "ALL" and category != category_filter:
                        structure_match = False
                else:
                    structure_match = False
            
            # Show only if passes ALL filters
            should_show = error_match and structure_match
            self.table_widget.setRowHidden(row, not should_show)
        
        # Обновляем информацию о выборе
        self._update_selection_info()

    def _add_table_row(self, bad_url_info: dict, domain: str):
        """Добавить строку в таблицу.
        
        Args:
            bad_url_info: Информация о недоступном URL
            domain: Домен ссылки
        """
        row = self.table_widget.rowCount()
        self.table_widget.insertRow(row)

        # Чекбокс для выбора (автовыбор только для критических ошибок)
        checkbox_widget = QTableWidgetItem()
        checkbox_widget.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        )
        is_selected = self._should_auto_select(bad_url_info["error"])
        checkbox_widget.setCheckState(
            Qt.CheckState.Checked if is_selected else Qt.CheckState.Unchecked
        )
        self.table_widget.setItem(row, 0, checkbox_widget)

        # Domain
        domain_item = QTableWidgetItem(domain)
        self.table_widget.setItem(row, 1, domain_item)

        # URL (with tooltip)
        url_item = QTableWidgetItem(bad_url_info["url"])
        url_item.setData(Qt.ItemDataRole.UserRole, bad_url_info["id"])
        url_item.setToolTip("Double-click to open or copy")
        self.table_widget.setItem(row, 2, url_item)

        # Error
        error_item = QTableWidgetItem(bad_url_info["error"])
        self.table_widget.setItem(row, 3, error_item)

        # Category
        category_item = QTableWidgetItem(bad_url_info["category_path"])
        self.table_widget.setItem(row, 4, category_item)

    def _rebuild_table(self):
        """Перестроить таблицу с группировкой по доменам."""
        self.table_widget.setRowCount(0)

        # Сортируем домены по количеству ссылок (убывание)
        sorted_domains = sorted(
            self._domain_groups.items(), key=lambda x: len(x[1]), reverse=True
        )

        for domain, links in sorted_domains:
            # Добавляем каждую ссылку этого домена
            for _idx, bad_url_info in enumerate(links):
                row = self.table_widget.rowCount()
                self.table_widget.insertRow(row)

                # Чекбокс для выбора (автовыбор только для критических ошибок)
                checkbox_widget = QTableWidgetItem()
                checkbox_widget.setFlags(
                    Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                )
                is_selected = self._should_auto_select(bad_url_info["error"])
                checkbox_widget.setCheckState(
                    Qt.CheckState.Checked if is_selected else Qt.CheckState.Unchecked
                )
                self.table_widget.setItem(row, 0, checkbox_widget)

                # Domain
                domain_item = QTableWidgetItem(domain)
                self.table_widget.setItem(row, 1, domain_item)

                # URL
                url_item = QTableWidgetItem(bad_url_info["url"])
                url_item.setData(Qt.ItemDataRole.UserRole, bad_url_info["id"])
                self.table_widget.setItem(row, 2, url_item)

                # Error
                error_item = QTableWidgetItem(bad_url_info["error"])
                self.table_widget.setItem(row, 3, error_item)

                # Category
                category_item = QTableWidgetItem(bad_url_info["category_path"])
                self.table_widget.setItem(row, 4, category_item)

        # Обновляем информацию о выборе
        self._update_selection_info()

    def _flush_pending_table_updates(self) -> None:
        """Flush pending table updates in batch."""
        if not self._pending_bad_urls:
            return
        
        # Disable sorting during batch insert for performance
        self.table_widget.setSortingEnabled(False)
        
        for bad_url_info, domain in self._pending_bad_urls:
            self._add_table_row(bad_url_info, domain)
        
        # Re-enable sorting
        self.table_widget.setSortingEnabled(True)
        
        # Clear pending batch
        self._pending_bad_urls.clear()
    
    def _should_auto_select(self, error: str) -> bool:
        """Определить, нужно ли автоматически выбрать ссылку для удаления.

        Args:
            error: Тип ошибки

        Returns:
            True если ссылку рекомендуется удалить
        """
        # Автоматически выбираем для удаления только критические:
        # - DNS Resolution Failed (домен не существует - 100% мёртвая ссылка)
        # НЕ выбираем автоматически:
        # - 404 Not Found (может быть перемещена)
        # - Timeout (может быть временная проблема)
        # - Refused (может быть временная проблема)
        # - SSL Error (можно исправить)
        # - 403 Forbidden (может требовать авторизации)
        # - Server Error (временная проблема сервера)
        auto_select_errors = [
            "DNS Resolution Failed",
        ]
        return error in auto_select_errors

    def _on_finished(self, bad_urls: list):
        """Обработчик завершения проверки."""
        self._is_finished = True
        self._bad_urls = bad_urls
        
        # Flush any remaining pending updates
        self._flush_pending_table_updates()

        self.progress_bar.setValue(100)

        if len(bad_urls) == 0:
            # Не найдено недоступных URL
            self.status_label.setText(QCoreApplication.translate("BadUrlCleanupDialog", "All links are accessible!"))
        else:
            # Найдены недоступные URL
            num_domains = len(self._domain_groups)
            self.status_label.setText(
                QCoreApplication.translate("BadUrlCleanupDialog", "Found {0} unreachable links in {1} domains").format(
                    len(bad_urls), num_domains
                )
            )

            # Перестраиваем таблицу с финальными данными
            self._rebuild_table()
            
            # Populate filter combos from hierarchy
            self._populate_filter_combos()

            # Устанавливаем фильтр на "All" для показа всех найденных проблем
            self.error_filter_combo.setCurrentIndex(0)  # 🟢 All
            self._filter_enabled = True  # Активируем фильтрацию
            self._apply_filter()  # Применяем фильтр
            
            # Показываем кнопки выбора
            self.select_all_button.setVisible(True)
            self.select_none_button.setVisible(True)
            self.selection_info_label.setVisible(True)

            # Показываем кнопку удаления
            self.delete_button.setVisible(True)

            # Применяем фильтр по умолчанию (только критические)
            self._apply_filter()
            
            # Обновляем информацию о выборе
            self._update_selection_info()

        # Скрываем кнопку отмены, показываем кнопку закрытия
        self.cancel_button.setVisible(False)
        self.close_button.setVisible(True)

        logger.info("[bad_url_cleanup_dialog] Check completed: %s bad URLs", len(bad_urls))

    def _on_error(self, error_message: str):
        """Обработчик ошибки."""
        self._is_finished = True

        self.progress_bar.setValue(0)
        self.status_label.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Error: {0}").format(error_message))
        self.table_widget.setVisible(False)

        # Скрываем кнопку отмены, показываем кнопку закрытия
        self.cancel_button.setVisible(False)
        self.close_button.setVisible(True)

        logger.error("[bad_url_cleanup_dialog] Check error: %s", error_message)

    def _on_cancel_clicked(self):
        """Обработчик нажатия кнопки отмены."""
        if not self._is_finished:
            self.service.cancel_check()
            self.status_label.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Cancelling..."))
            self.cancel_button.setEnabled(False)
    
    def closeEvent(self, event):
        """Обработчик закрытия диалога."""
        if self._delete_in_progress:
            from PyQt6.QtWidgets import QMessageBox

            from app.views.windows.dialogs.base_dialog import (
                apply_uniform_height_to_message_box,
            )

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle(tr_common("Delete Bad URLs"))
            msg_box.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Link deletion is still in progress. Please wait."))
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            apply_uniform_height_to_message_box(msg_box)
            msg_box.exec()
            event.ignore()
            return

        if not self._is_finished:
            # Проверка идёт - спрашиваем подтверждение
            from PyQt6.QtWidgets import QMessageBox

            from app.controllers.ui.dialogs.dialog_manager import DialogManager
            
            reply = DialogManager.show_custom(
                self,
                QMessageBox.Icon.Question,
                QCoreApplication.translate("BadUrlCleanupDialog", "Cancel Check"),
                QCoreApplication.translate("BadUrlCleanupDialog", "URL check is still running. Cancel it?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.service.cancel_check()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def _on_select_all(self):
        """Выбрать все ссылки."""
        for row in range(self.table_widget.rowCount()):
            if self.table_widget.isRowHidden(row):
                continue
            item = self.table_widget.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)
        self._update_selection_info()

    def _on_select_none(self):
        """Снять выбор со всех ссылок."""
        for row in range(self.table_widget.rowCount()):
            if self.table_widget.isRowHidden(row):
                continue
            item = self.table_widget.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)
        self._update_selection_info()

    def _update_selection_info(self):
        """Обновить информацию о выборе (только видимые строки)."""
        selected_count = 0
        visible_count = 0
        
        for row in range(self.table_widget.rowCount()):
            if not self.table_widget.isRowHidden(row):
                visible_count += 1
                if self.table_widget.item(row, 0).checkState() == Qt.CheckState.Checked:
                    selected_count += 1

        self.selection_info_label.setText(
            QCoreApplication.translate("BadUrlCleanupDialog", "Selected: {0} of {1}").format(selected_count, visible_count)
        )

    def _on_delete_clicked(self):
        """Обработчик нажатия кнопки удаления."""
        # Собираем ID выбранных ссылок (только видимые строки)
        selected_ids = []
        for row in range(self.table_widget.rowCount()):
            # Пропускаем скрытые строки (фильтр)
            if self.table_widget.isRowHidden(row):
                continue
            
            checkbox_item = self.table_widget.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                # URL в колонке 2
                url_item = self.table_widget.item(row, 2)
                if url_item:
                    link_id = url_item.data(Qt.ItemDataRole.UserRole)
                    if link_id:
                        selected_ids.append(link_id)

        if not selected_ids:
            from app.controllers.ui.dialogs.dialog_manager import DialogManager

            DialogManager.show_warning(
                self,
                QCoreApplication.translate("BadUrlCleanupDialog", "Delete Bad URLs"),
                QCoreApplication.translate("BadUrlCleanupDialog", "No links selected for deletion."),
            )
            return

        # Подтверждение удаления
        from PyQt6.QtWidgets import QMessageBox

        from app.controllers.ui.dialogs.dialog_manager import DialogManager

        message = QCoreApplication.translate("BadUrlCleanupDialog", "Delete {0} selected links?").format(len(selected_ids))
        message += "\n\n" + QCoreApplication.translate("BadUrlCleanupDialog", "This action cannot be undone.")
        
        reply = DialogManager.show_custom(
            self,
            QMessageBox.Icon.Question,
            QCoreApplication.translate("BadUrlCleanupDialog", "Delete Bad URLs"),
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_delete_links(selected_ids)

    def _start_delete_links(self, link_ids: list[int]) -> None:
        """Запустить асинхронное удаление выбранных ссылок."""
        if self._delete_in_progress:
            logger.info("[bad_url_cleanup_dialog] Delete already in progress")
            return

        self._delete_in_progress = True
        self._pending_deletion_ids = list(link_ids)

        self.delete_button.setEnabled(False)
        self.select_all_button.setEnabled(False)
        self.select_none_button.setEnabled(False)
        self.status_label.setText(
            QCoreApplication.translate("BadUrlCleanupDialog", "Deleting selected links... ({0})").format(len(link_ids))
        )
        self.progress_bar.setVisible(True)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(max(1, len(link_ids)))
        self.progress_bar.setValue(0)

        worker = _DeleteLinksWorker(self.db, link_ids)
        worker.signals.progress.connect(self._on_delete_progress)
        worker.signals.finished.connect(self._on_delete_finished)
        worker.signals.error.connect(self._on_delete_error)

        self._current_delete_worker = worker
        WorkerManager.run(worker)

    def _on_delete_progress(self, processed: int, total: int) -> None:
        """Обновить прогресс удаления."""
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(processed)
        self.status_label.setText(
            QCoreApplication.translate("BadUrlCleanupDialog", "Deleting selected links... {0}/{1}").format(processed, total)
        )

    def _on_delete_finished(self, deleted_ids: list[int]) -> None:
        """Завершение удаления ссылок."""
        deleted_set = set(deleted_ids or [])
        logger.info(
            "[bad_url_cleanup_dialog] Deleted %s links", len(deleted_set)
        )

        if deleted_set:
            self._bad_urls = [
                info for info in self._bad_urls if info.get("id") not in deleted_set
            ]

            for domain in list(self._domain_groups.keys()):
                filtered = [
                    info
                    for info in self._domain_groups[domain]
                    if info.get("id") not in deleted_set
                ]
                if filtered:
                    self._domain_groups[domain] = filtered
                else:
                    del self._domain_groups[domain]

        rows_to_remove = []
        for row in range(self.table_widget.rowCount()):
            item = self.table_widget.item(row, 2)
            if not item:
                continue
            link_id = item.data(Qt.ItemDataRole.UserRole)
            if link_id in deleted_set:
                rows_to_remove.append(row)

        for row in reversed(rows_to_remove):
            self.table_widget.removeRow(row)

        self.error_filter_combo.setCurrentIndex(0)
        self._apply_filter()

        total_remaining = self.table_widget.rowCount()
        if total_remaining == 0:
            self.status_label.setText(QCoreApplication.translate("BadUrlCleanupDialog", "All links deleted!"))
            self.table_widget.setVisible(False)
            self.select_all_button.setVisible(False)
            self.select_none_button.setVisible(False)
            self.selection_info_label.setVisible(False)
            self.delete_button.setVisible(False)
        else:
            visible_remaining = 0
            for row in range(self.table_widget.rowCount()):
                if not self.table_widget.isRowHidden(row):
                    visible_remaining += 1
            self.status_label.setText(
                QCoreApplication.translate("BadUrlCleanupDialog", "Deleted {0} links. {1} total remaining ({2} visible).").format(
                    len(deleted_set), total_remaining, visible_remaining
                )
            )
            self._update_selection_info()

        self._finalize_delete_operation(success=True)

    def _on_delete_error(self, error_message: str) -> None:
        """Обработчик ошибки удаления."""
        logger.error(
            "[bad_url_cleanup_dialog] Failed to delete links: %s",
            error_message,
        )
        from app.controllers.ui.dialogs.dialog_manager import DialogManager

        DialogManager.show_error(
            self,
            QCoreApplication.translate("BadUrlCleanupDialog", "Delete Bad URLs"),
            QCoreApplication.translate("BadUrlCleanupDialog", "Failed to delete links."),
            details=error_message,
        )

        self.status_label.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Failed to delete selected links."))
        self._finalize_delete_operation(success=False)

    def _finalize_delete_operation(self, success: bool) -> None:
        """Reset UI/state after deletion completes."""
        self._delete_in_progress = False
        self._pending_deletion_ids = []
        self._current_delete_worker = None

        if self.delete_button.isVisible():
            self.delete_button.setEnabled(True)
        self.select_all_button.setEnabled(True)
        self.select_none_button.setEnabled(True)

        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100 if success else 0)

    def retranslateUi(self):
        """Update UI translations."""
        self.setWindowTitle(tr_common("Bad URL Cleanup"))

        # Проверяем что UI элементы уже созданы
        if not hasattr(self, "status_label"):
            return

        if not self._is_finished:
            self.status_label.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Checking web links for availability..."))

        # Обновляем заголовки таблицы
        self.table_widget.setHorizontalHeaderLabels(
            [
                QCoreApplication.translate("BadUrlCleanupDialog", "Select"),
                QCoreApplication.translate("BadUrlCleanupDialog", "Domain"),
                QCoreApplication.translate("BadUrlCleanupDialog", "URL"),
                QCoreApplication.translate("BadUrlCleanupDialog", "Error"),
                QCoreApplication.translate("BadUrlCleanupDialog", "Category"),
            ]
        )

        self.select_all_button.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Select All"))
        self.select_none_button.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Select None"))
        self.cancel_button.setText(tr_common("Cancel"))
        self.delete_button.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Delete Selected"))
        self.close_button.setText(QCoreApplication.translate("BadUrlCleanupDialog", "Close"))


__all__ = ["BadUrlCleanupDialog"]
