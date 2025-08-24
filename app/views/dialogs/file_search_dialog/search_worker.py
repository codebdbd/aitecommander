import os
import re

from PyQt6.QtCore import QRunnable

from .common import matches_criteria as _matches_common
from .search_signals import SearchSignals


class FileSearchWorker(QRunnable):
    """Worker для выполнения поиска в отдельном потоке"""

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.signals = SearchSignals()
        self._stop_requested = False

    def stop(self):
        """Запрос на остановку поиска"""
        self._stop_requested = True

    def run(self):
        """Основная функция поиска"""
        try:
            # Компиляция регулярных выражений
            name_regex = None
            if self.config["regex_name"]:
                name_regex = re.compile(self.config["regex_name"])

            content_regex = None
            if self.config["content"]:
                flags = 0 if self.config["case_sensitive"] else re.IGNORECASE
                if self.config["content_regex"]:
                    content_regex = re.compile(self.config["content"], flags)

            # Обход файловой системы
            for root, dirs, files in os.walk(self.config["root"]):
                if self._stop_requested:
                    break

                for filename in files:
                    if self._stop_requested:
                        break

                    filepath = os.path.join(root, filename)

                    if _matches_common(
                        self.config, filepath, filename, name_regex, content_regex
                    ):
                        ext = os.path.splitext(filepath)[1].lower()
                        self.signals.result_found.emit(filepath, ext)

        except Exception as e:
            self.signals.error_occurred.emit(f"Ошибка при поиске: {str(e)}")
        finally:
            self.signals.search_finished.emit()

    def _matches_criteria(
        self, filepath: str, filename: str, name_regex, content_regex
    ) -> bool:
        """DEPRECATED: вызывать _matches_common напрямую из run()."""
        return _matches_common(
            self.config, filepath, filename, name_regex, content_regex
        )
