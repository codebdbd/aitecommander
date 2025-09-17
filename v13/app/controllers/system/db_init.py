"""Модуль для инициализации базы данных в фоновом режиме."""

import logging
from typing import Callable, Optional

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.models.db import Database
from app.utils.db.api import run_db

# Модульный логгер
logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """Класс для управления инициализацией базы данных."""

    def __init__(self, database: Database, main_window=None):
        """
        Инициализирует DatabaseInitializer.

        Args:
            database: Экземпляр базы данных
            main_window: Главное окно приложения (опционально)
        """
        self.database = database
        self.main_window = main_window

    def initialize_async(
        self,
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """
        Запускает асинхронную инициализацию базы данных.

        Args:
            on_success: Колбэк при успешной инициализации
            on_error: Колбэк при ошибке инициализации
        """
        # Показать статус в строке состояния (если доступно)
        self._update_status_message("Инициализация базы данных…")

        # Временно заблокировать взаимодействие с UI на время инициализации БД
        self._set_ui_enabled(False)

        # Запуск тяжёлых операций инициализации в пуле потоков
        run_db(
            self._do_db_init,
            use_lock=True,
            description="db_init",
            on_finished=lambda res: self._on_db_init_finished(res, on_success),
            on_error=lambda e: self._on_db_init_error(e, on_error),
        )

    def _do_db_init(self) -> bool:
        """
        Выполняет инициализацию базы данных.

        Returns:
            bool: True при успехе, False при ошибке
        """
        # Позволяем исключениям всплывать, чтобы run_db передал их в on_error
        self.database.prepare_dirs()
        self.database.initialize_or_migrate()
        return True

    def _on_db_init_finished(
        self, result: bool, on_success: Optional[Callable] = None
    ) -> None:
        """
        Обработчик завершения инициализации БД.

        Args:
            result: Результат инициализации
            on_success: Колбэк при успехе
        """
        if not result:
            # Разблокировать UI при ошибке
            self._set_ui_enabled(True)

            # Сообщаем пользователю и завершаем приложение
            self._show_critical_error(
                "Ошибка инициализации БД",
                "Произошла ошибка при инициализации базы данных. Приложение будет закрыто.",
            )
            self._quit_application()
            return

        # При успехе — завершаем штатные действия
        try:
            # Создаём соединение в главном потоке по требованию
            _ = self.database.connection
        except Exception as e:
            logger.warning("Не удалось открыть соединение в главном потоке: %s", e)

        # Обновить статус-бар и разблокировать UI
        self._update_status_message("Готово")
        self._update_statusbar()
        self._set_ui_enabled(True)

        # Вызвать колбэк успеха
        if on_success:
            try:
                on_success()
            except Exception as e:
                logger.error(
                    "Ошибка в колбэке успешной инициализации БД: %s", e, exc_info=True
                )

    def _on_db_init_error(
        self, error: Exception, on_error: Optional[Callable[[Exception], None]] = None
    ) -> None:
        """
        Обработчик ошибки инициализации БД.

        Args:
            error: Исключение
            on_error: Колбэк при ошибке
        """
        logger.error("Ошибка инициализации БД в фоне: %s", error, exc_info=True)

        # Обновить статус и разблокировать UI перед показом критического сообщения
        self._update_status_message("Ошибка инициализации БД")
        self._update_statusbar()
        self._set_ui_enabled(True)

        # Показать пользователю подробную причину ошибки и завершить приложение
        try:
            # Включаем текст исключения в сообщение для быстрой диагностики
            err_text = f"Произошла ошибка при инициализации базы данных:\n{type(error).__name__}: {error}\nПриложение будет закрыто."
            self._show_critical_error("Ошибка инициализации БД", err_text)
        except Exception:
            # Даже если показ диалога не удался, продолжаем завершение
            logger.debug("Не удалось показать подробности ошибки инициализации БД", exc_info=True)

        # Завершаем приложение после критической ошибки
        self._quit_application()

        # Вызвать колбэк ошибки
        if on_error:
            try:
                on_error(error)
            except Exception as e:
                logger.error(
                    "Ошибка в колбэке ошибки инициализации БД: %s", e, exc_info=True
                )

    def _update_status_message(self, message: str) -> None:
        """Обновляет сообщение в статус-баре."""
        try:
            if (
                self.main_window
                and hasattr(self.main_window, "message_label")
                and self.main_window.message_label
            ):
                self.main_window.message_label.setText(message)
        except Exception as e:
            logger.warning(
                "[DatabaseInitializer] Не удалось обновить статус-сообщение '%s': %s",
                message,
                e,
                exc_info=True,
            )

    def _update_statusbar(self) -> None:
        """Обновляет статус-бар."""
        try:
            if self.main_window and hasattr(self.main_window, "update_statusbar"):
                self.main_window.update_statusbar()
        except Exception as e:
            logger.warning(
                "[DatabaseInitializer] Не удалось обновить статус-бар: %s",
                e,
                exc_info=True,
            )

    def _set_ui_enabled(self, enabled: bool) -> None:
        """Включает/отключает UI."""
        try:
            if self.main_window:
                self.main_window.setEnabled(enabled)
        except Exception as e:
            logger.warning(
                "[DatabaseInitializer] Не удалось %sключить UI: %s",
                "в" if enabled else "от",
                e,
                exc_info=True,
            )

    def _show_critical_error(self, title: str, message: str) -> None:
        """Показывает критическую ошибку."""
        try:
            if self.main_window is None:
                logger.critical(
                    "Главное окно отсутствует при показе ошибки инициализации БД; диалог будет показан без родителя"
                )

            QMessageBox.critical(
                self.main_window if self.main_window is not None else None,
                title,
                message,
            )
        except Exception as e:
            logger.error(
                "[DatabaseInitializer] Не удалось показать критический диалог '%s': %s",
                title,
                e,
                exc_info=True,
            )

    def _quit_application(self) -> None:
        """Завершает приложение."""
        try:
            app_inst = QApplication.instance()
            if app_inst is not None:
                app_inst.quit()
        except Exception as e:
            logger.error(
                "[DatabaseInitializer] Не удалось завершить приложение: %s",
                e,
                exc_info=True,
            )
