"""Local signals for `LinkDialog` to enable reuse and easier testing."""

from PyQt6.QtCore import QObject, pyqtSignal


class LinkDialogSignals(QObject):
    """Local signals for `LinkDialog` (compatible with legacy slots)."""

    link_info_finished: pyqtSignal = pyqtSignal(dict)
    simple_error: pyqtSignal = pyqtSignal(str)
