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
from typing import Any, Optional

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from app.config_data import app_config
from app.views.common.retranslatable import ReTranslatable

from .base_dialog import BaseDialog

_TR_CONTEXT = "RestoreDbDialog"


def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)


_LIST_ITEM_TEMPLATES: dict[str, str] = {
    "no_backups": QT_TRANSLATE_NOOP(_TR_CONTEXT, "No backups found"),
    "single_backup": QT_TRANSLATE_NOOP(
        _TR_CONTEXT,
        "{backup_name} — before attaching new database: {timestamp} ({size} MB)",
    ),
    "auto_backup_with_timestamp": QT_TRANSLATE_NOOP(
        _TR_CONTEXT, "{backup_name} — {timestamp} ({size} MB)"
    ),
    "auto_backup_without_timestamp": QT_TRANSLATE_NOOP(
        _TR_CONTEXT,
        "{backup_name} ({size} MB)",
    ),
    "error": QT_TRANSLATE_NOOP(_TR_CONTEXT, "Error: {details}"),
}

# lupdate hints so pylupdate6 picks up template strings
if False:  # pragma: no cover
    QCoreApplication.translate("RestoreDbDialog", "No backups found")
    QCoreApplication.translate(
        "RestoreDbDialog",
        "{backup_name} - before attaching new database: {timestamp} ({size} MB)",
    )
    QCoreApplication.translate(
        "RestoreDbDialog", "{backup_name} - {timestamp} ({size} MB)"
    )
    QCoreApplication.translate(
        "RestoreDbDialog",
        "{backup_name} ({size} MB)",
    )
    QCoreApplication.translate("RestoreDbDialog", "Error: {details}")

logger = logging.getLogger(__name__)


class RestoreDbDialog(BaseDialog):
    """Диалог для восстановления базы данных из резервной копии."""

    def __init__(self, backup_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)

        self.resize(500, 300)
        self.setModal(True)

        # Используем переданную директорию или получаем стандартную из PathConfig
        self.paths = app_config.paths
        self.backup_dir = backup_dir or self.paths.get_backups_dir()
        self.selected_backup = None

        self._init_ui()
        self._populate_list()

        # Подключаемся к языковой службе и выполняем первоначальную локализацию
        ReTranslatable.__init__(self)

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

        cancel_btn = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)

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
            logger.debug("Поиск резервных копий в: %s", self.backup_dir)

            # Ищем файлы резервных копий
            backups = sorted(self.backup_dir.glob("osteen_path_*.db"), reverse=True)
            logger.debug("Найдено резервных копий: %s", len(backups))

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
            logger.error("Failed to list database backups: %s", e)
            self._show_error_message(self.tr("Failed to list database backups: {error}").format(error=str(e)))

    def _show_no_backups_message(self) -> None:
        """Показывает сообщение об отсутствии резервных копий."""
        item = self._create_list_item("no_backups")
        self.list_widget.addItem(item)
        self.list_widget.setEnabled(False)
        logger.info("No backups found")

    def _add_single_backup_item(self, backup_path: Path) -> None:
        """Добавляет одиночную резервную копию links.db.bak в список с визуальным выделением."""
        try:
            # Проверяем размер файла
            if backup_path.stat().st_size == 0:
                logger.warning("Empty backup file encountered: %s", backup_path.name)
                return

            # Получаем дату и время создания файла
            stat = backup_path.stat()
            creation_time = datetime.datetime.fromtimestamp(stat.st_mtime)
            time_str = creation_time.strftime("%d.%m.%Y %H:%M")

            # Форматируем отображение с выделением и датой создания
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            item = self._create_list_item(
                "single_backup",
                backup_name=backup_path.name,
                timestamp=time_str,
                size=f"{size_mb:.1f}",
                font_bold=True,
            )

            # Добавляем элемент в список
            self.list_widget.addItem(item)

            logger.debug("Added single backup entry: %s", backup_path.name)

        except Exception as e:
            logger.warning("Failed to handle backup file %s: %s", backup_path.name, e)

    def _populate_backup_list(self, backups: list) -> None:
        """Заполняет список найденными резервными копиями."""
        for backup in backups:
            try:
                # Проверяем размер файла
                if backup.stat().st_size == 0:
                    logger.warning("Empty backup file encountered: %s", backup.name)
                    continue

                # Форматируем отображение
                dt_str = self._parse_datetime(backup.name)
                size_mb = backup.stat().st_size / (1024 * 1024)

                if dt_str:
                    item = self._create_list_item(
                        "auto_backup_with_timestamp",
                        backup_name=backup.name,
                        timestamp=dt_str,
                        size=f"{size_mb:.1f}",
                    )
                else:
                    item = self._create_list_item(
                        "auto_backup_without_timestamp",
                        backup_name=backup.name,
                        size=f"{size_mb:.1f}",
                    )

                self.list_widget.addItem(item)
                logger.debug("Added backup entry: %s", backup.name)

            except Exception as e:
                logger.warning("Failed to process backup file %s: %s", backup.name, e)
                continue

        if self.list_widget.count() > 0:
            self.list_widget.setEnabled(True)
            self.list_widget.setCurrentRow(0)  # Выбираем самую новую
        else:
            self._show_no_backups_message()

        self._update_ok_state()

    def _show_error_message(self, message: str) -> None:
        """Показывает сообщение об ошибке."""
        item = self._create_list_item(
            "error",
            details=message,
        )
        self.list_widget.addItem(item)
        self.list_widget.setEnabled(False)

    def _parse_datetime(self, filename: str) -> Optional[str]:
        """Парсит дату и время из имени файла резервной копии."""
        try:
            # Убираем префикс и суффикс
            base = filename.replace("osteen_path_", "").replace("links_", "").replace(".db", "")

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

            logger.debug("Could not parse backup timestamp from filename: %s", filename)
            return None

        except Exception as e:
            logger.debug("Failed to parse date from %s: %s", filename, e)
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
            backups = sorted(self.backup_dir.glob("osteen_path_*.db"), reverse=True)
            # Фильтруем пустые файлы
            valid_backups = [b for b in backups if b.stat().st_size > 0]

            # Если есть одиночная резервная копия, она будет первой в списке
            if single_backup_exists:
                # Если выбрана первая строка (одиночная резервная копия)
                if row == 0:
                    logger.info(
                        "Single backup selected: %s", single_backup_path.name
                    )
                    return single_backup_path
                else:
                    # Смещаем индекс для автоматических резервных копий
                    adjusted_row = row - 1
                    if adjusted_row >= len(valid_backups):
                        logger.warning("Неверный индекс резервной копии: %s", row)
                        return None

                    selected = valid_backups[adjusted_row]
                    logger.info(
                        "Automatic backup selected: %s", selected.name
                    )
                    return selected
            else:
                # Если нет одиночной резервной копии, работаем как раньше
                if row >= len(valid_backups):
                    logger.warning("Неверный индекс резервной копии: %s", row)
                    return None

                selected = valid_backups[row]
                logger.info("Backup selected: %s", selected.name)
                return selected

        except Exception as e:
            logger.error("Failed to resolve selected backup: %s", e)
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
                self.tr("No backup selected."),
                self.tr("Backup selection required"),
                informative_text=self.tr(
                    "Select a file from the list and click 'Restore'. If the list is empty, verify the backup directory."
                ),
            )
            return

        self.selected_backup = selected_backup
        super().accept()

    def get_result(self) -> Optional[Path]:
        """Возвращает выбранную резервную копию после закрытия диалога."""
        return self.selected_backup

    def retranslateUi(self) -> None:
        """Обновляет тексты интерфейса при смене языка."""
        if not hasattr(self, "buttons"):
            return

        self.setWindowTitle(_tr("Restore database from backup"))

        ok_btn = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText(_tr("Restore"))

        cancel_btn = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText(_tr("Cancel"))

        # Обновляем существующие элементы списка
        if hasattr(self, "list_widget"):
            for index in range(self.list_widget.count()):
                item = self.list_widget.item(index)
                self._apply_item_translation(item)

    def _create_list_item(
        self, template_key: str, font_bold: bool = False, **format_kwargs: Any
    ) -> QListWidgetItem:
        sanitized_kwargs = self._sanitize_format_kwargs(format_kwargs)

        item = QListWidgetItem()
        item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "template_key": template_key,
                "format_kwargs": sanitized_kwargs,
                "font_bold": font_bold,
            },
        )
        self._apply_item_translation(item)
        return item

    def _apply_item_translation(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        template_key = data.get("template_key", "")
        format_kwargs = data.get("format_kwargs", {})

        try:
            template = _LIST_ITEM_TEMPLATES.get(template_key)
            if template is None:
                logger.warning("Неизвестный ключ шаблона для элемента списка: %s", template_key)
                template = template_key
            translated = _tr(template)
            if format_kwargs:
                translated = translated.format(**format_kwargs)
            item.setText(translated)
        except Exception:
            fallback_template = template if template is not None else template_key
            if format_kwargs and isinstance(fallback_template, str):
                try:
                    item.setText(fallback_template.format(**format_kwargs))
                except Exception:
                    item.setText(str(fallback_template))
            else:
                item.setText(str(fallback_template))

        font_bold = bool(data.get("font_bold"))
        font = item.font()
        font.setBold(font_bold)
        item.setFont(font)

    @staticmethod
    def _sanitize_format_kwargs(format_kwargs: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in format_kwargs.items():
            if isinstance(value, str):
                sanitized[key] = value.replace("{", "{{").replace("}", "}}").strip()
            else:
                sanitized[key] = value
        return sanitized
