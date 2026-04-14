"""Mixin handling the "Browse" button in `LinkDialogHandlers`."""

import logging
import os
from pathlib import Path

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QFileDialog

from app.config_data.runtime_config import runtime_app_config as app_config
from app.models import LinkType
from app.utils.links.link_parser import parse_lnk

logger = logging.getLogger(__name__)

_TR_CONTEXT = "FileDialogMixin"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


PROGRAM_FILES = QCoreApplication.translate("FileDialogMixin", "Programs (*.exe *.bat *.com *.msi *.lnk)")
SCRIPT_FILES = QCoreApplication.translate("FileDialogMixin", "Scripts (*.py *.ps1 *.vbs *.js *.cmd)")
DOC_FILES = QCoreApplication.translate("FileDialogMixin", 
    "Documents (*.txt *.pdf *.doc *.docx *.xls *.xlsx *.csv *.jpg *.png *.jpeg *.bmp *.gif);;All files (*)"
)

# File dialog configuration per link type
BROWSE_CONFIG = {
    "program": {
        "title": QCoreApplication.translate("FileDialogMixin", "Select program"),
        "mode": QFileDialog.FileMode.ExistingFile,
        "filter": PROGRAM_FILES,
    },
    "script": {
        "title": QCoreApplication.translate("FileDialogMixin", "Select script"),
        "mode": QFileDialog.FileMode.ExistingFile,
        "filter": SCRIPT_FILES,
    },
    "folder": {
        "title": QCoreApplication.translate("FileDialogMixin", "Select folder"),
        "mode": QFileDialog.FileMode.Directory,
        "filter": None,
    },
    "file": {
        "title": QCoreApplication.translate("FileDialogMixin", "Select file"),
        "mode": QFileDialog.FileMode.ExistingFile,
        "filter": DOC_FILES,
    },
}


class FileDialogMixin:
    def _on_browse(self) -> None:
        """Handle the "Browse" button click."""
        lt = LinkType.from_value(self.dialog.link_type)
        path = ""

        # Obtain default path from config
        default_paths = app_config.settings.get_default_browse_paths()
        start_dir = default_paths.get(lt.value, "")

        # Handle paths: do not validate GUID-style paths via Path.exists()
        if start_dir:
            if start_dir.startswith("::"):
                # GUID path for "This PC" — leave untouched
                pass
            else:
                # Regular path — expand variables and validate existence
                start_dir = os.path.expandvars(start_dir)
                if not Path(start_dir).exists():
                    start_dir = ""  # Fallback to "This PC"

        # Create dialog with explicit directory selection
        dialog = QFileDialog(self.dialog.parent())
        cfg = BROWSE_CONFIG.get(lt.value) or {
            "title": QCoreApplication.translate("FileDialogMixin", "Select file"),
            "mode": QFileDialog.FileMode.ExistingFile,
            "filter": DOC_FILES,
        }
        dialog.setFileMode(cfg["mode"])
        dialog.setWindowTitle(cfg["title"])
        if cfg.get("filter"):
            dialog.setNameFilter(cfg["filter"])

        # Explicitly set starting directory
        if start_dir:
            dialog.setDirectory(start_dir)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                path = selected_files[0]
            else:
                path = ""
        else:
            path = ""

        if path:
            normalized_path = path.replace("/", "\\")

            # For "program" keep `.lnk` path as-is to preserve shortcut identity
            # (name/icon/source). We only prefill args from shortcut metadata.
            if lt == LinkType.PROGRAM and normalized_path.lower().endswith(".lnk"):
                try:
                    lnk_info = parse_lnk(normalized_path)
                except (
                    FileNotFoundError,
                    PermissionError,
                    OSError,
                    ValueError,
                    RuntimeError,
                ) as e:
                    # Log parsing issue but do not interrupt file selection
                    logger.warning(
                        "parse_lnk: failed to parse shortcut '%s': %s",
                        normalized_path,
                        e,
                    )
                    lnk_info = None
                if lnk_info:
                    # Populate args field when shortcut specifies arguments
                    if (
                        lnk_info.get("args")
                        and not self.dialog.ui.get_widget("args_le").text().strip()
                    ):
                        self.dialog.ui.set_widget_value("args_le", lnk_info["args"])

            self.dialog.ui.set_widget_value("url_le", normalized_path)

            name_widget = self.dialog.ui.get_widget("name_le")
            if not name_widget.text().strip():
                name = Path(normalized_path).name
                if lt == LinkType.PROGRAM or name.lower().endswith(".lnk"):
                    name = Path(name).stem
                name_widget.setText(name)
