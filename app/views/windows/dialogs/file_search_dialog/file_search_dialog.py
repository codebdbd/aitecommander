import logging
import platform
import re
import subprocess
import time
from pathlib import Path

from PyQt6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QDate,
    QModelIndex,
    Qt,
    QThreadPool,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
)

from ..base_dialog import BaseDialog
from .search_worker import FileSearchWorker

logger = logging.getLogger(__name__)


_MODEL_TR_CONTEXT = "FileSearchResultsModel"
_DIALOG_TR_CONTEXT = "FileSearchDialog"


def _tr_model(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_MODEL_TR_CONTEXT, text, disambiguation)


def _tr_dialog(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_DIALOG_TR_CONTEXT, text, disambiguation)


class _SearchResultsModel(QAbstractTableModel):
    """Table model holding file search results for the dialog."""

    HEADERS = [
        _tr_model("Name"),
        _tr_model("Path"),
        _tr_model("Size (KB)"),
        _tr_model("Modified"),
        _tr_model("Contains"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []  # list of tuples: (name, path, size_kb, mtime_str, has_content)

    def rowCount(self, parent=None):  # noqa: N802 Qt signature
        if parent is None:
            parent = QModelIndex()
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=None):  # noqa: N802
        if parent is None:
            parent = QModelIndex()
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
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
        self, name: str, path: str, size_kb: int, mtime_str: str, has_content: str
    ):
        row = len(self._rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self._rows.append((name, path, str(size_kb), mtime_str, has_content))
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
        self.lbl_size = None
        self.lbl_modified = None

        super().__init__(parent)
        self.setWindowTitle(self.tr("Advanced file search"))
        self.resize(900, 700)

        self._setup_ui()
        self._setup_defaults()

        # ThreadPool for running background search workers
        self.threadpool = QThreadPool()

        # Translate after widgets are created
        self.retranslateUi()

    def _setup_ui(self):
        """Configure dialog widgets and layout."""
        layout = QVBoxLayout(self)

        # --- Primary filter panel ---

        # Folder selection
        folder_layout = QHBoxLayout()
        self.lbl_search_location = QLabel(self.tr("Search location:"))
        folder_layout.addWidget(self.lbl_search_location)
        self.root_le = QLineEdit(str(Path.home()))
        self.root_le.setMinimumWidth(200)
        browse_btn = QPushButton(self.tr("Browse"))
        browse_btn.clicked.connect(self._choose_root)
        folder_layout.addWidget(self.root_le)
        folder_layout.addWidget(browse_btn)

        # File name/regex and mask row
        name_mask_layout = QHBoxLayout()
        self.lbl_name_regex = QLabel(self.tr("Name (regex):"))
        name_mask_layout.addWidget(self.lbl_name_regex)
        from PyQt6.QtWidgets import QSizePolicy

        self.regex_le = QLineEdit()
        self.regex_le.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        name_mask_layout.addWidget(self.regex_le)
        name_mask_layout.setStretch(name_mask_layout.count() - 1, 1)
        self.lbl_pattern = QLabel(self.tr("Pattern:"))
        name_mask_layout.addWidget(self.lbl_pattern)
        self.pattern_le = QLineEdit("*.*")
        self.pattern_le.setMaximumWidth(100)
        name_mask_layout.addWidget(self.pattern_le)

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
        self.pattern_combo.setFixedWidth(max_width + 36)  # +36 for arrow and padding
        self.pattern_combo.setToolTip(self.tr("Quickly apply an extension mask"))
        self.pattern_combo.setCurrentIndex(-1)

        def set_pattern_from_combo(idx):
            if idx >= 0:
                self.pattern_le.setText(self.pattern_combo.itemText(idx))

        self.pattern_combo.currentIndexChanged.connect(set_pattern_from_combo)
        name_mask_layout.addWidget(self.pattern_combo)

        # Content filter and toggles
        self.lbl_content = QLabel(self.tr("Content:"))
        name_mask_layout.addWidget(self.lbl_content)
        self.content_le = QLineEdit()
        self.content_le.setMinimumWidth(200)
        self.content_regex_cb = QCheckBox(self.tr("Regex"))
        self.case_cb = QCheckBox(self.tr("Case sensitive"))
        name_mask_layout.addWidget(self.content_le)
        self.search_btn = QPushButton(self.tr("Search"))
        self.search_btn.clicked.connect(self._start_search)
        self.stop_btn = QPushButton(self.tr("Stop"))
        self.stop_btn.clicked.connect(self._stop_search)
        self.stop_btn.setEnabled(False)
        name_mask_layout.addWidget(self.search_btn)
        name_mask_layout.addWidget(self.stop_btn)
        name_mask_layout.addStretch()

        # First row: path
        layout.addLayout(folder_layout)
        # Second row: name, pattern, content, actions
        layout.addLayout(name_mask_layout)

        # --- Size and date filters ---
        filter_row1 = QHBoxLayout()

        # File size filter
        size_layout = QHBoxLayout()
        self.lbl_size = QLabel(self.tr("Size (KB):"))
        size_layout.addWidget(self.lbl_size)
        from PyQt6.QtGui import QIntValidator

        self.size_min_le = QLineEdit()
        self.size_min_le.setValidator(QIntValidator(0, 999999))
        self.size_min_le.setPlaceholderText(self.tr("from"))
        self.size_min_le.setMaximumWidth(60)
        size_layout.addWidget(self.size_min_le)
        size_layout.addWidget(QLabel("-"))
        self.size_max_le = QLineEdit()
        self.size_max_le.setValidator(QIntValidator(0, 999999))
        self.size_max_le.setPlaceholderText(self.tr("to"))
        self.size_max_le.setMaximumWidth(60)
        size_layout.addWidget(self.size_max_le)

        # Modified date filter
        date_layout = QHBoxLayout()
        self.lbl_modified = QLabel(self.tr("Modified:"))
        date_layout.addWidget(self.lbl_modified)
        self.date_from_de = QDateEdit()
        self.date_from_de.setCalendarPopup(True)
        self.date_from_de.setDate(QDate.currentDate().addYears(-1))

        self.date_to_de = QDateEdit()
        self.date_to_de.setCalendarPopup(True)
        self.date_to_de.setDate(QDate.currentDate())

        date_layout.addWidget(self.date_from_de)
        date_layout.addWidget(self.date_to_de)

        filter_row1.addLayout(size_layout)
        filter_row1.addLayout(date_layout)
        # Additional toggles
        self.hidden_cb = QCheckBox(self.tr("Hidden files"))
        self.readonly_cb = QCheckBox(self.tr("Read-only"))
        filter_row1.addWidget(self.hidden_cb)
        filter_row1.addWidget(self.readonly_cb)
        filter_row1.addWidget(self.content_regex_cb)
        filter_row1.addWidget(self.case_cb)
        filter_row1.addStretch()

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
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Path
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Size
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Date
        header.setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )  # Contains

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
        layout.addLayout(filter_row1)
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
            self.lbl_search_location.setText(self.tr("Search location:"))
        if self.lbl_name_regex is not None:
            self.lbl_name_regex.setText(self.tr("Name (regex):"))
        if self.lbl_pattern is not None:
            self.lbl_pattern.setText(self.tr("Pattern:"))
        if self.lbl_content is not None:
            self.lbl_content.setText(self.tr("Content:"))
        if self.lbl_size is not None:
            self.lbl_size.setText(self.tr("Size (KB):"))
        if self.lbl_modified is not None:
            self.lbl_modified.setText(self.tr("Modified:"))

    def _translate_buttons(self):
        """Translate button texts and tooltips."""
        if hasattr(self, "pattern_combo") and self.pattern_combo is not None:
            self.pattern_combo.setToolTip(self.tr("Quickly apply an extension mask"))
        if hasattr(self, "content_regex_cb") and self.content_regex_cb is not None:
            self.content_regex_cb.setText(self.tr("Regex"))
        if hasattr(self, "case_cb") and self.case_cb is not None:
            self.case_cb.setText(self.tr("Case sensitive"))
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
        if hasattr(self, "size_min_le") and self.size_min_le is not None:
            self.size_min_le.setPlaceholderText(self.tr("from"))
        if hasattr(self, "size_max_le") and self.size_max_le is not None:
            self.size_max_le.setPlaceholderText(self.tr("to"))

    def retranslateUi(self) -> None:  # type: ignore[override]
        """Update all texts on language change."""
        self.setWindowTitle(self.tr("Advanced file search"))
        self._translate_labels()
        self._translate_buttons()
        self._translate_status()
        self._translate_placeholders()

    def _update_buttons(self):
        """Enable/disable buttons based on current selection."""
        has_selection = bool(self.table.selectionModel().selectedRows())
        self.add_link_btn.setEnabled(has_selection)
        self.open_folder_btn.setEnabled(has_selection)

    def _get_full_file_path(self, row):
        """Return the full file path for the supplied table row."""
        idx_name = self.model.index(row, 0)
        idx_path = self.model.index(row, 1)
        filename = self.model.data(idx_name, Qt.ItemDataRole.DisplayRole) or ""
        folder_path = self.model.data(idx_path, Qt.ItemDataRole.DisplayRole) or ""

        # Combine folder path and filename
        full_path = Path(folder_path) / filename

        # Normalize
        full_path = Path(full_path).resolve()

        return str(full_path)

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
                    ["explorer", "/select,", str(file_path_obj)], shell=False
                )
            elif system == "Darwin":  # macOS
                # macOS: use `open -R`
                subprocess.run(["open", "-R", str(file_path_obj)], check=True)
            elif system == "Linux":
                # Linux: attempt several file managers sequentially
                try:
                    subprocess.run(
                        ["nautilus", "--select", str(file_path_obj)], check=True
                    )
                except (subprocess.CalledProcessError, FileNotFoundError):
                    try:
                        subprocess.run(
                            ["dolphin", "--select", str(file_path_obj)], check=True
                        )
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        try:
                            subprocess.run(
                                ["thunar", str(file_path_obj.parent)], check=True
                            )
                        except (subprocess.CalledProcessError, FileNotFoundError):
                            try:
                                subprocess.run(
                                    ["pcmanfm", str(file_path_obj.parent)], check=True
                                )
                            except (subprocess.CalledProcessError, FileNotFoundError):
                                folder_path = file_path_obj.parent
                                subprocess.run(
                                    ["xdg-open", str(folder_path)], check=True
                                )
            else:
                folder_path = file_path_obj.parent
                subprocess.run(["xdg-open", str(folder_path)], check=True)

        except subprocess.CalledProcessError as e:
            self.show_warning(
                self.tr("Failed to open file in explorer: {error}").format(error=str(e))
            )
        except Exception as e:
            self.show_warning(self.tr("Unexpected error: {error}").format(error=str(e)))

    def _setup_defaults(self):
        """Reset default values."""
        self.size_min_le.clear()
        self.size_max_le.clear()

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

        # Validate content regular expression when regex mode enabled
        content_pattern = self.content_le.text().strip()
        if content_pattern and self.content_regex_cb.isChecked():
            try:
                flags = 0 if self.case_cb.isChecked() else re.IGNORECASE
                re.compile(content_pattern, flags)
            except re.error as e:
                self.show_warning(
                    self.tr("Invalid regular expression for content: {error}").format(
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
        self.search_worker.signals.result_found.connect(self._add_result)
        self.search_worker.signals.search_finished.connect(self._on_search_finished)
        self.search_worker.signals.error_occurred.connect(self._on_search_error)

        self.threadpool.start(self.search_worker)

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
            "size_min": int(self.size_min_le.text())
            if self.size_min_le.text()
            else None,
            "size_max": int(self.size_max_le.text())
            if self.size_max_le.text()
            else None,
            "date_from": self.date_from_de.date().toPyDate(),
            "date_to": self.date_to_de.date().toPyDate(),
            "hidden": self.hidden_cb.isChecked(),
            "readonly": self.readonly_cb.isChecked(),
            "content": self.content_le.text().strip(),
            "content_regex": self.content_regex_cb.isChecked(),
            "case_sensitive": self.case_cb.isChecked(),
        }

    def _add_result(self, file_path: str, _ext: str = ""):
        """Append a search result to the table."""
        try:
            file_path_obj = Path(file_path)
            file_stat = file_path_obj.stat()
            size_kb = file_stat.st_size // 1024
            mtime = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(file_stat.st_mtime)
            )

            # Mark content column if content filter is used
            has_content = "✓" if self.content_le.text().strip() else ""

            # Row data
            filename = file_path_obj.name
            folder_path = str(file_path_obj.parent)
            self.model.add_result(filename, folder_path, size_kb, mtime, has_content)
        except OSError as e:
            logger.warning(
                "Failed to gather information for file %s: %s",
                file_path,
                e,
                exc_info=True,
            )
        # Refresh buttons when rows appear
        self._update_buttons()

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
        self.is_searching = False
        self.search_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        count = self.model.rowCount()
        self.status_label.setText(
            self.tr("Search finished. Files found: {count}").format(count=count)
        )
        self._update_buttons()
