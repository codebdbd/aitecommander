"""
Centralized dialog manager to eliminate QMessageBox duplication.

This module provides a single point for all dialog windows in the application,
eliminating code duplication and ensuring UI consistency.
"""

import logging
from typing import Optional

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication
from PyQt6.QtWidgets import QMessageBox, QWidget

from app.config_data.runtime_config import (
    get_dialog_message_box_max_width,
    is_dialogs_enable_details,
)

logger = logging.getLogger(__name__)

_DIALOG_MANAGER_CONTEXT = "DialogManager"
_DM_TITLE_ERROR = QT_TRANSLATE_NOOP(_DIALOG_MANAGER_CONTEXT, "Error")
_DM_TITLE_WARNING = QT_TRANSLATE_NOOP(_DIALOG_MANAGER_CONTEXT, "Warning")
_DM_TITLE_INFO = QT_TRANSLATE_NOOP(_DIALOG_MANAGER_CONTEXT, "Information")
_DM_TITLE_CONFIRM = QT_TRANSLATE_NOOP(_DIALOG_MANAGER_CONTEXT, "Confirmation")
_DM_BUTTON_OK = QT_TRANSLATE_NOOP(_DIALOG_MANAGER_CONTEXT, "OK")
_DM_BUTTON_CANCEL = QT_TRANSLATE_NOOP(_DIALOG_MANAGER_CONTEXT, "Cancel")
_DM_BUTTON_YES = QT_TRANSLATE_NOOP(_DIALOG_MANAGER_CONTEXT, "Yes")
_DM_BUTTON_NO = QT_TRANSLATE_NOOP(_DIALOG_MANAGER_CONTEXT, "No")

_DIALOG_MIXIN_CONTEXT = "DialogMixin"
_TITLE_ERROR = QT_TRANSLATE_NOOP(_DIALOG_MIXIN_CONTEXT, "Error")
_TITLE_WARNING = QT_TRANSLATE_NOOP(_DIALOG_MIXIN_CONTEXT, "Warning")
_TITLE_INFO = QT_TRANSLATE_NOOP(_DIALOG_MIXIN_CONTEXT, "Information")
_TITLE_CONFIRM = QT_TRANSLATE_NOOP(_DIALOG_MIXIN_CONTEXT, "Confirmation")


def _dm_tr(text: str) -> str:
    return QCoreApplication.translate(_DIALOG_MANAGER_CONTEXT, text)


def _mix_tr(text: str) -> str:
    return QCoreApplication.translate(_DIALOG_MIXIN_CONTEXT, text)


def localize_message_box_buttons(msg_box: QMessageBox) -> None:
    """Apply translated captions to standard QMessageBox buttons if present."""
    mapping = {
        QMessageBox.StandardButton.Ok: _dm_tr(_DM_BUTTON_OK),
        QMessageBox.StandardButton.Cancel: _dm_tr(_DM_BUTTON_CANCEL),
        QMessageBox.StandardButton.Yes: _dm_tr(_DM_BUTTON_YES),
        QMessageBox.StandardButton.No: _dm_tr(_DM_BUTTON_NO),
    }
    for button_id, text in mapping.items():
        button = msg_box.button(button_id)
        if button is not None:
            button.setText(text)


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
        title: Optional[str] = None,
        informative_text: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Show critical error dialog.

        Args:
            parent: Parent widget (can be None)
            message: Error message text
            title: Dialog title (default "Error")
        """
        resolved_title = title or _dm_tr(_DM_TITLE_ERROR)
        logger.debug("Showing error dialog: %s - %s", resolved_title, message)
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(resolved_title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if is_dialogs_enable_details() and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        localize_message_box_buttons(msg_box)
        msg_box.exec()

    @staticmethod
    def show_warning(
        parent: Optional[QWidget],
        message: str,
        title: Optional[str] = None,
        informative_text: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        """Show warning dialog.

        Args:
            parent: Parent widget (can be None)
            message: Warning text
            title: Dialog title (default "Warning")
        """
        resolved_title = title or _dm_tr(_DM_TITLE_WARNING)
        logger.debug("Showing warning dialog: %s - %s", resolved_title, message)
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(resolved_title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if is_dialogs_enable_details() and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        localize_message_box_buttons(msg_box)
        msg_box.exec()

    @staticmethod
    def show_info(
        parent: Optional[QWidget],
        message: str,
        title: Optional[str] = None,
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
        resolved_title = title or _dm_tr(_DM_TITLE_INFO)
        logger.debug("Showing info dialog: %s - %s", resolved_title, message)
        msg_box = QMessageBox(parent)
        # For silent message don't use icon to avoid system sound
        msg_box.setIcon(
            QMessageBox.Icon.NoIcon if silent else QMessageBox.Icon.Information
        )
        msg_box.setWindowTitle(resolved_title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if is_dialogs_enable_details() and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        localize_message_box_buttons(msg_box)
        msg_box.exec()

    @staticmethod
    def ask_confirmation(
        parent: Optional[QWidget],
        message: str,
        title: Optional[str] = None,
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
        resolved_title = title or _dm_tr(_DM_TITLE_CONFIRM)
        logger.debug("Showing confirmation dialog: %s - %s", resolved_title, message)

        # Create custom QMessageBox with limited width
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle(resolved_title)
        msg_box.setText(message)
        if informative_text:
            msg_box.setInformativeText(informative_text)
        if is_dialogs_enable_details() and details:
            msg_box.setDetailedText(details)
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)

        # Limit maximum dialog width
        msg_box.setMaximumWidth(get_dialog_message_box_max_width())

        localize_message_box_buttons(msg_box)

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
        from app.views.windows.dialogs.base_dialog import (
            apply_uniform_height_to_message_box,
        )
        
        logger.debug("Showing custom dialog: %s - %s", title, message)
        msg_box = QMessageBox(parent)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(buttons)
        msg_box.setDefaultButton(default_button)
        localize_message_box_buttons(msg_box)
        apply_uniform_height_to_message_box(msg_box)

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
        if hasattr(self, "parent") and isinstance(self.parent, QWidget):
            return self.parent

        # Try self if it's QWidget
        if isinstance(self, QWidget):
            return self

        # Try self.main (for controllers)
        if hasattr(self, "main") and isinstance(self.main, QWidget):
            return self.main

        # No suitable parent
        return None

    def show_error(self, message: str, title: Optional[str] = None) -> None:
        """Show error dialog."""
        resolved_title = title or _mix_tr(_TITLE_ERROR)
        DialogManager.show_error(self._get_parent_widget(), message, resolved_title)

    def show_warning(self, message: str, title: Optional[str] = None) -> None:
        """Show warning dialog."""
        resolved_title = title or _mix_tr(_TITLE_WARNING)
        DialogManager.show_warning(self._get_parent_widget(), message, resolved_title)

    def show_info(self, message: str, title: Optional[str] = None) -> None:
        """Show information dialog."""
        resolved_title = title or _mix_tr(_TITLE_INFO)
        DialogManager.show_info(self._get_parent_widget(), message, resolved_title)

    def ask_confirmation(
        self, message: str, title: Optional[str] = None
    ) -> bool:
        """Show confirmation dialog."""
        resolved_title = title or _mix_tr(_TITLE_CONFIRM)
        return DialogManager.ask_confirmation(
            self._get_parent_widget(), message, resolved_title
        )

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
