"""
Centralized dialog manager to eliminate QMessageBox duplication.

This module provides a single point for all dialog windows in the application,
eliminating code duplication and ensuring UI consistency.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import QMessageBox, QWidget

from app.config_data import app_config

logger = logging.getLogger(__name__)


class DialogManager:
    """Centralized dialog manager to eliminate QMessageBox duplication.

    Provides static methods for showing various types of dialogs:
    - Errors (critical)
    - Warnings (warning)
    - Information (information)
    - Confirmations (question)

    Eliminates QMessageBox call duplication in 50+ places in the project.
    """

    @staticmethod
    def show_error(
        parent: Optional[QWidget],
        message: str,
        title: str = "Error",
        informative_text: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Show critical error dialog.

        Args:
            parent: Parent widget (can be None)
            message: Error message text
            title: Dialog title (default "Error")
        """
        logger.debug("Showing error dialog: %s - %s", title, message)
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if app_config.ui.get_dialogs_enable_details() and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    @staticmethod
    def show_warning(
        parent: Optional[QWidget],
        message: str,
        title: str = "Warning",
        informative_text: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Show warning dialog.

        Args:
            parent: Parent widget (can be None)
            message: Warning text
            title: Dialog title (default "Warning")
        """
        logger.debug("Showing warning dialog: %s - %s", title, message)
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if app_config.ui.get_dialogs_enable_details() and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    @staticmethod
    def show_info(
        parent: Optional[QWidget],
        message: str,
        title: str = "Information",
        informative_text: Optional[str] = None,
        details: Optional[str] = None,
        silent: bool = False,
    ) -> None:
        """Show information dialog.

        Args:
            parent: Parent widget (can be None)
            message: Informational message
            title: Dialog title (default "Information")
            informative_text: Additional text
            details: Details section text (if enabled in config)
            silent: If True, window is shown without icon (and system sound)
        """
        logger.debug("Showing info dialog: %s - %s", title, message)
        msg_box = QMessageBox(parent)
        # For silent message don't use icon to avoid system sound
        msg_box.setIcon(
            QMessageBox.Icon.NoIcon if silent else QMessageBox.Icon.Information
        )
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if app_config.ui.get_dialogs_enable_details() and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    @staticmethod
    def ask_confirmation(
        parent: Optional[QWidget],
        message: str,
        title: str = "Confirmation",
        informative_text: Optional[str] = None,
        details: Optional[str] = None,
    ) -> bool:
        """Show confirmation dialog with Yes/No buttons.

        Args:
            parent: Parent widget (can be None)
            message: Confirmation question text
            title: Dialog title (default "Confirmation")

        Returns:
            bool: True if user clicked "Yes", False if "No"
        """
        logger.debug("Showing confirmation dialog: %s - %s", title, message)

        # Create custom QMessageBox with limited width
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if app_config.ui.get_dialogs_enable_details() and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        # Limit maximum dialog width
        msg_box.setMaximumWidth(400)

        # Set button texts
        yes_button = msg_box.button(QMessageBox.StandardButton.Yes)
        no_button = msg_box.button(QMessageBox.StandardButton.No)
        if yes_button:
            yes_button.setText("Yes")
        if no_button:
            no_button.setText("No")

        reply = msg_box.exec()
        result = reply == QMessageBox.StandardButton.Yes
        logger.debug("Confirmation result: %s", result)
        return result

    @staticmethod
    def show_custom(
        parent: Optional[QWidget],
        icon: QMessageBox.Icon,
        title: str,
        message: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> QMessageBox.StandardButton:
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
        logger.debug("Showing custom dialog: %s - %s", title, message)
        msg_box = QMessageBox(parent)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(buttons)
        msg_box.setDefaultButton(default_button)

        result = msg_box.exec()
        logger.debug("Custom dialog result: %s", result)
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
        # Try self.parent
        if hasattr(self, "parent") and isinstance(getattr(self, "parent"), QWidget):
            return self.parent

        # Try self if it's QWidget
        if isinstance(self, QWidget):
            return self

        # Try self.main (for controllers)
        if hasattr(self, "main") and isinstance(getattr(self, "main"), QWidget):
            return self.main

        # No suitable parent
        return None

    def show_error(self, message: str, title: str = "Error") -> None:
        """Show error dialog."""
        DialogManager.show_error(self._get_parent_widget(), message, title)

    def show_warning(self, message: str, title: str = "Warning") -> None:
        """Show warning dialog."""
        DialogManager.show_warning(self._get_parent_widget(), message, title)

    def show_info(self, message: str, title: str = "Information") -> None:
        """Show information dialog."""
        DialogManager.show_info(self._get_parent_widget(), message, title)

    def ask_confirmation(self, message: str, title: str = "Confirmation") -> bool:
        """Show confirmation dialog."""
        return DialogManager.ask_confirmation(self._get_parent_widget(), message, title)

    def show_custom_dialog(
        self,
        icon: QMessageBox.Icon,
        title: str,
        message: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> QMessageBox.StandardButton:
        """Показать кастомный диалог."""
        return DialogManager.show_custom(
            self._get_parent_widget(), icon, title, message, buttons, default_button
        )
