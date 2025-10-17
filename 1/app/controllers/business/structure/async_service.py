"""Asynchronous helpers for structure business logic."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer

from app.controllers.structure_modules import AsyncOperations, AsyncSignalHandlers

if TYPE_CHECKING:  # pragma: no cover - only for type checking
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.controllers.ui.top_panels_controller import TopPanelsController
    from app.models import Database


class StructureAsyncService(QObject):
    """Encapsulates asynchronous operations and reload scheduling."""

    def __init__(
        self, owner: StructureBusinessLogic, db: Database, logger: logging.Logger
    ) -> None:
        super().__init__(owner)
        self._owner = owner
        self._logger = logger
        self.async_operations = AsyncOperations(
            db, logger, parent=self
        )  # ✅ Добавлен parent
        self._handlers = AsyncSignalHandlers(owner, parent=self)  # ✅ Добавлен parent
        # Type-safe connection
        if hasattr(self.async_operations, 'connect_signal_handlers'):
            self.async_operations.connect_signal_handlers(self._handlers)  # type: ignore[arg-type]

        self._structure_reload_timer = QTimer(self)
        self._structure_reload_timer.setSingleShot(True)
        self._structure_reload_timer.timeout.connect(self._perform_structure_reload)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def shutdown(self, timeout: int) -> None:
        """Stop pending timers and shutdown async operations.

        ✅ ИСПРАВЛЕНИЕ: Добавлено отключение сигнала для предотвращения утечек памяти.
        """
        if self._structure_reload_timer.isActive():
            try:
                self._structure_reload_timer.stop()
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.debug(
                    "Failed to stop structure reload timer: %s", exc, exc_info=True
                )

        # ✅ Отключаем сигнал для предотвращения утечек памяти
        try:
            self._structure_reload_timer.timeout.disconnect(
                self._perform_structure_reload
            )
        except (TypeError, RuntimeError):
            pass  # Сигнал уже отключен

        try:
            getattr(self.async_operations, 'shutdown', lambda **kw: None)(timeout=timeout)
        except AttributeError:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug(
                "AsyncOperations.shutdown raised: %s", exc, exc_info=True
            )

    def set_top_panels_controller(self, controller: TopPanelsController) -> None:
        """Inject top panels controller into async components."""
        try:
            self.async_operations.top_panels = controller
        except AttributeError as exc:
            self._logger.warning(
                "Failed to inject TopPanelsController into AsyncOperations: %s",
                exc,
                exc_info=True,
            )

        try:
            self._handlers.top_panels = controller
        except AttributeError as exc:
            self._logger.warning(
                "Failed to inject TopPanelsController into AsyncSignalHandlers: %s",
                exc,
                exc_info=True,
            )

    def load_structure_async(self, sphere_id: int) -> None:
        self.async_operations.load_structure_async(sphere_id)

    def load_categories_async(self, section_id: int) -> None:
        self.async_operations.load_categories_async(section_id)

    def load_spheres_async(self) -> None:
        self.async_operations.load_spheres_async()

    def schedule_structure_reload(self, delay_ms: int | None = None) -> None:
        """Schedule structure reload with debounce."""
        try:
            from app.config_data import app_config

            if delay_ms is None:
                delay_ms = int(app_config.ui.get_structure_reload_delay_ms())
            if not isinstance(delay_ms, int) or delay_ms < 0:
                delay_ms = int(app_config.ui.get_structure_reload_delay_ms())

            if self._structure_reload_timer.isActive():
                self._structure_reload_timer.stop()
            self._structure_reload_timer.start(delay_ms)
        except Exception as exc:
            self._logger.warning(
                "_schedule_structure_reload failed to schedule: %s",
                exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------
    def _perform_structure_reload(self) -> None:
        try:
            self._owner._invalidate_structure_cache()
            sphere_id = self._owner.current_sphere_id
            if isinstance(sphere_id, int) and sphere_id > 0:
                self.async_operations.load_structure_async(sphere_id)
        except Exception as exc:
            self._logger.error("_perform_structure_reload: %s", exc, exc_info=True)
