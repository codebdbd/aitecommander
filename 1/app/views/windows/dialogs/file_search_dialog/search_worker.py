import os
import re
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QRunnable

from .common import matches_criteria as _matches_common
from .search_signals import SearchSignals


class FileSearchWorker(QRunnable):
    """Worker running file search in a dedicated thread."""

    _TR_CONTEXT = "FileSearchWorker"

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.signals = SearchSignals()
        self._stop_requested = False

    def stop(self):
        """Request search cancellation."""
        self._stop_requested = True

    def _validate_root_path(self):
        """Validate and return root path."""
        _tr = QCoreApplication.translate
        root_cfg = self.config.get("root")
        if not isinstance(root_cfg, str) or not root_cfg.strip():
            self.signals.error_occurred.emit(
                _tr(self._TR_CONTEXT, "Invalid search root path.")
            )
            return None

        try:
            root_path = Path(root_cfg).resolve(strict=False)
        except Exception:
            root_path = Path(root_cfg)

        if not root_path.exists() or not root_path.is_dir():
            self.signals.error_occurred.emit(
                _tr(
                    self._TR_CONTEXT,
                    "Root path not found or is not a directory: {path}",
                ).format(path=root_cfg)
            )
            return None
        return root_path

    def _compile_regexes(self):
        """Compile regular expressions for search."""
        name_regex = None
        if self.config["regex_name"]:
            name_regex = re.compile(self.config["regex_name"])

        content_regex = None
        if self.config["content"]:
            flags = 0 if self.config["case_sensitive"] else re.IGNORECASE
            if self.config["content_regex"]:
                content_regex = re.compile(self.config["content"], flags)

        return name_regex, content_regex

    def _get_search_constraints(self):
        """Get search constraints from config."""
        max_depth = self.config.get("max_depth")
        allowed_exts = self.config.get("allowed_exts")
        max_file_size_mb = self.config.get("max_file_size_mb")
        max_file_size_bytes = (
            int(max_file_size_mb) * 1024 * 1024 if max_file_size_mb else None
        )
        return max_depth, allowed_exts, max_file_size_bytes

    def _should_limit_depth(self, root, base_depth, max_depth, dirs):
        """Check if depth limit reached and update dirs."""
        if isinstance(max_depth, int) and max_depth >= 0:
            current_depth = len(Path(root).parts) - base_depth
            if current_depth >= max_depth:
                dirs[:] = []

    def _is_extension_allowed(self, filepath, allowed_exts):
        """Check if file extension is allowed."""
        if not allowed_exts:
            return True
        try:
            ext = filepath.suffix.lower().lstrip(".")
        except Exception:
            ext = ""
        return ext in set(x.lower().lstrip(".") for x in allowed_exts)

    def _is_size_allowed(self, filepath, max_file_size_bytes):
        """Check if file size is within limit."""
        if max_file_size_bytes is None:
            return True
        try:
            return filepath.stat().st_size <= max_file_size_bytes
        except OSError:
            return False

    def _process_files(
        self, root, files, name_regex, content_regex, allowed_exts, max_file_size_bytes
    ):
        """Process files in directory."""
        for filename in files:
            if self._stop_requested:
                break

            filepath = Path(root) / filename

            if not self._is_extension_allowed(filepath, allowed_exts):
                continue

            if not self._is_size_allowed(filepath, max_file_size_bytes):
                continue

            if _matches_common(
                self.config, str(filepath), filename, name_regex, content_regex
            ):
                ext = filepath.suffix.lower()
                self.signals.result_found.emit(str(filepath), ext)

    def run(self):
        """Entry point for the background search."""
        try:
            root_path = self._validate_root_path()
            if root_path is None:
                self.signals.search_finished.emit()
                return

            name_regex, content_regex = self._compile_regexes()
            max_depth, allowed_exts, max_file_size_bytes = (
                self._get_search_constraints()
            )
            base_depth = len(root_path.parts)

            for root, dirs, files in os.walk(str(root_path)):
                if self._stop_requested:
                    break

                self._should_limit_depth(root, base_depth, max_depth, dirs)
                self._process_files(
                    root,
                    files,
                    name_regex,
                    content_regex,
                    allowed_exts,
                    max_file_size_bytes,
                )

        except Exception as e:
            _tr = QCoreApplication.translate
            self.signals.error_occurred.emit(
                _tr(self._TR_CONTEXT, "Error during search: {error}").format(
                    error=str(e)
                )
            )
        finally:
            self.signals.search_finished.emit()
