"""Сервис для управления фоновым обновлением иконок."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

from app.controllers.system.app_shutdown_controller import ShutdownPriority
from app.core.worker_manager import WorkerManager
from app.models.workers.icon_refresh_worker import IconRefreshWorker
from app.utils.ui.icon.cache_manager import clear_icon_cache

if TYPE_CHECKING:
    from app.controllers.system.app_shutdown_controller import AppShutdownController
    from app.models.database import Database

logger = logging.getLogger(__name__)


class IconRefreshService(QObject):
    """Сервис для фонового обновления иконок импортированных ссылок.
    
    Использует WorkerManager для выполнения задачи в фоновом потоке.
    Поддерживает отслеживание прогресса и отмену операции.
    """
    
    # Сигналы для UI
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(dict)  # stats: {updated: N, skipped: N, failed: N, total: N}
    error = pyqtSignal(str)  # error message
    
    def __init__(self, db: Database, parent: QObject | None = None):
        """
        Args:
            db: Database instance
            parent: Родительский QObject
        """
        super().__init__(parent)
        self.db = db
        self._current_worker: IconRefreshWorker | None = None
        self._dialog = None  # Ссылка на диалог для возможности показа из фона
        self._shutdown_controller: AppShutdownController | None = None
        self._shutdown_handler_name = f"icon_refresh_service_cancel_{id(self)}"
        self._parent_ref: QObject | None = parent
        self._register_shutdown_handler()

    def is_running(self) -> bool:
        """Проверить, выполняется ли задача в данный момент."""
        return self._current_worker is not None
    
    def set_dialog(self, dialog):
        """Установить ссылку на диалог для возможности показа из фона."""
        self._dialog = dialog
    
    def show_dialog(self):
        """Показать диалог если он скрыт в фоне."""
        if self._dialog and not self._dialog.isVisible():
            self._dialog.show()
            self._dialog.raise_()
            self._dialog.activateWindow()
    
    def start_refresh(
        self,
        batch_size: int = 50,
        delay_ms: int = 100,
        max_workers: int = 5,
        auto_start: bool = True,
    ) -> bool:
        """Запустить фоновое обновление иконок.
        
        Args:
            batch_size: Количество ссылок для обработки за раз
            delay_ms: Задержка между батчами (мс)
            max_workers: Количество параллельных потоков для загрузки иконок
            auto_start: Автоматически запустить после создания воркера
        
        Returns:
            True если задача запущена, False если уже выполняется
        """
        if self.is_running():
            logger.warning("[icon_refresh_service] Refresh already running")
            return False
        
        try:
            # Создаём воркер
            worker = IconRefreshWorker(
                db=self.db,
                batch_size=batch_size,
                delay_ms=delay_ms,
                max_workers=max_workers,
            )
            
            # Подключаем сигналы
            worker.signals.progress.connect(self._on_progress)
            worker.signals.finished.connect(self._on_finished)
            worker.signals.error.connect(self._on_error)
            worker.signals.batch_updated.connect(self._on_batch_updated)
            
            # Сохраняем ссылку на воркер
            self._current_worker = worker
            # Ensure shutdown handler is registered even if app_shutdown is attached later.
            self._register_shutdown_handler()
            
            if auto_start:
                # Запускаем в thread pool
                WorkerManager.run(worker)
                logger.info("[icon_refresh_service] Icon refresh started")
            
            return True
            
        except Exception as e:
            logger.error("[icon_refresh_service] Failed to start refresh: %s", e, exc_info=True)
            self._current_worker = None  # Reset worker on failure
            self.error.emit(f"Не удалось запустить обновление иконок: {e}")
            return False
    
    def cancel_refresh(self) -> bool:
        """Отменить текущее обновление иконок.
        
        Returns:
            True если отмена отправлена, False если задача не выполняется
        """
        if not self.is_running():
            logger.warning("[icon_refresh_service] No refresh running to cancel")
            return False
        
        try:
            if self._current_worker:
                self._current_worker.cancel()
                logger.info("[icon_refresh_service] Cancellation requested")
            return True
        except Exception as e:
            logger.error("[icon_refresh_service] Failed to cancel refresh: %s", e)
            return False
    
    def _on_progress(self, current: int, total: int, message: str):
        """Обработчик прогресса от воркера."""
        self.progress.emit(current, total, message)
    
    def _on_finished(self, stats: dict):
        """Обработчик завершения от воркера."""
        self._current_worker = None
        self._unregister_shutdown_handler()
        self.finished.emit(stats)
        logger.info(
            "[icon_refresh_service] Refresh completed: %s",
            stats,
        )
    
    def _on_batch_updated(self, updated_ids: list[int]):
        """Обработчик batch обновления иконок.
        
        Args:
            updated_ids: Список ID ссылок, у которых обновились иконки
        """
        # Можно добавить логику обновления UI здесь, если нужно
        # Например, отправить сигнал для обновления конкретных строк в таблице
        clear_icon_cache()
        logger.debug("[icon_refresh_service] Batch updated: %s links", len(updated_ids))

    def _on_error(self, error_message: str):
        """Обработчик ошибки от воркера."""
        self._current_worker = None
        self._unregister_shutdown_handler()
        self.error.emit(error_message)
        
        logger.error("[icon_refresh_service] Refresh error: %s", error_message)

    # === Shutdown integration ==================================================
    def _register_shutdown_handler(self) -> None:
        """Register cooperative cancellation handler with AppShutdownController."""
        if self._shutdown_controller is not None:
            return
        parent = self._parent_ref or self.parent()
        controller = None
        try:
            while parent is not None:
                if hasattr(parent, "app_shutdown"):
                    controller = parent.app_shutdown
                    if controller is not None:
                        break
                parent = parent.parent() if hasattr(parent, "parent") else None
        except Exception:
            controller = None
        if controller is None:
            return
        try:
            controller.add_shutdown_handler(
                self._shutdown_handler_name,
                self._handle_shutdown_request,
                priority=ShutdownPriority.HIGH,
                timeout=3000,
                critical=False,
            )
            self._shutdown_controller = controller
            logger.debug("[icon_refresh_service] Shutdown handler registered")
        except Exception as exc:
            logger.debug(
                "[icon_refresh_service] Failed to register shutdown handler: %s", exc
            )

    def _unregister_shutdown_handler(self) -> None:
        """Remove previously registered shutdown handler to avoid stale callbacks."""
        if not self._shutdown_controller:
            return
        try:
            removed = self._shutdown_controller.remove_shutdown_handler(
                self._shutdown_handler_name
            )
            if removed:
                logger.debug("[icon_refresh_service] Shutdown handler unregistered")
        except Exception as exc:
            logger.debug(
                "[icon_refresh_service] Failed to unregister shutdown handler: %s",
                exc,
            )
        finally:
            self._shutdown_controller = None

    def _handle_shutdown_request(self, timeout_ms: int | None = None) -> bool:
        """Shutdown handler invoked by AppShutdownController.

        Requests graceful cancellation and waits up to the provided timeout for
        worker threads to cooperate.
        """
        if self.is_running():
            try:
                self.cancel_refresh()
            except Exception as exc:
                logger.debug(
                    "[icon_refresh_service] Cancel during shutdown failed: %s", exc
                )
            wait_for = max(0, int(timeout_ms or 0))
            if wait_for:
                try:
                    WorkerManager.shutdown(wait_for)
                except Exception as exc:
                    logger.debug(
                        "[icon_refresh_service] WorkerManager shutdown failed: %s",
                        exc,
                    )
        return True


__all__ = ["IconRefreshService"]
