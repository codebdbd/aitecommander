"""
Диалог восстановления базы данных из резервной копии.

Исправления:
- Наследование от BaseDialog
- Убран отладочный код (print)
- Добавлено логирование
- Улучшена обработка ошибок
"""

import datetime
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QDialogButtonBox, QListWidget, QVBoxLayout

from app.config_data import app_config

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


class RestoreDbDialog(BaseDialog):
    """Диалог для восстановления базы данных из резервной копии."""

    def __init__(self, backup_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Восстановить базу из резервной копии")
        self.resize(500, 300)
        self.setModal(True)

        # Используем переданную директорию или получаем стандартную из PathConfig
        self.paths = app_config.paths
        self.backup_dir = backup_dir or self.paths.get_backups_dir()
        self.selected_backup = None

        self._init_ui()
        self._populate_list()

    def _init_ui(self) -> None:
        """Инициализирует пользовательский интерфейс."""
        layout = QVBoxLayout(self)

        # Список резервных копий
        self.list_widget = QListWidget(self)
        layout.addWidget(self.list_widget)

        # Кнопки
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        # Настройка кнопок
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Восстановить")

        cancel_btn = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("Отмена")

        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        # Подключение сигналов
        self.list_widget.currentRowChanged.connect(self._update_ok_state)
        self.list_widget.itemDoubleClicked.connect(self.accept)

    def _populate_list(self) -> None:
        """Заполняет список резервных копий."""
        self.list_widget.clear()

        try:
            # Создаем директорию если не существует
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Поиск резервных копий в: {self.backup_dir}")

            # Ищем файлы резервных копий
            backups = sorted(self.backup_dir.glob("links_*.db"), reverse=True)
            logger.debug(f"Найдено резервных копий: {len(backups)}")

            # Проверяем наличие файла links.db.bak
            single_backup_path = self.paths.get_db_backup_path()
            single_backup_exists = (
                single_backup_path.exists() and single_backup_path.stat().st_size > 0
            )

            if not backups and not single_backup_exists:
                self._show_no_backups_message()
            else:
                # Добавляем одиночную резервную копию в начало списка, если она существует
                if single_backup_exists:
                    self._add_single_backup_item(single_backup_path)

                if backups:
                    self._populate_backup_list(backups)
                else:
                    # Если в наличии только одиночная резервная копия — выделяем ее
                    if single_backup_exists and self.list_widget.count() > 0:
                        self.list_widget.setEnabled(True)
                        self.list_widget.setCurrentRow(0)
                        self._update_ok_state()

        except Exception as e:
            logger.error(f"Ошибка при поиске резервных копий: {e}")
            self._show_error_message(f"Ошибка при поиске резервных копий: {str(e)}")

    def _show_no_backups_message(self) -> None:
        """Показывает сообщение об отсутствии резервных копий."""
        self.list_widget.addItem("Резервные копии не найдены")
        self.list_widget.setEnabled(False)
        logger.info("Резервные копии не найдены")

    def _add_single_backup_item(self, backup_path: Path) -> None:
        """Добавляет одиночную резервную копию links.db.bak в список с визуальным выделением."""
        try:
            # Проверяем размер файла
            if backup_path.stat().st_size == 0:
                logger.warning(f"Пустой файл резервной копии: {backup_path.name}")
                return

            # Получаем дату и время создания файла
            stat = backup_path.stat()
            creation_time = datetime.datetime.fromtimestamp(stat.st_mtime)
            time_str = creation_time.strftime("%d.%m.%Y %H:%M")

            # Форматируем отображение с выделением и датой создания
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            label = f"{backup_path.name} — до подключения новой базы: {time_str} ({size_mb:.1f} МБ)"

            # Добавляем элемент в список
            self.list_widget.addItem(label)

            # Визуально выделяем элемент (берем последний добавленный элемент)
            item_count = self.list_widget.count()
            if item_count > 0:
                item = self.list_widget.item(item_count - 1)
                # Устанавливаем жирный шрифт для выделения
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            logger.debug(f"Добавлена одиночная резервная копия: {backup_path.name}")

        except Exception as e:
            logger.warning(f"Ошибка при обработке файла {backup_path.name}: {e}")

    def _populate_backup_list(self, backups: list) -> None:
        """Заполняет список найденными резервными копиями."""
        for backup in backups:
            try:
                # Проверяем размер файла
                if backup.stat().st_size == 0:
                    logger.warning(f"Пустой файл резервной копии: {backup.name}")
                    continue

                # Форматируем отображение
                dt_str = self._parse_datetime(backup.name)
                size_mb = backup.stat().st_size / (1024 * 1024)

                if dt_str:
                    label = f"{backup.name} — {dt_str} ({size_mb:.1f} МБ)"
                else:
                    label = f"{backup.name} ({size_mb:.1f} МБ)"

                self.list_widget.addItem(label)
                logger.debug(f"Добавлена резервная копия: {backup.name}")

            except Exception as e:
                logger.warning(f"Ошибка при обработке файла {backup.name}: {e}")
                continue

        if self.list_widget.count() > 0:
            self.list_widget.setEnabled(True)
            self.list_widget.setCurrentRow(0)  # Выбираем самую новую
        else:
            self._show_no_backups_message()

        self._update_ok_state()

    def _show_error_message(self, message: str) -> None:
        """Показывает сообщение об ошибке."""
        self.list_widget.addItem(f"Ошибка: {message}")
        self.list_widget.setEnabled(False)

    def _parse_datetime(self, filename: str) -> Optional[str]:
        """Парсит дату и время из имени файла резервной копии."""
        try:
            # Убираем префикс и суффикс
            base = filename.replace("links_", "").replace(".db", "")

            # Пробуем разные форматы
            formats = [
                "%Y%m%d_%H%M%S_%f",  # С микросекундами
                "%Y%m%d_%H%M%S",  # Без микросекунд
                "%Y-%m-%d_%H-%M-%S",  # Альтернативный формат
            ]

            for fmt in formats:
                try:
                    dt = datetime.datetime.strptime(base, fmt)
                    return dt.strftime("%d.%m.%Y %H:%M:%S")
                except ValueError:
                    continue

            logger.debug(f"Не удалось распарсить дату из имени файла: {filename}")
            return None

        except Exception as e:
            logger.debug(f"Ошибка при парсинге даты из {filename}: {e}")
            return None

    def get_selected_backup(self) -> Optional[Path]:
        """Возвращает путь к выбранной резервной копии."""
        if not self.list_widget.isEnabled():
            return None

        row = self.list_widget.currentRow()
        if row < 0:
            return None

        try:
            # Проверяем наличие одиночной резервной копии
            single_backup_path = self.paths.get_db_backup_path()
            single_backup_exists = (
                single_backup_path.exists() and single_backup_path.stat().st_size > 0
            )

            # Получаем список автоматических резервных копий
            backups = sorted(self.backup_dir.glob("links_*.db"), reverse=True)
            # Фильтруем пустые файлы
            valid_backups = [b for b in backups if b.stat().st_size > 0]

            # Если есть одиночная резервная копия, она будет первой в списке
            if single_backup_exists:
                # Если выбрана первая строка (одиночная резервная копия)
                if row == 0:
                    logger.info(
                        f"Выбрана одиночная резервная копия: {single_backup_path.name}"
                    )
                    return single_backup_path
                else:
                    # Смещаем индекс для автоматических резервных копий
                    adjusted_row = row - 1
                    if adjusted_row >= len(valid_backups):
                        logger.warning(f"Неверный индекс резервной копии: {row}")
                        return None

                    selected = valid_backups[adjusted_row]
                    logger.info(
                        f"Выбрана автоматическая резервная копия: {selected.name}"
                    )
                    return selected
            else:
                # Если нет одиночной резервной копии, работаем как раньше
                if row >= len(valid_backups):
                    logger.warning(f"Неверный индекс резервной копии: {row}")
                    return None

                selected = valid_backups[row]
                logger.info(f"Выбрана резервная копия: {selected.name}")
                return selected

        except Exception as e:
            logger.error(f"Ошибка при получении выбранной резервной копии: {e}")
            return None

    def _update_ok_state(self) -> None:
        """Обновляет состояние кнопки OK."""
        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        enabled = (
            self.list_widget.isEnabled()
            and self.list_widget.currentRow() >= 0
            and self.list_widget.count() > 0
        )
        ok_btn.setEnabled(enabled)

    def accept(self) -> None:
        """Подтверждение выбора резервной копии."""
        selected_backup = self.get_selected_backup()

        if not selected_backup:
            self.show_warning(
                "Резервная копия не выбрана.",
                "Требуется выбор резервной копии",
                informative_text="Выберите файл из списка и нажмите 'Импортировать'. Если список пуст, проверьте каталог бэкапов.",
            )
            return

        # Дополнительное подтверждение
        reply = self.ask_confirmation(
            "Восстановить базу данных из выбранной резервной копии?",
            "Восстановление базы данных",
            informative_text=(
                "Данные текущей базы будут полностью заменены содержимым бэкапа. \n"
                "Операция необратима. Рекомендуется предварительно создать текущий бэкап."
            ),
            details=(
                f"Путь: {selected_backup}\n"
                f"Имя: {selected_backup.name}\n"
                f"Размер: {selected_backup.stat().st_size / (1024 * 1024):.1f} МБ"
            ),
        )

        if reply:
            self.selected_backup = selected_backup
            super().accept()

    def get_result(self) -> Optional[Path]:
        """Возвращает выбранную резервную копию после закрытия диалога."""
        return self.selected_backup
