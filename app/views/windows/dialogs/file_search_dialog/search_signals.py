from PyQt6.QtCore import QObject, pyqtSignal

"""Signals emitted by the file search worker."""


class SearchSignals(QObject):
    """Qt signals used by `FileSearchWorker`."""

    # Batch results signal: list of tuples (filename, folder_path, size_kb, mtime_str, has_content)
    results_batch = pyqtSignal(list)
    
    # Progress signal: (files_processed, directories_processed)
    progress_update = pyqtSignal(int, int)

    # Skipped files signal: (skipped_big, skipped_binary, skipped_permission)
    skipped_updated = pyqtSignal(int, int, int)
    
    search_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
