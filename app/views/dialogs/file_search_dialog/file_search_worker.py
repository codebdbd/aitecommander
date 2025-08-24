"""
Worker для выполнения поиска файлов в отдельном потоке.
"""

import fnmatch
import os
import re
from datetime import datetime

from PyQt6.QtCore import QRunnable

from .search_signals import SearchSignals


class FileSearchWorker(QRunnable):
    """Worker для поиска файлов в отдельном потоке"""

    def __init__(self, search_params):
        super().__init__()
        self.signals = SearchSignals()
        self.search_params = search_params
        self.is_cancelled = False

    def cancel(self):
        """Отменить поиск"""
        self.is_cancelled = True

    def run(self):
        """Основной метод поиска"""
        try:
            self._perform_search()
        except Exception as e:
            self.signals.error_occurred.emit(str(e))
        finally:
            self.signals.search_finished.emit()

    def _perform_search(self):
        """Выполнить поиск с заданными параметрами"""
        search_path = self.search_params.get("path", "")
        if not search_path or not os.path.exists(search_path):
            self.signals.error_occurred.emit("Неверный путь для поиска")
            return

        for root, dirs, files in os.walk(search_path):
            if self.is_cancelled:
                break

            for file in files:
                if self.is_cancelled:
                    break

                file_path = os.path.join(root, file)

                match_result = self._matches_criteria(file_path, file)
                if match_result:
                    found_content = (
                        match_result if isinstance(match_result, str) else ""
                    )
                    self.signals.result_found.emit(file_path, found_content)

    def _matches_criteria(self, file_path, filename):
        """Проверить, соответствует ли файл критериям поиска"""
        try:
            # Проверка маски имени файла
            if self.search_params.get("name_mask"):
                if not fnmatch.fnmatch(
                    filename.lower(), self.search_params["name_mask"].lower()
                ):
                    return False

            # Проверка регулярного выражения для имени
            if self.search_params.get("name_regex"):
                pattern = self.search_params["name_regex"]
                flags = (
                    0
                    if self.search_params.get("case_sensitive", False)
                    else re.IGNORECASE
                )
                if not re.search(pattern, filename, flags):
                    return False

            # Проверка размера файла
            if (
                self.search_params.get("min_size") is not None
                or self.search_params.get("max_size") is not None
            ):
                try:
                    file_size = os.path.getsize(file_path) / 1024  # размер в КБ
                    if self.search_params.get("min_size") is not None:
                        if file_size < self.search_params["min_size"]:
                            return False
                    if self.search_params.get("max_size") is not None:
                        if file_size > self.search_params["max_size"]:
                            return False
                except OSError:
                    return False

            # Проверка даты модификации
            if self.search_params.get("date_from") or self.search_params.get("date_to"):
                try:
                    mod_time = datetime.fromtimestamp(
                        os.path.getmtime(file_path)
                    ).date()
                    if self.search_params.get("date_from"):
                        if mod_time < self.search_params["date_from"]:
                            return False
                    if self.search_params.get("date_to"):
                        if mod_time > self.search_params["date_to"]:
                            return False
                except OSError:
                    return False

            # Проверка атрибутов файла
            if not self.search_params.get("include_hidden", True):
                if self._is_hidden_file(file_path):
                    return False

            if self.search_params.get("readonly_only", False):
                if not self._is_readonly_file(file_path):
                    return False

            # Поиск по содержимому
            found_content = ""
            if self.search_params.get("content_text"):
                content_result = self._search_in_content(file_path)
                if not content_result:
                    return False
                elif isinstance(content_result, str):
                    found_content = content_result

            # Возвращаем найденный контент или True
            return found_content if found_content else True

        except Exception:
            return False

    def _is_hidden_file(self, file_path):
        """Проверить, является ли файл скрытым"""
        try:
            import stat

            return bool(
                os.stat(file_path).st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN
            )
        except (AttributeError, OSError):
            # Для Unix-систем или если атрибуты недоступны
            return os.path.basename(file_path).startswith(".")

    def _is_readonly_file(self, file_path):
        """Проверить, является ли файл только для чтения"""
        try:
            return not os.access(file_path, os.W_OK)
        except OSError:
            return False

    def _search_in_content(self, file_path):
        """Поиск текста в содержимом файла. Возвращает найденный фрагмент или False"""
        try:
            content_text = self.search_params.get("content_text", "")
            is_regex = self.search_params.get("content_regex", False)
            case_sensitive = self.search_params.get("case_sensitive", False)

            # Пробуем различные кодировки
            encodings = ["utf-8", "cp1251", "latin-1"]

            for encoding in encodings:
                try:
                    with open(file_path, "r", encoding=encoding, errors="ignore") as f:
                        content = f.read()

                    if is_regex:
                        flags = 0 if case_sensitive else re.IGNORECASE
                        match = re.search(content_text, content, flags)
                        if match:
                            # Возвращаем найденный фрагмент с контекстом
                            start = max(0, match.start() - 20)
                            end = min(len(content), match.end() + 20)
                            return (
                                content[start:end]
                                .strip()
                                .replace("\n", " ")
                                .replace("\r", "")
                            )
                        return False
                    else:
                        search_text = (
                            content_text if case_sensitive else content_text.lower()
                        )
                        search_content = content if case_sensitive else content.lower()

                        pos = search_content.find(search_text)
                        if pos >= 0:
                            # Возвращаем найденный фрагмент с контекстом
                            start = max(0, pos - 20)
                            end = min(len(content), pos + len(content_text) + 20)
                            return (
                                content[start:end]
                                .strip()
                                .replace("\n", " ")
                                .replace("\r", "")
                            )
                        return False

                except (UnicodeDecodeError, UnicodeError):
                    continue
                except Exception:
                    break

            return False

        except Exception:
            return False
