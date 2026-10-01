import logging
import os
import platform
import re
import subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QFileInfo,
    QModelIndex,
    QSettings,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialogButtonBox,
    QFileDialog,
    QFileIconProvider,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.core.worker_manager import WorkerManager
from app.services.dialog_path_service import DialogPathService
from app.utils.i18n.common import tr as tr_common

from ..base_dialog import BaseDialog
from .search_worker import FileSearchWorker

logger = logging.getLogger(__name__)


class _SearchResultsModel(QAbstractTableModel):
    """Table model holding file search results for the dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[str, str, int, float, str]] = []  # (name, folder, size, mtime, full_path)
        self._headers: list[str] = []
        self._icon_provider = QFileIconProvider()
        self.retranslateUi()

    def retranslateUi(self) -> None:
        self._headers = [
            QCoreApplication.translate("FileSearchResultsModel", "Name"),
            QCoreApplication.translate("FileSearchResultsModel", "Folder"),
            QCoreApplication.translate("FileSearchResultsModel", "Size"),
            QCoreApplication.translate("FileSearchResultsModel", "Date modified"),
        ]
        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal, 0, len(self._headers) - 1
        )

    def rowCount(self, parent=None):  # noqa: N802 Qt signature
        if parent is None:
            parent = QModelIndex()
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=None):  # noqa: N802
        if parent is None:
            parent = QModelIndex()
        return 0 if parent.isValid() else len(self._headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        return None

    def flags(self, index):  # noqa: D401
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row >= len(self._rows):
            return None
        name, folder, size_bytes, mtime_ts, full_path = self._rows[row]

        if role == Qt.ItemDataRole.DecorationRole and col == 0:
            return self._icon_provider.icon(QFileInfo(full_path))

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return name
            elif col == 1:
                return folder
            elif col == 2:
                return self._format_size(size_bytes)
            elif col == 3:
                return self._format_date(mtime_ts)

        if role == Qt.ItemDataRole.ToolTipRole:
            return full_path
        return None

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    @staticmethod
    def _format_date(timestamp: float) -> str:
        if timestamp <= 0:
            return ""
        try:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    def get_full_path(self, row: int) -> str:
        if 0 <= row < len(self._rows):
            return self._rows[row][4]
        return ""

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        if not self._rows:
            return
        self.layoutAboutToBeChanged.emit()
        reverse = (order == Qt.SortOrder.DescendingOrder)
        if column == 0:
            self._rows.sort(key=lambda r: r[0].lower(), reverse=reverse)
        elif column == 1:
            self._rows.sort(key=lambda r: r[1].lower(), reverse=reverse)
        elif column == 2:
            self._rows.sort(key=lambda r: r[2], reverse=reverse)
        elif column == 3:
            self._rows.sort(key=lambda r: r[3], reverse=reverse)
        self.layoutChanged.emit()

    # Mutations
    def clear(self):
        if not self._rows:
            return
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()

    def add_results_batch(self, batch: list[tuple[str, str, int, float, str]]):
        if not batch:
            return
        start_row = len(self._rows)
        end_row = start_row + len(batch) - 1
        self.beginInsertRows(QModelIndex(), start_row, end_row)
        self._rows.extend(batch)
        self.endInsertRows()


class FileSearchDialog(BaseDialog):
    """Dialog for advanced file search with extensive filtering options."""

    files_selected = pyqtSignal(list)

    def __init__(self, parent=None):
        # Search control state
        self.search_worker = None
        self.is_searching = False
        self._quick_look_dialog = None

        # Hold references to UI texts for runtime retranslation
        self.lbl_search_location = None
        self.lbl_name_regex = None
        self.lbl_pattern = None
        self.lbl_content = None

        super().__init__(parent)
        self.setWindowTitle(tr_common("File search"))
        width, height = app_config.ui.get_file_search_dialog_size()
        self._restore_dialog_geometry(width, height)

        self._setup_ui()

        self._explorer_timeout = 10  # seconds
        
        # Throttling for GUI updates
        self._pending_batches = []  # Queue of batches to add
        self._update_timer = None

        # Translate after widgets are created
        self.retranslateUi()

    def _setup_ui(self):
        """Configure dialog widgets and layout."""
        layout = QVBoxLayout(self)

        # --- Primary filter panel ---
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # First row: name + actions
        self.lbl_name_regex = QLabel(self.tr("Search files:"))
        name_row = QWidget()
        name_row_layout = QHBoxLayout(name_row)
        name_row_layout.setContentsMargins(0, 0, 0, 0)
        self.regex_le = QLineEdit()
        self.regex_le.setClearButtonEnabled(True)
        self.regex_le.returnPressed.connect(self._start_search)
        self.regex_le.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        name_row_layout.addWidget(self.regex_le, 1)
        self.search_btn = QPushButton(self.tr("Search"))
        self.search_btn.clicked.connect(self._start_search)
        self.stop_btn = QPushButton(self.tr("Stop"))
        self.stop_btn.clicked.connect(self._stop_search)
        self.stop_btn.setEnabled(False)
        name_row_layout.addWidget(self.search_btn)
        name_row_layout.addWidget(self.stop_btn)
        form.addRow(self.lbl_name_regex, name_row)

        # Second row: search location
        self.lbl_search_location = QLabel(self.tr("Search in:"))
        location_row = QWidget()
        location_row_layout = QHBoxLayout(location_row)
        location_row_layout.setContentsMargins(0, 0, 0, 0)
        default_search_path = DialogPathService.get_downloads_dir("file_search")
        self.root_le = QLineEdit(default_search_path)
        self.root_le.returnPressed.connect(self._start_search)
        self.browse_btn = QPushButton(self.tr("Browse"))
        self.adjust_button_width(self.browse_btn, min_width=app_config.ui.get_fixed_button_width())
        self.browse_btn.clicked.connect(self._choose_root)
        location_row_layout.addWidget(self.root_le, 1)
        location_row_layout.addWidget(self.browse_btn)
        form.addRow(self.lbl_search_location, location_row)

        # Third row: extension + content
        self.lbl_pattern = QLabel(self.tr("Extension:"))
        pattern_row = QWidget()
        pattern_row_layout = QHBoxLayout(pattern_row)
        pattern_row_layout.setContentsMargins(0, 0, 0, 0)
        self.pattern_le = QLineEdit("*.*")
        self.pattern_le.returnPressed.connect(self._start_search)
        self.pattern_le.setMaximumWidth(app_config.ui.get_file_search_pattern_max_width())
        pattern_row_layout.addWidget(self.pattern_le)

        # --- Common extension dropdown ---
        from app.utils.ui.qt.combo_helpers import PopupComboBox

        self.pattern_combo = PopupComboBox()
        self.pattern_combo.setEditable(False)
        common_patterns = [
            "*.cdr",
            "*.psd",
            "*.ai",
            "*.indd",
            "*.pdf",
            "*.doc",
            "*.docx",
            "*.xls",
            "*.xlsx",
            "*.ppt",
            "*.pptx",
            "*.odt",
            "*.ods",
            "*.odp",
            "*.txt",
            "*.md",
            "*.jpg",
            "*.jpeg",
            "*.png",
            "*.gif",
            "*.tiff",
            "*.svg",
            "*.webp",
            "*.ico",
            "*.raw",
            "*.nef",
            "*.dng",
            "*.mp3",
            "*.wav",
            "*.flac",
            "*.ogg",
            "*.mp4",
            "*.avi",
            "*.mkv",
            "*.mov",
            "*.webm",
            "*.mpeg",
            "*.fb2",
            "*.zip",
            "*.rar",
            "*.7z",
            "*.torrent",
        ]
        self.pattern_combo.addItems(common_patterns)
        font_metrics = self.pattern_combo.fontMetrics()
        max_width = max(font_metrics.horizontalAdvance(ext) for ext in common_patterns)
        combo_extra = app_config.ui.get_file_search_pattern_combo_extra_width()
        self.pattern_combo.setFixedWidth(max_width + combo_extra)
        self.pattern_combo.setToolTip(self.tr("Quickly apply an extension mask"))
        self.pattern_combo.setCurrentIndex(-1)

        def set_pattern_from_combo(idx):
            if idx >= 0:
                self.pattern_le.setText(self.pattern_combo.itemText(idx))

        self.pattern_combo.currentIndexChanged.connect(set_pattern_from_combo)
        pattern_row_layout.addWidget(self.pattern_combo)

        self.lbl_content = QLabel(self.tr("With text:"))
        pattern_row_layout.addWidget(self.lbl_content)
        self.content_le = QLineEdit()
        self.content_le.setClearButtonEnabled(True)
        self.content_le.returnPressed.connect(self._start_search)
        self.content_le.setMinimumWidth(app_config.ui.get_file_search_content_min_width())
        self.content_le.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        pattern_row_layout.addWidget(self.content_le, 1)

        form.addRow(self.lbl_pattern, pattern_row)

        layout.addLayout(form)

        # --- Progress bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)

        # --- Results table (QTableView + model) ---
        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.model = _SearchResultsModel(self)
        self.table.setModel(self.model)

        # Column sizing
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSortIndicatorShown(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 220)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setVisible(True)
        self.table.verticalHeader().setVisible(False)

        # Double-click opens file in explorer
        self.table.doubleClicked.connect(self._on_double_click)

        # --- Status & Actions ---
        btns_layout = QHBoxLayout()

        self.status_label = QLabel(self.tr("Ready to search"))

        self.button_box = QDialogButtonBox()
        self.add_link_btn = self.button_box.addButton(
            self.tr("Add as link"), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.add_link_btn.setEnabled(False)
        self.add_link_btn.clicked.connect(self._on_add_link)

        self.open_folder_btn = self.button_box.addButton(
            self.tr("Open in file explorer"), QDialogButtonBox.ButtonRole.ActionRole
        )
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._on_open_folder)

        self.close_btn = self.button_box.addButton(
            self.tr("Close"), QDialogButtonBox.ButtonRole.RejectRole
        )
        self.close_btn.clicked.connect(self.reject)

        btns_layout.addWidget(self.status_label)
        btns_layout.addStretch()
        btns_layout.addWidget(self.button_box)

        # Assemble main layout
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.table)
        layout.addLayout(btns_layout)

        # Connect selection change to button updates
        try:
            self.table.selectionModel().selectionChanged.connect(
                lambda *_: self._update_buttons()
            )
        except Exception:
            pass

    def _translate_labels(self):
        """Translate label texts."""
        if self.lbl_search_location is not None:
            self.lbl_search_location.setText(self.tr("Search in:"))
        if self.lbl_name_regex is not None:
            self.lbl_name_regex.setText(self.tr("Search files:"))
        if self.lbl_pattern is not None:
            self.lbl_pattern.setText(self.tr("Extension:"))
        if self.lbl_content is not None:
            self.lbl_content.setText(self.tr("With text:"))

    def _translate_buttons(self):
        """Translate button texts and tooltips."""
        if hasattr(self, "pattern_combo") and self.pattern_combo is not None:
            self.pattern_combo.setToolTip(self.tr("Quickly apply an extension mask"))
        if hasattr(self, "browse_btn") and self.browse_btn is not None:
            self.browse_btn.setText(self.tr("Browse"))
            self.adjust_button_width(self.browse_btn, min_width=app_config.ui.get_fixed_button_width())
        if hasattr(self, "search_btn") and self.search_btn is not None:
            self.search_btn.setText(self.tr("Search"))
            self.adjust_button_width(self.search_btn, min_width=app_config.ui.get_fixed_button_width())
        if hasattr(self, "stop_btn") and self.stop_btn is not None:
            self.stop_btn.setText(self.tr("Stop"))
            self.adjust_button_width(self.stop_btn, min_width=app_config.ui.get_fixed_button_width())
        if hasattr(self, "add_link_btn") and self.add_link_btn is not None:
            self.add_link_btn.setText(self.tr("Add as link"))
        if hasattr(self, "open_folder_btn") and self.open_folder_btn is not None:
            self.open_folder_btn.setText(self.tr("Open in file explorer"))
        if hasattr(self, "close_btn") and self.close_btn is not None:
            self.close_btn.setText(self.tr("Close"))
        if hasattr(self, "button_box") and self.button_box is not None:
            self.equalize_button_box(self.button_box, min_width=app_config.ui.get_fixed_button_width())

    def _translate_status(self):
        """Translate status label."""
        if (
            hasattr(self, "status_label")
            and self.status_label is not None
            and not self.is_searching
        ):
            self.status_label.setText(self.tr("Ready to search"))

    def retranslateUi(self) -> None:  # type: ignore[override]
        """Update all texts on language change."""
        self.setWindowTitle(tr_common("File search"))
        self._translate_labels()
        self._translate_buttons()
        self._translate_status()
        if hasattr(self, "model") and self.model is not None:
            try:
                self.model.retranslateUi()
            except Exception:
                pass

    def _update_buttons(self):
        """Enable/disable buttons based on current selection."""
        has_selection = bool(self.table.selectionModel().selectedRows())
        self.add_link_btn.setEnabled(has_selection)
        self.open_folder_btn.setEnabled(has_selection)

    def _on_add_link(self):
        """Emit selected files to caller and close dialog."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        paths = [
            self.model.get_full_path(idx.row())
            for idx in selected_rows
            if self.model.get_full_path(idx.row())
        ]
        if paths:
            self.files_selected.emit(paths)
            self.accept()

    def _on_open_folder(self):
        """Open the selected file in the system file explorer."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        file_path = self.model.get_full_path(selected_rows[0].row())
        if file_path:
            self._open_file_in_explorer(file_path)

    def _open_file_in_explorer(self, file_path: str):
        """Open file explorer highlighting the supplied file."""
        try:
            logger.info("Opening in file explorer: %s", file_path)
            file_path_obj = Path(file_path).resolve()

            if not file_path_obj.exists():
                self.show_warning(
                    self.tr("File not found: {path}").format(path=file_path)
                )
                return

            system = platform.system()
            if system == "Windows":
                subprocess.run(
                    ["explorer", f"/select,{file_path_obj}"],
                    shell=False,
                    check=False,
                    timeout=self._explorer_timeout,
                )
            elif system == "Darwin":
                subprocess.run(
                    ["open", "-R", str(file_path_obj)],
                    check=True,
                    timeout=self._explorer_timeout,
                )
            else:
                folder_path = file_path_obj.parent
                subprocess.run(
                    ["xdg-open", str(folder_path)],
                    check=True,
                    timeout=self._explorer_timeout,
                )
        except Exception as e:
            self.show_warning(self.tr("Unexpected error: {error}").format(error=str(e)))

    def _choose_root(self):
        """Prompt user to select the search root folder via DialogPathService."""
        current_path = self.root_le.text().strip()
        if not current_path or not Path(current_path).exists():
            current_path = DialogPathService.get_downloads_dir("file_search")

        path = QFileDialog.getExistingDirectory(
            self, self.tr("Select folder for search"), current_path
        )
        if path:
            DialogPathService.remember_dir("file_search", path)
            self.root_le.setText(path)

    def _validate_inputs(self):
        """Validate user input before starting search."""
        root_path = self.root_le.text().strip()
        if not root_path:
            self.show_warning(self.tr("Specify a folder to search."))
            return False

        root_path_obj = Path(root_path)
        if not root_path_obj.exists():
            self.show_warning(
                self.tr("The folder does not exist: {path}").format(path=root_path)
            )
            return False

        if not root_path_obj.is_dir():
            self.show_warning(
                self.tr("The specified path is not a folder: {path}").format(
                    path=root_path
                )
            )
            return False

        regex_pattern = self.regex_le.text().strip()
        if regex_pattern:
            try:
                re.compile(regex_pattern)
            except re.error as e:
                self.show_warning(
                    self.tr("Invalid regular expression for name: {error}").format(
                        error=e
                    )
                )
                return False

        return True

    def _start_search(self):
        """Start the search operation."""
        if not self._validate_inputs():
            return

        if self.is_searching:
            return

        self.model.clear()

        self.is_searching = True
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.status_label.setText(self.tr("Searching…"))

        config = self._create_search_config()

        self.search_worker = FileSearchWorker(config)
        self.search_worker.signals.results_batch.connect(self._on_results_batch)
        self.search_worker.signals.progress_update.connect(self._on_progress_update)
        self.search_worker.signals.search_finished.connect(self._on_search_finished)
        self.search_worker.signals.error_occurred.connect(self._on_search_error)

        WorkerManager.run(self.search_worker)

    def _stop_search(self):
        """Stop the ongoing search."""
        if self.search_worker:
            self.search_worker.stop()
        self._on_search_finished()

    def _create_search_config(self):
        """Create configuration dictionary for the worker."""
        return {
            "root": self.root_le.text().strip(),
            "pattern": self.pattern_le.text().strip() or "*.*",
            "regex_name": self.regex_le.text().strip(),
            "content": self.content_le.text().strip(),
        }

    def _on_results_batch(self, batch: list):
        """Handle batch of results from worker."""
        self._pending_batches.append(batch)
        
        if self._update_timer is None:
            self._update_timer = QTimer(self)
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._process_pending_batches)
            self._update_timer.start(100)

    def _process_pending_batches(self):
        """Process all pending result batches with file metadata extraction."""
        if not self._pending_batches:
            self._update_timer = None
            return

        processed = []
        for batch in self._pending_batches:
            for result in batch:
                full_path = result[0]
                p = Path(full_path)
                name = p.name
                folder = str(p.parent)
                try:
                    st = p.stat()
                    size = st.st_size
                    mtime = st.st_mtime
                except OSError:
                    size = 0
                    mtime = 0.0
                processed.append((name, folder, size, mtime, full_path))

        self.model.add_results_batch(processed)
        self._pending_batches.clear()
        self._update_timer = None
        self._update_buttons()

    def _on_progress_update(self, files_processed: int, dirs_processed: int):
        """Update progress information."""
        count = self.model.rowCount()
        self.status_label.setText(
            self.tr("Searching… %n file(s) found", "", count)
        )

    def _on_search_error(self, error_msg: str):
        """Handle errors raised by the worker."""
        self._on_search_finished()
        self.show_error(error_msg, self.tr("Search error"))

    def _on_double_click(self, index):
        """Open file explorer on double click."""
        if index.isValid():
            file_path = self.model.get_full_path(index.row())
            if file_path:
                self._open_file_in_explorer(file_path)

    def _on_search_finished(self):
        """Revert UI after search completion and show summary."""
        if self._pending_batches:
            self._process_pending_batches()

        self.is_searching = False
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        count = self.model.rowCount()
        self.status_label.setText(
            self.tr("Search finished. %n file(s) found.", "", count)
        )
        self._update_buttons()

    def keyPressEvent(self, event):
        """Handle space for Quick Look, Enter for adding, and Ctrl+C for copying paths."""
        if event.key() == Qt.Key.Key_Space:
            self._on_quick_look()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.table.hasFocus() and self.table.selectionModel().hasSelection():
                self._on_add_link()
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selected_paths()
            event.accept()
            return
        super().keyPressEvent(event)

    def _copy_selected_paths(self):
        """Copy paths of selected files to the system clipboard."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        paths = [
            self.model.get_full_path(idx.row())
            for idx in selected_rows
            if self.model.get_full_path(idx.row())
        ]
        if paths:
            QApplication.clipboard().setText("\n".join(paths))

    def _on_quick_look(self):
        """Trigger macOS-style Quick Look preview for currently selected file."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return
        file_path = self.model.get_full_path(selected_rows[0].row())
        if not file_path or not Path(file_path).exists():
            return

        from app.views.windows.dialogs.quick_look_dialog import QuickLookDialog
        if not self._quick_look_dialog:
            self._quick_look_dialog = QuickLookDialog(
                self,
                on_open_callback=lambda l: self._open_file_in_explorer(
                    l.get("url") if isinstance(l, dict) else str(l)
                ),
            )
        self._quick_look_dialog.set_link({
            "type": "file",
            "url": file_path,
            "name": Path(file_path).name,
        })
        self._quick_look_dialog.open_animated()

    def _restore_dialog_geometry(self, default_w: int, default_h: int):
        """Restore window geometry from QSettings or apply defaults."""
        settings = self._get_settings()
        geo = settings.value("FileSearch/geometry")
        if geo:
            self.restoreGeometry(geo)
        else:
            self.resize(default_w, default_h)

    def _save_dialog_geometry(self):
        """Save window geometry to QSettings."""
        settings = self._get_settings()
        settings.setValue("FileSearch/geometry", self.saveGeometry())

    def _get_settings(self) -> QSettings:
        return QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_config.get_org_name(),
            app_config.get_app_name(),
        )

    def closeEvent(self, event):
        """Stop running worker and persist geometry on close."""
        if self.is_searching and self.search_worker:
            self._stop_search()
        self._save_dialog_geometry()
        super().closeEvent(event)

    def reject(self):
        """Stop running worker and persist geometry on reject."""
        if self.is_searching and self.search_worker:
            self._stop_search()
        self._save_dialog_geometry()
        super().reject()
