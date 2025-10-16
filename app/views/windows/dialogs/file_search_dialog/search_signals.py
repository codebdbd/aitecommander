from PyQt6.QtCore import QObject, pyqtSignal

"""Signals emitted by the file search worker."""


class SearchSignals(QObject):
    """Qt signals used by `FileSearchWorker`."""

    result_found = pyqtSignal(
        str, str
    )  # file_path, found_content; pass empty string when content is not needed
    search_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
