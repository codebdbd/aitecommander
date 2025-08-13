# app/controllers/app_shutdown_controller.py

import logging

from PyQt6.QtCore import QThreadPool

from app.config_data import app_config


class AppShutdownController:
    """Контроллер корректного завершения приложения (graceful shutdown).
    Инкапсулирует остановку контроллеров/бизнес-логики, ожидание потоков и бэкап БД.
    """

    def __init__(self, main_window):
        self.window = main_window

    def perform_shutdown(self, event):
        """Выполнить корректное завершение приложения и передать событие базовому классу."""
        self._shutdown_controllers()
        self._wait_for_thread_pools()
        self._backup_database()
        # Передаем событие стандартной реализации closeEvent суперкласса QMainWindow
        self.window.__class__.__bases__[0].closeEvent(self.window, event)

    def _shutdown_controllers(self):
        """Остановить фоновые контроллеры, если они существуют."""
        try:
            if hasattr(self.window, "links") and hasattr(self.window.links, "shutdown"):
                self.window.links.shutdown()
            if hasattr(self.window, "links_business") and hasattr(self.window.links_business, "shutdown"):
                self.window.links_business.shutdown()
            if hasattr(self.window, "tiles") and hasattr(self.window.tiles, "shutdown"):
                self.window.tiles.shutdown()
        except Exception as exc:
            logging.error("Error during controllers shutdown: %s", exc, exc_info=True)

    def _wait_for_thread_pools(self):
        """Дождаться завершения фоновых задач, но ограниченно по времени."""
        try:
            pool = QThreadPool.globalInstance()
            timeout = app_config.get('ui.thread_pool_shutdown_timeout', 2000)
            pool.waitForDone(timeout)
            if hasattr(self.window, "thread_pool"):
                self.window.thread_pool.waitForDone(timeout)
        except Exception as exc:
            logging.error("Error waiting for thread pool to finish: %s", exc, exc_info=True)

    def _backup_database(self):
        """Создать резервную копию базы данных, если БД доступна."""
        try:
            if hasattr(self.window, 'db') and self.window.db:
                self.window.db.backup()
        except Exception as exc:
            logging.error("Error during backup or database closing: %s", exc, exc_info=True)
