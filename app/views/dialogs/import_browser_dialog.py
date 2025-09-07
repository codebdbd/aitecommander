"""
Диалог импорта ссылок из браузера.

Требования по UI (приведено к виду диалога добавления категории):
- 1 строка: выбор сферы
- 2 строка: выбор раздела в выбранной сфере

Убрана прежняя реализация с единым комбобоксом «Сфера / Раздел».
"""

import logging
from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
)

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


class ImportBrowserDialog(BaseDialog):
    """Диалог для выбора раздела при импорте ссылок из браузера."""

    def __init__(self, structure_business_logic, parent=None):
        super().__init__(parent)

        self.structure_business_logic = structure_business_logic
        self.selected_section_id = None

        self.setWindowTitle("Импорт из браузера")
        self.resize(400, 180)
        self.setModal(True)

        self._init_ui()
        self._populate_spheres()
        self._update_sections()

    def _init_ui(self) -> None:
        """Инициализирует пользовательский интерфейс."""
        vbox = QVBoxLayout(self)

        # Заголовок
        label = QLabel("Выберите место импорта ссылок:")
        vbox.addWidget(label)

        # Форма с 2 строками: Сфера, Раздел
        form = QFormLayout()

        self.sphere_cb = QComboBox()
        self.sphere_cb.setMinimumHeight(32)
        form.addRow("Сфера:", self.sphere_cb)

        self.section_cb = QComboBox()
        self.section_cb.setMinimumHeight(32)
        form.addRow("Раздел:", self.section_cb)

        vbox.addLayout(form)

        # Кнопки
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        # Настройка кнопок
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Импортировать")

        cancel_btn = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setText("Отмена")

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        vbox.addWidget(button_box)

        # Подключение сигналов
        self.sphere_cb.currentIndexChanged.connect(self._update_sections)
        self.section_cb.currentIndexChanged.connect(self._on_section_changed)

    def _populate_spheres(self) -> None:
        """Заполняет комбобокс сферами."""
        try:
            self.sphere_cb.clear()
            spheres = self.structure_business_logic.get_spheres()
            logger.debug("Найдено сфер: %s", len(spheres))
            if not spheres:
                # Нет сфер — блокируем оба комбобокса
                self._show_no_data_message("Не найдено ни одной сферы")
                return
            for sphere in spheres:
                self.sphere_cb.addItem(sphere["name"], sphere["id"])
            if self.sphere_cb.count() > 0:
                self.sphere_cb.setCurrentIndex(0)
        except Exception as e:
            logger.error("Ошибка при загрузке сфер: %s", e, exc_info=True)
            self._show_error_message(str(e))

    def _update_sections(self) -> None:
        """Обновляет список разделов для выбранной сферы."""
        try:
            self.section_cb.clear()
            sphere_id = self.sphere_cb.currentData()
            if not sphere_id:
                self._show_no_sections_message("Сначала выберите сферу")
                return
            sections = self.structure_business_logic.get_sections(sphere_id)
            if not sections:
                self._show_no_sections_message("В выбранной сфере нет разделов")
                return
            for section in sections:
                self.section_cb.addItem(section["name"], section["id"])
            if self.section_cb.count() > 0:
                self.section_cb.setCurrentIndex(0)
        except Exception as e:
            logger.error("Ошибка при загрузке разделов: %s", e, exc_info=True)
            self._show_error_message(str(e))

    def _show_no_data_message(self, message: str) -> None:
        """Показывает сообщение об отсутствии данных (нет сфер)."""
        self.sphere_cb.addItem(message)
        self.sphere_cb.setEnabled(False)
        self.section_cb.addItem("Нет данных")
        self.section_cb.setEnabled(False)
        logger.warning("%s", message)

    def _show_no_sections_message(self, message: str) -> None:
        """Показывает сообщение об отсутствии разделов в выбранной сфере."""
        self.section_cb.addItem(message)
        self.section_cb.setEnabled(False)
        logger.warning(message)

    def _show_error_message(self, message: str) -> None:
        """Показывает сообщение об ошибке."""
        self.section_cb.addItem(f"Ошибка: {message}")
        self.section_cb.setEnabled(False)
        self.show_error(
            "Не удалось загрузить список разделов.",
            "Ошибка загрузки разделов",
            informative_text="Проверьте подключение к базе данных и повторите попытку.",
            details=message,
        )

    def _on_section_changed(self) -> None:
        """Обработчик изменения выбранного раздела."""
        section_id = self.section_cb.currentData()
        if section_id:
            sphere_name = self.sphere_cb.currentText()
            section_name = self.section_cb.currentText()
            logger.debug("Выбран раздел: %s / %s", sphere_name, section_name)

    def get_selected_section_id(self) -> Optional[int]:
        """Возвращает ID выбранного раздела."""
        if not self.section_cb.isEnabled():
            return None
        return self.section_cb.currentData()

    def get_selected_section_info(self) -> Optional[Dict]:
        """Возвращает информацию о выбранном разделе и сфере."""
        section_id = self.get_selected_section_id()
        if not section_id:
            return None
        return {
            "section_id": section_id,
            "sphere_id": self.sphere_cb.currentData(),
            "sphere_name": self.sphere_cb.currentText(),
            "section_name": self.section_cb.currentText(),
        }

    def accept(self) -> None:
        """Подтверждение выбора раздела."""
        section_id = self.get_selected_section_id()

        if not section_id:
            self.show_warning(
                "Раздел для импорта не выбран.",
                "Требуется выбор раздела",
                informative_text="Выберите раздел в выпадающем списке, затем нажмите 'Импортировать'.",
            )
            return

        # Проверяем, что раздел еще существует
        try:
            section_info = self.get_selected_section_info()
            if not section_info:
                self.show_warning(
                    "Выбранный раздел недоступен.",
                    "Раздел не найден",
                    informative_text="Возможно, раздел был удалён. Обновите список разделов и выберите другой.",
                )
                return

            self.selected_section_id = section_id
            logger.info(
                "Подтвержден импорт в раздел: %s / %s",
                section_info['sphere_name'],
                section_info['section_name'],
            )
            super().accept()

        except Exception as e:
            logger.error("Ошибка при подтверждении выбора раздела: %s", e, exc_info=True)
            self.show_error(
                "Не удалось подтвердить выбор раздела.",
                "Ошибка при подтверждении",
                informative_text="Попробуйте выбрать раздел заново или обновите список разделов.",
                details=str(e),
            )

    def get_result(self) -> Optional[Dict]:
        """Возвращает результат выбора после закрытия диалога."""
        if self.selected_section_id:
            return self.get_selected_section_info()
        return None
