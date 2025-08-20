"""
Диалог импорта ссылок из браузера.

Исправления:
- Использование Repository вместо прямой работы с Database
- Улучшена обработка ошибок
- Добавлено логирование
- Валидация выбранного раздела
"""

import logging
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from app.controllers.ui.dialogs import DialogManager

from .base_dialog import BaseDialog


class ImportBrowserDialog(BaseDialog):
    """Диалог для выбора раздела при импорте ссылок из браузера."""
    
    def __init__(self, structure_business_logic, parent=None):
        super().__init__(parent)
        
        self.logger = logging.getLogger(__name__)
        self.structure_business_logic = structure_business_logic
        self.selected_section_id = None
        self.section_map = {}
        
        self.setWindowTitle("Импорт из браузера")
        self.resize(400, 150)
        self.setModal(True)
        
        self._init_ui()
        self._populate_sections()
    
    def _init_ui(self) -> None:
        """Инициализирует пользовательский интерфейс."""
        vbox = QVBoxLayout(self)
        
        # Заголовок
        label = QLabel("Выберите раздел для импорта ссылок:")
        vbox.addWidget(label)
        
        # Комбобокс для выбора раздела
        self.section_cb = QComboBox()
        self.section_cb.setMinimumHeight(32)
        vbox.addWidget(self.section_cb)
        
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
        self.section_cb.currentIndexChanged.connect(self._on_section_changed)
    
    def _populate_sections(self) -> None:
        """Заполняет комбобокс разделами из всех сфер."""
        try:
            self.section_cb.clear()
            self.section_map.clear()
            
            # Получаем все сферы
            spheres = self.structure_business_logic.get_spheres()
            self.logger.debug(f"Найдено сфер: {len(spheres)}")
            
            if not spheres:
                self._show_no_data_message("Не найдено ни одной сферы")
                return
            
            sections_added = 0
            
            # Проходим по всем сферам и их разделам
            for sphere in spheres:
                try:
                    sections = self.structure_business_logic.get_sections(sphere['id'])
                    
                    for section in sections:
                        # Формируем отображаемый текст
                        display_text = f"{sphere['name']} / {section['name']}"
                        
                        # Добавляем в комбобокс
                        self.section_cb.addItem(display_text, section['id'])
                        
                        # Сохраняем информацию о разделе
                        self.section_map[section['id']] = {
                            'sphere_id': sphere['id'],
                            'sphere_name': sphere['name'],
                            'section_name': section['name']
                        }
                        
                        sections_added += 1
                        
                except Exception as e:
                    self.logger.warning(f"Ошибка при получении разделов для сферы {sphere['name']}: {e}")
                    continue
            
            if sections_added == 0:
                self._show_no_data_message("Не найдено ни одного раздела")
            else:
                self.logger.info(f"Загружено разделов: {sections_added}")
                # Выбираем первый раздел по умолчанию
                if self.section_cb.count() > 0:
                    self.section_cb.setCurrentIndex(0)
                    
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке разделов: {e}")
            self._show_error_message(f"Ошибка при загрузке данных: {str(e)}")
    
    def _show_no_data_message(self, message: str) -> None:
        """Показывает сообщение об отсутствии данных."""
        self.section_cb.addItem(message)
        self.section_cb.setEnabled(False)
        self.logger.warning(message)
    
    def _show_error_message(self, message: str) -> None:
        """Показывает сообщение об ошибке."""
        self.section_cb.addItem(f"Ошибка: {message}")
        self.section_cb.setEnabled(False)
        DialogManager.show_error(
            self,
            "Не удалось загрузить список разделов.",
            "Ошибка загрузки разделов",
            informative_text="Проверьте подключение к базе данных и повторите попытку.",
            details=message,
        )
    
    def _on_section_changed(self) -> None:
        """Обработчик изменения выбранного раздела."""
        section_id = self.section_cb.currentData()
        if section_id and section_id in self.section_map:
            section_info = self.section_map[section_id]
            self.logger.debug(f"Выбран раздел: {section_info['sphere_name']} / {section_info['section_name']}")
    
    def get_selected_section_id(self) -> Optional[int]:
        """Возвращает ID выбранного раздела."""
        if not self.section_cb.isEnabled():
            return None
        return self.section_cb.currentData()
    
    def get_selected_section_info(self) -> Optional[Dict]:
        """Возвращает полную информацию о выбранном разделе."""
        section_id = self.get_selected_section_id()
        if section_id and section_id in self.section_map:
            return {
                'section_id': section_id,
                **self.section_map[section_id]
            }
        return None
    
    def accept(self) -> None:
        """Подтверждение выбора раздела."""
        section_id = self.get_selected_section_id()
        
        if not section_id:
            DialogManager.show_warning(
                self,
                "Раздел для импорта не выбран.",
                "Требуется выбор раздела",
                informative_text="Выберите раздел в выпадающем списке, затем нажмите 'Импортировать'.",
            )
            return
        
        # Проверяем, что раздел еще существует
        try:
            section_info = self.get_selected_section_info()
            if not section_info:
                DialogManager.show_warning(
                    self,
                    "Выбранный раздел недоступен.",
                    "Раздел не найден",
                    informative_text="Возможно, раздел был удалён. Обновите список разделов и выберите другой.",
                )
                return
            
            self.selected_section_id = section_id
            self.logger.info(f"Подтвержден импорт в раздел: {section_info['sphere_name']} / {section_info['section_name']}")
            super().accept()
            
        except Exception as e:
            self.logger.error(f"Ошибка при подтверждении выбора раздела: {e}")
            DialogManager.show_error(
                self,
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

