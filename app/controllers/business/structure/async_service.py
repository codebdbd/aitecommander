"""Asynchronous helpers for structure business logic."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer

from app.controllers.structure_modules import AsyncOperations, AsyncSignalHandlers
from app.config_data.runtime_config import get_structure_reload_delay_ms

if TYPE_CHECKING:  # pragma: no cover - only for type checking
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.controllers.ui.top_panels_controller import TopPanelsController
    from app.models import Database


class StructureAsyncService(QObject):
    """Encapsulates asynchronous operations and reload scheduling."""

    _CATEGORY_LOAD_COALESCE_WINDOW_S = 0.20
    _CATEGORY_LOAD_INFLIGHT_TIMEOUT_S = 5.0

    def __init__(
        self, owner: StructureBusinessLogic, db: Database, logger: logging.Logger
    ) -> None:
        super().__init__(owner)
        self._owner = owner
        self._logger = logger
        self._structure_reload_in_flight = False
        self._pending_structure_reload: int | None = None
        self._last_structure_reload_sphere: int | None = None
        self._last_structure_reload_started_ts = 0.0
        self._category_load_started_ts: dict[int, float] = {}
        self._category_last_dispatched_ts: dict[int, float] = {}
        self._category_inflight_since_ts: dict[int, float] = {}
        self._category_load_in_flight: set[int] = set()
        self._category_pending_reload: set[int] = set()
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
        self._connect_structure_reload_signals()

    def _connect_structure_reload_signals(self) -> None:
        try:
            signals = getattr(self.async_operations, "get_worker_signals", None)
            if callable(signals):
                signals = signals()
            if signals is None:
                signals = getattr(self.async_operations, "_worker_signals", None)
            if signals is None:
                return
            signals.structure_loaded.connect(self._on_structure_loaded)
            if hasattr(signals, "categories_loaded"):
                signals.categories_loaded.connect(self._on_categories_loaded)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.debug(
                "StructureAsyncService: failed to connect structure_loaded: %s",
                exc,
                exc_info=True,
            )

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
            getattr(self.async_operations, "shutdown", lambda **_: None)(
                timeout=timeout
            )
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
        started_ts = time.perf_counter()
        self._logger.info(
            "[Trace] StructureAsyncService.load_structure_async enter sphere=%s in_flight=%s pending=%s",
            sphere_id,
            self._structure_reload_in_flight,
            self._pending_structure_reload,
        )
        if self._structure_reload_in_flight:
            self._pending_structure_reload = sphere_id
            self._logger.debug(
                "StructureAsyncService: structure reload in flight, coalescing sphere=%s",
                sphere_id,
            )
            self._logger.info(
                "[Trace] StructureAsyncService.load_structure_async coalesced sphere=%s elapsed=%.2f ms",
                sphere_id,
                (time.perf_counter() - started_ts) * 1000.0,
            )
            return
        self._structure_reload_in_flight = True
        self._last_structure_reload_started_ts = time.perf_counter()
        self._logger.info(
            "[Trace] StructureAsyncService.load_structure_async dispatch sphere=%s",
            sphere_id,
        )
        self.async_operations.load_structure_async(sphere_id)
        self._logger.info(
            "[Trace] StructureAsyncService.load_structure_async returned sphere=%s elapsed=%.2f ms",
            sphere_id,
            (time.perf_counter() - started_ts) * 1000.0,
        )

    def load_categories_async(self, section_id: int) -> None:
        try:
            sid = int(section_id)
            if sid <= 0:
                return
        except Exception:
            return

        now = time.perf_counter()

        if sid in self._category_load_in_flight:
            started_at = self._category_inflight_since_ts.get(sid, now)
            if (now - started_at) <= self._CATEGORY_LOAD_INFLIGHT_TIMEOUT_S:
                self._category_pending_reload.add(sid)
                self._logger.debug(
                    "StructureAsyncService: categories load in flight, coalescing section=%s",
                    sid,
                )
                return
            self._logger.debug(
                "StructureAsyncService: stale in-flight category load reset section=%s",
                sid,
            )
            self._category_load_in_flight.discard(sid)
            self._category_inflight_since_ts.pop(sid, None)

        last_dispatched = self._category_last_dispatched_ts.get(sid, 0.0)
        if (now - last_dispatched) < self._CATEGORY_LOAD_COALESCE_WINDOW_S:
            self._logger.debug(
                "StructureAsyncService: categories load deduplicated section=%s",
                sid,
            )
            return

        self._dispatch_categories_load(sid, now)

    def _dispatch_categories_load(self, section_id: int, now_ts: float | None = None) -> None:
        now = now_ts if isinstance(now_ts, (int, float)) else time.perf_counter()
        sid = int(section_id)
        self._category_load_started_ts[sid] = now
        self._category_last_dispatched_ts[sid] = now
        self._category_inflight_since_ts[sid] = now
        self._category_load_in_flight.add(sid)
        self.async_operations.load_categories_async(sid)

    def should_drop_categories_emit(self, section_id: int) -> bool:
        """Return True when current categories result is stale and should be ignored.

        A result is treated as stale if a newer reload request for the same section
        was queued while the previous one was still in flight.
        """
        try:
            sid = int(section_id)
        except Exception:
            return False
        return sid in self._category_pending_reload

    def pop_category_load_started_ts(self, section_id: int) -> float | None:
        try:
            sid = int(section_id)
        except Exception:
            return None
        return self._category_load_started_ts.pop(sid, None)

    def load_spheres_async(self) -> None:
        self.async_operations.load_spheres_async()

    def schedule_structure_reload(self, delay_ms: int | None = None) -> None:
        """Schedule structure reload with debounce."""
        try:
            if delay_ms is None:
                delay_ms = get_structure_reload_delay_ms()
            if not isinstance(delay_ms, int) or delay_ms < 0:
                delay_ms = get_structure_reload_delay_ms()

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
        started_ts = time.perf_counter()
        try:
            self._owner._invalidate_structure_cache()
            sphere_id = self._owner.current_sphere_id
            self._logger.info(
                "[Trace] StructureAsyncService._perform_structure_reload enter sphere=%s in_flight=%s",
                sphere_id,
                self._structure_reload_in_flight,
            )
            if isinstance(sphere_id, int) and sphere_id > 0:
                if self._structure_reload_in_flight:
                    self._pending_structure_reload = sphere_id
                    self._logger.debug(
                        "StructureAsyncService: structure reload already in flight, coalescing sphere=%s",
                        sphere_id,
                    )
                    self._logger.info(
                        "[Trace] StructureAsyncService._perform_structure_reload coalesced sphere=%s elapsed=%.2f ms",
                        sphere_id,
                        (time.perf_counter() - started_ts) * 1000.0,
                    )
                    return
                self._structure_reload_in_flight = True
                self._last_structure_reload_started_ts = time.perf_counter()
                self._logger.info(
                    "StructureAsyncService: performing full structure reload, sphere=%s",
                    sphere_id,
                )
                self.async_operations.load_structure_async(sphere_id)
                self._logger.info(
                    "[Trace] StructureAsyncService._perform_structure_reload dispatched sphere=%s elapsed=%.2f ms",
                    sphere_id,
                    (time.perf_counter() - started_ts) * 1000.0,
                )
        except Exception as exc:
            self._logger.error("_perform_structure_reload: %s", exc, exc_info=True)

    def _on_structure_loaded(self, *_args) -> None:
        reload_elapsed_ms = 0.0
        try:
            if self._last_structure_reload_started_ts > 0:
                reload_elapsed_ms = (
                    time.perf_counter() - float(self._last_structure_reload_started_ts)
                ) * 1000.0
        except Exception:
            reload_elapsed_ms = 0.0
        self._structure_reload_in_flight = False
        try:
            if len(_args) >= 2 and isinstance(_args[1], int):
                self._last_structure_reload_sphere = int(_args[1])
        except Exception:
            pass
        try:
            self._logger.info(
                "[Perf] Structure reload async complete: sphere=%s reload_total=%.2f ms",
                self._last_structure_reload_sphere,
                reload_elapsed_ms,
            )
        except Exception:
            pass
        pending = self._pending_structure_reload
        self._pending_structure_reload = None
        if pending is not None and pending != self._last_structure_reload_sphere:
            self.load_structure_async(pending)

    def _on_categories_loaded(self, _categories, section_id: int) -> None:
        try:
            sid = int(section_id)
        except Exception:
            return
        self._category_load_in_flight.discard(sid)
        self._category_inflight_since_ts.pop(sid, None)
        if sid in self._category_pending_reload:
            self._category_pending_reload.discard(sid)
            QTimer.singleShot(0, lambda sid=sid: self.load_categories_async(sid))
