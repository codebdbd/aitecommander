from PyQt6.QtCore import QObject, pyqtSignal


class SearchSignals(QObject):
    """Сигналы для worker'а поиска файлов"""
    result_found = pyqtSignal(str, str)  # file_path, found_content; если found_content не нужен — передавать пустую строку
    search_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
