"""
Централизованный менеджер диалогов для устранения дублирования QMessageBox.

Этот модуль предоставляет единую точку для всех диалоговых окон в приложении,
устраняя дублирование кода и обеспечивая единообразие UI.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import QMessageBox, QWidget

from app.config_data import app_config

logger = logging.getLogger(__name__)


class DialogManager:
    """Централизованный менеджер диалогов для устранения дублирования QMessageBox.
    
    Предоставляет статические методы для показа различных типов диалогов:
    - Ошибки (critical)
    - Предупреждения (warning) 
    - Информация (information)
    - Подтверждения (question)
    
    Устраняет дублирование QMessageBox вызовов в 50+ местах проекта.
    """
    
    @staticmethod
    def show_error(parent: Optional[QWidget], message: str, title: str = "Ошибка",
                   informative_text: Optional[str] = None,
                   details: Optional[str] = None) -> None:
        """Показать диалог критической ошибки.
        
        Args:
            parent: Родительский виджет (может быть None)
            message: Текст сообщения об ошибке
            title: Заголовок диалога (по умолчанию "Ошибка")
        """
        logger.debug(f"Showing error dialog: {title} - {message}")
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if app_config.get('ui.dialogs.enable_details', False) and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    
    @staticmethod
    def show_warning(parent: Optional[QWidget], message: str, title: str = "Предупреждение",
                     informative_text: Optional[str] = None,
                     details: Optional[str] = None) -> None:
        """Показать диалог предупреждения.
        
        Args:
            parent: Родительский виджет (может быть None)
            message: Текст предупреждения
            title: Заголовок диалога (по умолчанию "Предупреждение")
        """
        logger.debug(f"Showing warning dialog: {title} - {message}")
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if app_config.get('ui.dialogs.enable_details', False) and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    
    @staticmethod
    def show_info(parent: Optional[QWidget], message: str, title: str = "Информация",
                  informative_text: Optional[str] = None,
                  details: Optional[str] = None,
                  silent: bool = False) -> None:
        """Показать информационный диалог.
        
        Args:
            parent: Родительский виджет (может быть None)
            message: Информационное сообщение
            title: Заголовок диалога (по умолчанию "Информация")
            informative_text: Дополнительный текст
            details: Текст для секции подробностей (если включено в конфиге)
            silent: Если True, окно показывается без иконки (и системного звука)
        """
        logger.debug(f"Showing info dialog: {title} - {message}")
        msg_box = QMessageBox(parent)
        # Для тихого сообщения не используем иконку, чтобы избежать системного звука
        msg_box.setIcon(QMessageBox.Icon.NoIcon if silent else QMessageBox.Icon.Information)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if app_config.get('ui.dialogs.enable_details', False) and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    
    @staticmethod
    def ask_confirmation(parent: Optional[QWidget], message: str, 
                        title: str = "Подтверждение",
                        informative_text: Optional[str] = None,
                        details: Optional[str] = None) -> bool:
        """Показать диалог подтверждения с кнопками Да/Нет.
        
        Args:
            parent: Родительский виджет (может быть None)
            message: Текст вопроса для подтверждения
            title: Заголовок диалога (по умолчанию "Подтверждение")
            
        Returns:
            bool: True если пользователь нажал "Да", False если "Нет"
        """
        logger.debug(f"Showing confirmation dialog: {title} - {message}")
        
        # Создаем кастомный QMessageBox с ограниченной шириной
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if app_config.get('ui.dialogs.enable_details', False) and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        
        # Ограничиваем максимальную ширину диалога
        msg_box.setMaximumWidth(400)
        
        # Устанавливаем русские названия кнопок
        yes_button = msg_box.button(QMessageBox.StandardButton.Yes)
        no_button = msg_box.button(QMessageBox.StandardButton.No)
        if yes_button:
            yes_button.setText("Да")
        if no_button:
            no_button.setText("Нет")
        
        reply = msg_box.exec()
        result = reply == QMessageBox.StandardButton.Yes
        logger.debug(f"Confirmation result: {result}")
        return result
    
    @staticmethod
    def show_custom(parent: Optional[QWidget], icon: QMessageBox.Icon, 
                   title: str, message: str, 
                   buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
                   default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok) -> QMessageBox.StandardButton:
        """Показать кастомный диалог с настраиваемыми параметрами.
        
        Args:
            parent: Родительский виджет (может быть None)
            icon: Иконка диалога (Critical, Warning, Information, Question)
            title: Заголовок диалога
            message: Текст сообщения
            buttons: Кнопки диалога (по умолчанию Ok)
            default_button: Кнопка по умолчанию (по умолчанию Ok)
            
        Returns:
            QMessageBox.StandardButton: Нажатая пользователем кнопка
        """
        logger.debug(f"Showing custom dialog: {title} - {message}")
        msg_box = QMessageBox(parent)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(buttons)
        msg_box.setDefaultButton(default_button)
        
        result = msg_box.exec()
        logger.debug(f"Custom dialog result: {result}")
        return QMessageBox.StandardButton(result)


class DialogMixin:
    """Mixin для добавления методов диалогов в любой класс.
    
    Предоставляет удобные методы для показа диалогов без необходимости
    импортировать DialogManager в каждом классе.
    
    Использование:
        class MyClass(DialogMixin):
            def some_method(self):
                self.show_error("Произошла ошибка!")
    """
    
    def _get_parent_widget(self) -> Optional[QWidget]:
        """Получить родительский виджет для диалогов.
        
        Пытается найти подходящий родительский виджет в следующем порядке:
        1. self.parent (если есть и это QWidget)
        2. self (если это QWidget)
        3. None (диалог будет показан без родителя)
        """
        # Попробовать self.parent
        if hasattr(self, 'parent') and isinstance(getattr(self, 'parent'), QWidget):
            return self.parent
        
        # Попробовать self если это QWidget
        if isinstance(self, QWidget):
            return self
        
        # Попробовать self.main (для контроллеров)
        if hasattr(self, 'main') and isinstance(getattr(self, 'main'), QWidget):
            return self.main
        
        # Нет подходящего родителя
        return None
    
    def show_error(self, message: str, title: str = "Ошибка") -> None:
        """Показать диалог ошибки."""
        DialogManager.show_error(self._get_parent_widget(), message, title)
    
    def show_warning(self, message: str, title: str = "Предупреждение") -> None:
        """Показать диалог предупреждения."""
        DialogManager.show_warning(self._get_parent_widget(), message, title)
    
    def show_info(self, message: str, title: str = "Информация") -> None:
        """Показать информационный диалог."""
        DialogManager.show_info(self._get_parent_widget(), message, title)
    
    def ask_confirmation(self, message: str, title: str = "Подтверждение") -> bool:
        """Показать диалог подтверждения."""
        return DialogManager.ask_confirmation(self._get_parent_widget(), message, title)
    
    def show_custom_dialog(self, icon: QMessageBox.Icon, title: str, message: str,
                          buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
                          default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok) -> QMessageBox.StandardButton:
        """Показать кастомный диалог."""
        return DialogManager.show_custom(self._get_parent_widget(), icon, title, message, buttons, default_button)
