# app/utils/logging/exception_handler.py

import logging
import sys
import traceback

from PyQt6.QtWidgets import QApplication

from app.controllers.ui.dialogs import DialogManager

logger = logging.getLogger(__name__)


class ExceptionHandler:
    """Обработчик глобальных исключений."""

    def __init__(self):
        self.original_excepthook = sys.excepthook
        sys.excepthook = self.handle_exception

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Обрабатывает непойманные исключения."""
        if issubclass(exc_type, KeyboardInterrupt):
            # Возвращаем стандартное поведение для прерывания
            self.original_excepthook(exc_type, exc_value, exc_traceback)
            return

        # Логируем критическую ошибку
        logger.critical(
            "Непойманное исключение", exc_info=(exc_type, exc_value, exc_traceback)
        )

        # Показываем пользователю информацию об ошибке
        self._show_error_dialog(exc_type, exc_value, exc_traceback)

    def _show_error_dialog(self, exc_type, exc_value, exc_traceback):
        """Показывает диалог с информацией об ошибке."""
        try:
            # Проверяем, существует ли QApplication
            if QApplication.instance() is None:
                error_text = f"Произошла критическая ошибка: {exc_type.__name__}"
                error_info = str(exc_value)
                error_details = "".join(
                    traceback.format_exception(exc_type, exc_value, exc_traceback)
                )
                logger.error(error_text)
                logger.error(error_info)
                logger.error("Подробности:")
                logger.error(error_details)
                return

            error_text = f"Произошла критическая ошибка: {exc_type.__name__}"
            error_info = str(exc_value)
            error_details = "".join(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            )

            DialogManager.show_error(
                None,
                "Критическая ошибка",
                error_text,
                informative_text=f"{error_info}\n\nПриложение будет закрыто.",
                details=error_details,
            )
        except Exception as e:
            # Если даже диалог не удается показать
            logger.critical(f"Критическая ошибка: {exc_type.__name__}: {exc_value}")
            logger.critical(f"Ошибка показа диалога: {e}", exc_info=True)
