"""
Локальные сигналы для LinkDialog.
Выделены в отдельный модуль для повторного использования и облегчения тестирования.
"""
from PyQt6.QtCore import QObject, pyqtSignal


class LinkDialogSignals(QObject):
    """Локальные сигналы для LinkDialog (совместимы с легаси-слотами)."""

    link_info_finished: pyqtSignal = pyqtSignal(dict)
    simple_error: pyqtSignal = pyqtSignal(str)
