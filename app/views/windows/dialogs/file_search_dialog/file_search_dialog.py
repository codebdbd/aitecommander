import logging
import platform
import re
import subprocess
from pathlib import Path

from PyQt6.QtCore import (
    QT_TRANSLATE_NOOP,
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    Qt,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
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
from app.utils.i18n.common import tr as tr_common

from ..base_dialog import BaseDialog
from .search_worker import FileSearchWorker

logger = logging.getLogger(__name__)


_MODEL_TR_CONTEXT = "FileSearchResultsModel"
_DIALOG_TR_CONTEXT = "FileSearchDialog"
_HEADER_TRANSLATABLE = [
    QT_TRANSLATE_NOOP(_MODEL_TR_CONTEXT, "Path"),
]


def _tr_model(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_MODEL_TR_CONTEXT, text, disambiguation)


def _tr_dialog(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_DIALOG_TR_CONTEXT, text, disambiguation)


class _SearchResultsModel(QAbstractTableModel):
    """Table model holding file search results for the dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []  # list of tuples: (path,)
        self._headers: list[str] = []
        self.retranslateUi()

    def retranslateUi(self) -> None:
        self._headers = [_tr_model(text) for text in _HEADER_TRANSLATABLE]
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
        # Non-editable table, rows selectable only
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            row = index.row()
            col = index.column()
            try:
                return self._rows[row][col]
            except Exception:
                return None
        return None

    # Mutations
    def clear(self):
        if not self._rows:
            return
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()

    def add_result(
        self, path: str
    ):
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append((path,))
        self.endInsertRows()


class FileSearchDialog(BaseDialog):
    """Dialog for advanced file search with extensive filtering options."""

    files_selected = pyqtSignal(list)

    def __init__(self, parent=None):
        # Search control state
        self.search_worker = None
        self.is_searching = False

        # Hold references to UI texts for runtime retranslation
        self.lbl_search_location = None
        self.lbl_name_regex = None
        self.lbl_pattern = None
        self.lbl_content = None

        super().__init__(parent)
        self.setWindowTitle(tr_common("File search"))
        width, height = app_config.ui.get_file_search_dialog_size()
        self.resize(width, height)

        self._setup_ui()
        self._setup_defaults()

        self._explorer_timeout = 10  # seconds
        
        # Throttling for GUI updates
        self._pending_batches = []  # Queue of batches to add
        self._update_timer = None  # Timer for throttled updates

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
        self.root_le = QLineEdit(str(Path.home()))
        self.root_le.setMinimumWidth(app_config.ui.get_file_search_root_min_width())
        browse_btn = QPushButton(self.tr("Browse"))
        browse_btn.clicked.connect(self._choose_root)
        location_row_layout.addWidget(self.root_le, 1)
        location_row_layout.addWidget(browse_btn)
        form.addRow(self.lbl_search_location, location_row)

        # Third row: extension + content
        self.lbl_pattern = QLabel(self.tr("Extension:"))
        pattern_row = QWidget()
        pattern_row_layout = QHBoxLayout(pattern_row)
        pattern_row_layout.setContentsMargins(0, 0, 0, 0)
        self.pattern_le = QLineEdit("*.*")
        self.pattern_le.setMaximumWidth(app_config.ui.get_file_search_pattern_max_width())
        pattern_row_layout.addWidget(self.pattern_le)

        # --- Common extension dropdown ---
        from PyQt6.QtWidgets import QComboBox

        self.pattern_combo = QComboBox()
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
        # Fit dropdown width to contents
        font_metrics = self.pattern_combo.fontMetrics()
        max_width = max(font_metrics.horizontalAdvance(ext) for ext in common_patterns)
        combo_extra = app_config.ui.get_file_search_pattern_combo_extra_width()
        self.pattern_combo.setFixedWidth(max_width + combo_extra)  # + for arrow and padding
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
        self.progress_bar.setRange(0, 0)  # Indeterminate progress

        # --- Results table (QTableView + model) ---
        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.model = _SearchResultsModel(self)
        self.table.setModel(self.model)

        # Column sizing
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Path
        header.setVisible(False)
        self.table.verticalHeader().setVisible(False)

        # Double-click opens file in explorer
        self.table.doubleClicked.connect(self._on_double_click)

        # --- Status ---
        self.status_label = QLabel(self.tr("Ready to search"))

        # --- Action buttons ---
        btns_layout = QHBoxLayout()

        self.add_link_btn = QPushButton(self.tr("Add as link"))
        self.add_link_btn.setEnabled(False)
        self.add_link_btn.clicked.connect(self._on_add_link)

        self.open_folder_btn = QPushButton(self.tr("Open in file explorer"))
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._on_open_folder)

        close_btn = QPushButton(self.tr("Close"))
        close_btn.clicked.connect(self.reject)

        btns_layout.addWidget(self.status_label)
        btns_layout.addStretch()
        btns_layout.addWidget(self.add_link_btn)
        btns_layout.addWidget(self.open_folder_btn)
        btns_layout.addWidget(close_btn)

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
        if hasattr(self, "search_btn") and self.search_btn is not None:
            self.search_btn.setText(self.tr("Search"))
        if hasattr(self, "stop_btn") and self.stop_btn is not None:
            self.stop_btn.setText(self.tr("Stop"))
        if hasattr(self, "add_link_btn") and self.add_link_btn is not None:
            self.add_link_btn.setText(self.tr("Add as link"))
        if hasattr(self, "open_folder_btn") and self.open_folder_btn is not None:
            self.open_folder_btn.setText(self.tr("Open in file explorer"))

    def _translate_status(self):
        """Translate status label."""
        if (
            hasattr(self, "status_label")
            and self.status_label is not None
            and not self.is_searching
        ):
            self.status_label.setText(self.tr("Ready to search"))

    def _translate_placeholders(self):
        """Translate placeholder texts."""
        pass

    def retranslateUi(self) -> None:  # type: ignore[override]
        """Update all texts on language change."""
        self.setWindowTitle(tr_common("File search"))
        self._translate_labels()
        self._translate_buttons()
        self._translate_status()
        self._translate_placeholders()
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

    def _get_full_file_path(self, row):
        """Return the full file path for the supplied table row."""
        idx_path = self.model.index(row, 0)
        full_path = self.model.data(idx_path, Qt.ItemDataRole.DisplayRole) or ""
        return str(Path(full_path).resolve())

    def _on_add_link(self):
        """Add the selected file as a link."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        file_path = self._get_full_file_path(selected_rows[0].row())
        main_window = (
            self.parent()
            if hasattr(self.parent(), "show_link_dialog")
            else (self.parent().parent() if self.parent() else None)
        )
        if main_window and hasattr(main_window, "show_link_dialog"):
            # Open LinkDialog with pre-filled path

            # Prefer links_actions facade when available
            if hasattr(main_window, "links_actions"):
                main_window.links_actions.show_link_dialog(
                    link={"type": "file", "url": file_path},
                    category_id=getattr(main_window, "current_category_id", None),
                )
            else:
                # Fallback: call MainWindow directly
                main_window.show_link_dialog(
                    link={"type": "file", "url": file_path},
                    category_id=getattr(main_window, "current_category_id", None),
                )
            return

    def _on_open_folder(self):
        """Open the selected file in the system file explorer."""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return

        file_path = self._get_full_file_path(selected_rows[0].row())
        self._open_file_in_explorer(file_path)

    def _open_file_in_explorer(self, file_path):
        """Open file explorer highlighting the supplied file."""
        try:
            logger.info("Opening in file explorer: %s", file_path)

            # Normalize path before usage
            file_path_obj = Path(file_path).resolve()

            if not file_path_obj.exists():
                self.show_warning(
                    self.tr("File not found: {path}").format(path=file_path)
                )
                return

            system = platform.system()

            if system == "Windows":
                # Windows: explorer with /select flag
                subprocess.run(
                    ["explorer", f"/select,{file_path_obj}"],
                    shell=False,
                    check=False,
                    timeout=self._explorer_timeout,
                )
            elif system == "Darwin":  # macOS
                # macOS: use `open -R`
                subprocess.run(
                    ["open", "-R", str(file_path_obj)],
                    check=True,
                    timeout=self._explorer_timeout,
                )
            elif system == "Linux":
                # Linux: attempt several file managers sequentially
                try:
                    subprocess.run(
                        ["nautilus", "--select", str(file_path_obj)],
                        check=True,
                        timeout=self._explorer_timeout,
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    try:
                        subprocess.run(
                            ["dolphin", "--select", str(file_path_obj)],
                            check=True,
                            timeout=self._explorer_timeout,
                        )
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        try:
                            subprocess.run(
                                ["thunar", str(file_path_obj.parent)],
                                check=True,
                                timeout=self._explorer_timeout,
                            )
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            try:
                                subprocess.run(
                                    ["pcmanfm", str(file_path_obj.parent)],
                                    check=True,
                                    timeout=self._explorer_timeout,
                                )
                            except (subprocess.CalledProcessError, FileNotFoundError):
                                folder_path = file_path_obj.parent
                                subprocess.run(
                                    ["xdg-open", str(folder_path)],
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

        except subprocess.CalledProcessError as e:
            self.show_warning(
                self.tr("Failed to open file in explorer: {error}").format(error=str(e))
            )
        except subprocess.TimeoutExpired as e:
            self.show_warning(
                self.tr("Opening the file explorer timed out: {error}").format(
                    error=str(e)
                )
            )
        except Exception as e:
            self.show_warning(self.tr("Unexpected error: {error}").format(error=str(e)))

    def _setup_defaults(self):
        """Reset default values."""
        pass

    def _choose_root(self):
        """Prompt user to select the search root folder."""
        current_path = self.root_le.text().strip()
        if not current_path or not Path(current_path).exists():
            current_path = str(Path.home())

        path = QFileDialog.getExistingDirectory(
            self.parent(), self.tr("Select folder for search"), current_path
        )
        if path:
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

        # Validate name regular expression if specified
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

        # Clear previous results
        self.model.clear()

        # Switch UI to searching state
        self.is_searching = True
        self.search_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.status_label.setText(self.tr("Searching…"))

        # Build search configuration
        config = self._create_search_config()

        # Create and start worker
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
        """Handle batch of results from worker.
        
        Batch format: list of tuples (path,)
        """
        # Add batch to pending queue
        self._pending_batches.append(batch)
        
        # Schedule GUI update if not already scheduled
        if self._update_timer is None:
            from PyQt6.QtCore import QTimer
            self._update_timer = QTimer()
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self._process_pending_batches)
            self._update_timer.start(100)  # 100ms throttle
    
    def _process_pending_batches(self):
        """Process all pending result batches."""
        if not self._pending_batches:
            self._update_timer = None
            return
        
        # Process all pending batches at once
        for batch in self._pending_batches:
            for result in batch:
                # result is (path,)
                self.model.add_result(*result)
        
        self._pending_batches.clear()
        self._update_timer = None
        
        # Refresh buttons when rows appear
        self._update_buttons()
    
    def _on_progress_update(self, files_processed: int, dirs_processed: int):
        """Update progress information."""
        self.status_label.setText(
            self.tr("Searching… Files: {files}, Directories: {dirs}").format(
                files=files_processed, dirs=dirs_processed
            )
        )

    def _on_search_error(self, error_msg: str):
        """Handle errors raised by the worker."""
        self._on_search_finished()
        self.show_error(error_msg, self.tr("Search error"))

    def _on_double_click(self, index):
        """Open file explorer on double click."""
        if index.isValid():
            file_path = self._get_full_file_path(index.row())
            self._open_file_in_explorer(file_path)

    def _on_search_finished(self):
        """Revert UI after search completion and show summary."""
        # Process any remaining batches
        if self._pending_batches:
            self._process_pending_batches()
        
        self.is_searching = False
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        count = self.model.rowCount()
        self.status_label.setText(
            self.tr("Search finished. Files found: {count}").format(count=count)
        )
        self._update_buttons()
