import os
import re
from pathlib import Path

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
            # Валидация корневого каталога
            root_cfg = self.config.get("root")
            if not isinstance(root_cfg, str) or not root_cfg.strip():
                self.signals.error_occurred.emit("Некорректный корневой путь поиска")
                self.signals.search_finished.emit()
                return
            try:
                root_path = Path(root_cfg).resolve(strict=False)
            except Exception:
                root_path = Path(root_cfg)
            if not root_path.exists() or not root_path.is_dir():
                self.signals.error_occurred.emit(
                    f"Корневой путь не найден или не является каталогом: {root_cfg}"
                )
                self.signals.search_finished.emit()
                return

            # Компиляция регулярных выражений
            name_regex = None
            if self.config["regex_name"]:
                name_regex = re.compile(self.config["regex_name"])

            content_regex = None
            if self.config["content"]:
                flags = 0 if self.config["case_sensitive"] else re.IGNORECASE
                if self.config["content_regex"]:
                    content_regex = re.compile(self.config["content"], flags)

            # Параметры ограничений (опциональные)
            max_depth = self.config.get("max_depth")  # int | None
            allowed_exts = self.config.get("allowed_exts")  # Iterable[str] | None
            # Хард-лимит файла применяется только если явно указан размер в конфиге
            max_file_size_mb = self.config.get("max_file_size_mb")  # int | None
            max_file_size_bytes = (
                int(max_file_size_mb) * 1024 * 1024 if max_file_size_mb else None
            )

            base_depth = len(root_path.parts)

            # Обход файловой системы
            for root, dirs, files in os.walk(str(root_path)):
                if self._stop_requested:
                    break

                # Ограничение глубины обхода, если задано
                if isinstance(max_depth, int) and max_depth >= 0:
                    current_depth = len(Path(root).parts) - base_depth
                    if current_depth >= max_depth:
                        # Не углубляемся дальше
                        dirs[:] = []

                for filename in files:
                    if self._stop_requested:
                        break

                    filepath = os.path.join(root, filename)

                    # Фильтр по расширениям (если задан белый список)
                    if allowed_exts:
                        try:
                            ext = os.path.splitext(filename)[1].lower().lstrip(".")
                        except Exception:
                            ext = ""
                        if ext not in set(x.lower().lstrip(".") for x in allowed_exts):
                            continue

                    # Проверка лимита размера файла перед дальнейшей обработкой
                    if max_file_size_bytes is not None:
                        try:
                            if os.path.getsize(filepath) > max_file_size_bytes:
                                continue
                        except OSError:
                            continue

                    if _matches_common(
                        self.config, filepath, filename, name_regex, content_regex
                    ):
                        ext = os.path.splitext(filepath)[1].lower()
                        self.signals.result_found.emit(filepath, ext)

        except Exception as e:
            self.signals.error_occurred.emit(f"Ошибка при поиске: {str(e)}")
        finally:
            self.signals.search_finished.emit()
