import os
import re
import time
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QRunnable

from .common import matches_criteria as _matches_common
from .search_signals import SearchSignals

# Batch size for sending results to GUI
_BATCH_SIZE = 50
# Progress update interval (seconds)
_PROGRESS_UPDATE_INTERVAL = 0.1


class FileSearchWorker(QRunnable):
    """Worker running file search in a dedicated thread."""

    _TR_CONTEXT = "FileSearchWorker"

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.signals = SearchSignals()
        self._stop_requested = False
        self._results_batch = []  # Accumulator for batch sending
        self._files_processed = 0
        self._dirs_processed = 0
        self._last_progress_time = 0.0

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

        return name_regex

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

    def _flush_batch(self):
        """Send accumulated results to GUI."""
        if self._results_batch:
            self.signals.results_batch.emit(self._results_batch.copy())
            self._results_batch.clear()
    
    def _add_result(self, filepath: Path):
        """Add result to batch and flush if needed."""
        try:
            # Add to batch: (path,)
            self._results_batch.append((str(filepath),))
            
            # Flush batch if it reached the limit
            if len(self._results_batch) >= _BATCH_SIZE:
                self._flush_batch()
                
        except OSError:
            pass  # Skip files that can't be stat'ed
    
    def _update_progress(self, force: bool = False):
        """Send progress update if enough time has passed."""
        current_time = time.time()
        if force or (current_time - self._last_progress_time) >= _PROGRESS_UPDATE_INTERVAL:
            self.signals.progress_update.emit(self._files_processed, self._dirs_processed)
            self._last_progress_time = current_time
    
    def _process_files(
        self, root, files, name_regex, allowed_exts, max_file_size_bytes
    ):
        """Process files in directory."""
        for filename in files:
            if self._stop_requested:
                break

            filepath = Path(root) / filename
            self._files_processed += 1

            if not self._is_extension_allowed(filepath, allowed_exts):
                continue

            if not self._is_size_allowed(filepath, max_file_size_bytes):
                continue

            if _matches_common(self.config, str(filepath), filename, name_regex):
                self._add_result(filepath)
            
            # Update progress periodically
            if self._files_processed % 100 == 0:
                self._update_progress()

    def run(self):
        """Entry point for the background search."""
        try:
            root_path = self._validate_root_path()
            if root_path is None:
                self.signals.search_finished.emit()
                return

            name_regex = self._compile_regexes()
            max_depth, allowed_exts, max_file_size_bytes = (
                self._get_search_constraints()
            )
            base_depth = len(root_path.parts)

            for root, dirs, files in os.walk(str(root_path)):
                if self._stop_requested:
                    break

                self._dirs_processed += 1
                self._should_limit_depth(root, base_depth, max_depth, dirs)
                self._process_files(
                    root,
                    files,
                    name_regex,
                    allowed_exts,
                    max_file_size_bytes,
                )
            
            # Flush any remaining results
            self._flush_batch()
            # Send final progress
            self._update_progress(force=True)

        except Exception as e:
            # Flush any pending results before error
            self._flush_batch()
            _tr = QCoreApplication.translate
            self.signals.error_occurred.emit(
                _tr(self._TR_CONTEXT, "Error during search: {error}").format(
                    error=str(e)
                )
            )
        finally:
            self.signals.search_finished.emit()
