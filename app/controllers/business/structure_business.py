"""Business layer for managing spheres, sections, and categories."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from app.controllers.structure_modules import (
    CacheManager,
    ValidationResult,
    handle_exceptions,
)
from app.controllers.structure_services.exporter import ExportService
from app.controllers.structure_services.importer import ImportService
from app.controllers.structure_services.integrity import IntegrityService
from app.controllers.structure_services.loader import LoaderService
from app.controllers.structure_services.selection import SelectionService
from app.controllers.structure_services.utilities import UtilityService
from app.controllers.structure_services.validation import ValidationService
from app.controllers.ui.undo.dispatcher import UndoDispatcher
from app.core.results import ErrorNotification, InvalidateRegion, Result
from app.models import Database, StructureCoordinator
from app.services.structure_service import StructureService
from app.utils.db.api import run_db

if TYPE_CHECKING:
    from app.controllers.ui.top_panels_controller import TopPanelsController

from .structure import (
    StructureAsyncService,
    StructureCacheService,
    StructureEventService,
    StructureQueryService,
    StructureValidationService,
    StructureWarmupService,
)


class StructureBusinessLogic(QObject):
    """Refactored structure business logic compatible with the legacy UI."""

    structure_loaded = pyqtSignal(list, name="structureLoaded")
    active_sphere_changed = pyqtSignal(int, name="activeSphereChanged")

    item_added = pyqtSignal(str, int, dict, name="itemAdded")
    item_updated = pyqtSignal(str, int, dict, name="itemUpdated")
    item_deleted = pyqtSignal(str, int, name="itemDeleted")
    items_batch_deleted = pyqtSignal(str, list, name="itemsBatchDeleted")

    section_selected = pyqtSignal(int, name="sectionSelected")
    category_selected = pyqtSignal(int, name="categorySelected")

    error_occurred = pyqtSignal(str, str, name="errorOccurred")
    spheres_loaded = pyqtSignal(list, name="spheresLoaded")
    _STRUCTURE_PRELOAD_IDLE_DELAY_MS = 750
    _STRUCTURE_PRELOAD_STARTUP_DELAY_MS = 2500
    _STRUCTURE_PRELOAD_MIN_INTERVAL_MS = 2000
    _STRUCTURE_PRELOAD_LONG_RUN_MS = 1000
    _STRUCTURE_PRELOAD_LONG_COOLDOWN_MS = 15000
    _STRUCTURE_PRELOAD_INTERACTIVE_COOLDOWN_MS = 3500
    _STRUCTURE_PRELOAD_POST_SWITCH_GRACE_MS = 4000

    def __init__(
        self,
        db: Database,
        parent: QObject | None = None,
        logger: logging.Logger | None = None,
    ):
        """Initialise structure business logic."""
        super().__init__(parent)

        self.db = db
        self.structure_coordinator = StructureCoordinator(db)
        self.structure_service = StructureService(db)
        self.logger = logger or logging.getLogger(__name__)

        self.current_sphere_id: int | None = None

        self.cache_manager = CacheManager(self.logger)

        self.export_service = ExportService()
        self.integrity_service = IntegrityService()
        self.loader_service = LoaderService()
        self.selection_service = SelectionService()
        self.validation_service = ValidationService()
        self.import_service = ImportService()
        self.utility_service = UtilityService()

        self.async_service = StructureAsyncService(self, self.db, self.logger)
        self.cache_service = StructureCacheService(
            owner=self,
            cache_manager=self.cache_manager,
            structure_service=self.structure_service,
            loader_service=self.loader_service,
            utility_service=self.utility_service,
            structure_coordinator=self.structure_coordinator,
            logger=self.logger,
        )
        self._result_dispatcher = UndoDispatcher(self)
        self.event_service = StructureEventService(
            owner=self,
            cache_service=self.cache_service,
            async_service=self.async_service,
            logger=self.logger,
        )
        self.warmup_service = StructureWarmupService(
            owner=self,
            cache_manager=self.cache_manager,
            utility_service=self.utility_service,
            cache_service=self.cache_service,
            async_service=self.async_service,
            logger=self.logger,
        )
        self.validation_facade = StructureValidationService(
            owner=self,
            validation_service=self.validation_service,
            utility_service=self.utility_service,
            cache_service=self.cache_service,
            structure_service=self.structure_service,
            structure_coordinator=self.structure_coordinator,
            logger=self.logger,
        )
        self.query_service = StructureQueryService(
            owner=self,
            cache_service=self.cache_service,
            validation_facade=self.validation_facade,
            logger=self.logger,
        )
        self._structure_cache_ready = False
        self._structure_preload_in_progress = False
        self._structure_preload_pending = False
        self._structure_preload_active_token: int | None = None
        self._structure_preload_handle = None
        self._structure_preload_suspended_until_monotonic: float = 0.0
        self._structure_preload_suspended_reason: str | None = None
        self._structure_preload_started_monotonic: float = 0.0
        self._structure_preload_last_finished_monotonic: float = 0.0
        self._structure_preload_cooldown_until_monotonic: float = 0.0
        self._structure_preload_interactive_until_monotonic: float = 0.0
        self._structure_preload_interactive_reason: str | None = None
        self._first_structure_loaded_completed = False
        self._structure_dirty_since_preload = False
        self._structure_mutation_generation: int = 0
        self._cached_spheres: list[dict[str, Any]] = []
        self._cached_sections: dict[int, list[dict[str, Any]]] = {}
        self._cached_categories: dict[int, list[dict[str, Any]]] = {}
        self._last_switch_started_ms: float | None = None
        self._last_selected_section_id: int | None = None
        self._batch_preferred_section_id: int | None = None
        self._last_categories_sync_load_ts: dict[int, float] = {}
        self._optimistic_categories_cache_until_ts: dict[int, float] = {}
        self._tiles_force_fresh_until_ts: dict[int, float] = {}
        self._setup_preload_timer()

        self._initialize_system()

        self._connect_internal_signals()

    def _connect_internal_signals(self) -> None:
        try:
            self.item_added.connect(self.event_service.on_item_added)
            self.item_updated.connect(self.event_service.on_item_updated)
            self.item_deleted.connect(self.event_service.on_item_deleted)
            self.items_batch_deleted.connect(self.event_service.on_items_batch_deleted)
        except (AttributeError, RuntimeError) as e:
            self.logger.warning(
                "Failed to attach internal signal handlers: %s",
                e,
                exc_info=True,
            )

        for signal in (
            self.item_added,
            self.item_updated,
            self.item_deleted,
            self.items_batch_deleted,
        ):
            try:
                signal.connect(self._handle_structure_mutation)
            except (AttributeError, RuntimeError):
                pass

        try:
            self.structure_loaded.connect(self._handle_structure_reloaded)
        except (AttributeError, RuntimeError):
            pass

        try:
            self.structure_loaded.connect(self._on_structure_loaded_warm_cache)
        except (AttributeError, RuntimeError) as e:
            self.logger.debug(
                "Failed to attach warm-cache handler to structure_loaded: %s",
                e,
                exc_info=True,
            )

    def shutdown(self, timeout: int = 5000) -> None:
        """Perform a graceful shutdown of internal services.
        
        ✅ FIX: Safe signal disconnection with individual error handling.
        """
        try:
            # ✅ Disconnect signals individually with error handling for each
            self._safe_disconnect(self.item_added, self.event_service.on_item_added)
            self._safe_disconnect(self.item_updated, self.event_service.on_item_updated)
            self._safe_disconnect(self.item_deleted, self.event_service.on_item_deleted)
            self._safe_disconnect(
                self.items_batch_deleted,
                self.event_service.on_items_batch_deleted,
            )
            self._safe_disconnect(self.item_added, self._handle_structure_mutation)
            self._safe_disconnect(self.item_updated, self._handle_structure_mutation)
            self._safe_disconnect(self.item_deleted, self._handle_structure_mutation)
            self._safe_disconnect(
                self.structure_loaded,
                self._handle_structure_reloaded,
            )
            self._safe_disconnect(
                self.structure_loaded,
                self._on_structure_loaded_warm_cache,
            )

            if getattr(self, "_result_dispatcher", None) is not None:
                self._result_dispatcher.deleteLater()
            self.async_service.shutdown(timeout=timeout)
            self.cache_manager.invalidate()
            self.logger.info("StructureBusinessLogic shutdown completed")
        except Exception as exc:
            self.logger.error(
                "Error during StructureBusinessLogic shutdown: %s",
                exc,
                exc_info=True,
            )

    def _safe_disconnect(self, signal, slot) -> bool:
        """Safely disconnect a signal from a slot."""

        try:
            signal.disconnect(slot)
            return True
        except TypeError:
            self.logger.debug(
                "Signal %s was not connected to %s",
                getattr(signal, "signal", signal),
                getattr(slot, "__name__", slot),
            )
            return False
        except RuntimeError as exc:
            self.logger.debug(
                "RuntimeError disconnecting signal %s from %s: %s",
                getattr(signal, "signal", signal),
                getattr(slot, "__name__", slot),
                exc,
            )
            return False
        except Exception as exc:
            self.logger.warning(
                "Unexpected error disconnecting signal %s from %s: %s",
                getattr(signal, "signal", signal),
                getattr(slot, "__name__", slot),
                exc,
                exc_info=True,
            )
            return False

    def _dispatch_result(
        self,
        result: Result[dict[str, Any] | None],
        *,
        description: str,
        on_success: Callable[[dict[str, Any] | None], None] | None = None,
    ) -> dict[str, Any] | None:
        def _success_adapter(payload: dict[str, Any] | None) -> None:
            try:
                if on_success:
                    on_success(payload)
            finally:
                self._handle_result_metadata(result)

        def _error_adapter(error: Exception) -> None:
            try:
                self._handle_result_metadata(result)
            finally:
                self.logger.warning("%s failed: %s", description, error)

        self._result_dispatcher.dispatch(
            result,
            on_success=_success_adapter,
            on_error=_error_adapter,
            description=description,
        )
        return result.value if result.is_success() else None

    def _handle_result_metadata(self, result: Result[object]) -> None:
        self._apply_invalidation(result.invalidate_regions)
        self._notify_errors(result.notifications)

    def _apply_invalidation(
        self, invalidate_regions: tuple[InvalidateRegion, ...]
    ) -> None:
        for region in invalidate_regions:
            if region.scope == "structure":
                self._invalidate_structure_cache()
                continue
            if region.scope == "sections" and isinstance(region.identifier, int):
                try:
                    self.cache_service.invalidate_sections_cache(region.identifier)
                except Exception:
                    self.logger.debug(
                        "Failed to invalidate sections cache for %s",
                        region.identifier,
                        exc_info=True,
                    )
                continue
            if region.scope == "categories" and isinstance(region.identifier, int):
                self._invalidate_categories_cache(region.identifier)

    def _notify_errors(
        self, notifications: tuple[ErrorNotification, ...]
    ) -> None:
        for notification in notifications:
            self._emit_error(notification.title, notification.message)

    def set_top_panels_controller(
        self, top_panels_controller: TopPanelsController
    ) -> None:
        """Inject ``TopPanelsController`` into asynchronous layers."""
        self.top_panels_controller = top_panels_controller
        self.async_service.set_top_panels_controller(top_panels_controller)

    def _initialize_system(self) -> None:
        """Initialise auxiliary components."""
        self.logger.info("StructureBusinessLogic initialised")
        self._schedule_preload_structure_async(
            reason="init",
            delay_ms=self._STRUCTURE_PRELOAD_STARTUP_DELAY_MS,
        )

    def _setup_preload_timer(self) -> None:
        self._structure_preload_timer = QTimer(self)
        self._structure_preload_timer.setSingleShot(True)
        self._structure_preload_timer.timeout.connect(self.preload_structure_async)

    def _schedule_preload_structure_async(
        self, *, reason: str, delay_ms: int | None = None
    ) -> None:
        if not getattr(self, "db", None):
            return
        if reason != "init" and not bool(self._structure_dirty_since_preload):
            return
        # Avoid competing with the very first structure load on startup.
        if not self._first_structure_loaded_completed and reason == "init":
            self._structure_preload_pending = True
            try:
                if self._structure_preload_timer.isActive():
                    self._structure_preload_timer.stop()
            except Exception:
                pass
            return
        self._structure_preload_pending = True
        delay = (
            self._STRUCTURE_PRELOAD_IDLE_DELAY_MS
            if delay_ms is None
            else max(0, int(delay_ms))
        )
        try:
            if self._structure_preload_timer.isActive():
                self._structure_preload_timer.stop()
            self._structure_preload_timer.start(delay)
            self.logger.debug(
                "Structure preload scheduled: reason=%s delay_ms=%s", reason, delay
            )
        except Exception:
            self.logger.debug(
                "Failed to schedule structure preload: reason=%s", reason, exc_info=True
            )

    def preload_structure_async(self) -> None:
        """Preload full structure snapshot asynchronously to warm caches."""
        if not getattr(self, "db", None):
            return
        # Do not preload until the first structure load has completed.
        if not self._first_structure_loaded_completed:
            self._structure_preload_pending = True
            self._schedule_preload_structure_async(
                reason="wait-first-structure",
                delay_ms=800,
            )
            return
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        if now and now < float(self._structure_preload_suspended_until_monotonic or 0.0):
            self._structure_preload_pending = True
            delay_ms = int(
                max(
                    100,
                    (float(self._structure_preload_suspended_until_monotonic) - now) * 1000.0,
                )
            )
            self._schedule_preload_structure_async(
                reason="suspended",
                delay_ms=delay_ms,
            )
            return
        if now and now < float(self._structure_preload_cooldown_until_monotonic or 0.0):
            self._structure_preload_pending = True
            delay_ms = int(
                max(
                    250,
                    (float(self._structure_preload_cooldown_until_monotonic) - now) * 1000.0,
                )
            )
            self._schedule_preload_structure_async(
                reason="cooldown",
                delay_ms=delay_ms,
            )
            return
        if now and now < float(self._structure_preload_interactive_until_monotonic or 0.0):
            self._structure_preload_pending = True
            delay_ms = int(
                max(
                    250,
                    (float(self._structure_preload_interactive_until_monotonic) - now) * 1000.0,
                )
            )
            self._schedule_preload_structure_async(
                reason="interactive-cooldown",
                delay_ms=delay_ms,
            )
            return
        if self._last_switch_started_ms is not None:
            try:
                elapsed_since_switch_ms = (
                    (float(now) - float(self._last_switch_started_ms)) * 1000.0
                )
            except Exception:
                elapsed_since_switch_ms = float(self._STRUCTURE_PRELOAD_POST_SWITCH_GRACE_MS)
            if elapsed_since_switch_ms < float(self._STRUCTURE_PRELOAD_POST_SWITCH_GRACE_MS):
                self._structure_preload_pending = True
                self._schedule_preload_structure_async(
                    reason="post-switch-grace",
                    delay_ms=int(
                        float(self._STRUCTURE_PRELOAD_POST_SWITCH_GRACE_MS)
                        - float(elapsed_since_switch_ms)
                    ),
                )
                return
        if now and self._structure_preload_last_finished_monotonic:
            elapsed_ms = (now - float(self._structure_preload_last_finished_monotonic)) * 1000.0
            if elapsed_ms < float(self._STRUCTURE_PRELOAD_MIN_INTERVAL_MS):
                self._structure_preload_pending = True
                self._schedule_preload_structure_async(
                    reason="min-interval",
                    delay_ms=int(self._STRUCTURE_PRELOAD_MIN_INTERVAL_MS - elapsed_ms),
                )
                return
        if self._structure_preload_in_progress:
            self._structure_preload_pending = True
            return

        self._structure_preload_pending = False
        self._structure_preload_in_progress = True
        self._structure_preload_started_monotonic = now or 0.0
        token = int(time.monotonic() * 1000)
        self._structure_preload_active_token = token

        self._structure_preload_handle = run_db(
            self._build_structure_snapshot,
            description="structure_preload",
            on_finished=lambda payload, t=token: self._on_structure_snapshot_ready(
                payload, t
            ),
            on_error=lambda error, t=token: self._on_structure_snapshot_error(error, t),
        )

    def _build_structure_snapshot(
        self,
    ) -> tuple[
        list[dict[str, Any]],
        dict[int, list[dict[str, Any]]],
        dict[int, list[dict[str, Any]]],
    ]:
        structure = self.db.structure_manager.get_structure_without_links() or []

        spheres: list[dict[str, Any]] = []
        sections_map: dict[int, list[dict[str, Any]]] = {}
        categories_map: dict[int, list[dict[str, Any]]] = {}

        for sphere in structure:
            try:
                raw_id = sphere.get("id")
                if raw_id is None:
                    continue
                sphere_id = int(raw_id)
            except Exception:
                continue

            sphere_copy = {key: value for key, value in sphere.items() if key != "sections"}
            sphere_copy["id"] = sphere_id
            spheres.append(sphere_copy)

            sections = sphere.get("sections") or []
            section_entries: list[dict[str, Any]] = []

            for section in sections:
                try:
                    section_id = int(section.get("id"))
                except Exception:
                    continue

                section_copy = {
                    key: value for key, value in section.items() if key != "categories"
                }
                section_copy["id"] = section_id
                section_copy["sphere_id"] = sphere_id
                section_entries.append(section_copy)

                categories = section.get("categories") or []
                category_entries: list[dict[str, Any]] = []

                for category in categories:
                    try:
                        category_id = int(category.get("id"))
                    except Exception:
                        continue

                    category_copy = {
                        key: value for key, value in category.items() if key != "links"
                    }
                    category_copy["id"] = category_id
                    category_copy["section_id"] = section_id
                    category_entries.append(category_copy)

                categories_map[section_id] = category_entries

            sections_map[sphere_id] = section_entries

        return spheres, sections_map, categories_map

    def _on_structure_snapshot_ready(
        self,
        payload: tuple[
            list[dict[str, Any]],
            dict[int, list[dict[str, Any]]],
            dict[int, list[dict[str, Any]]],
        ],
        token: int,
    ) -> None:
        if token != self._structure_preload_active_token:
            self.logger.debug(
                "Skip stale structure preload result: token=%s active=%s",
                token,
                self._structure_preload_active_token,
            )
            return

        spheres, sections_map, categories_map = payload

        self._cached_spheres = spheres
        self._cached_sections = sections_map
        self._cached_categories = categories_map
        self._structure_cache_ready = True
        self._structure_dirty_since_preload = False
        self._structure_preload_in_progress = False
        self._structure_preload_active_token = None
        try:
            finished_now = time.monotonic()
        except Exception:
            finished_now = 0.0
        self._structure_preload_last_finished_monotonic = finished_now
        try:
            run_ms = max(
                0.0,
                (float(finished_now) - float(self._structure_preload_started_monotonic or 0.0))
                * 1000.0,
            )
        except Exception:
            run_ms = 0.0
        if run_ms >= float(self._STRUCTURE_PRELOAD_LONG_RUN_MS) and finished_now:
            self._structure_preload_cooldown_until_monotonic = max(
                float(self._structure_preload_cooldown_until_monotonic or 0.0),
                float(finished_now) + (float(self._STRUCTURE_PRELOAD_LONG_COOLDOWN_MS) / 1000.0),
            )
            self.logger.debug(
                "Structure preload cooldown armed: run_ms=%.1f cooldown_ms=%s",
                run_ms,
                self._STRUCTURE_PRELOAD_LONG_COOLDOWN_MS,
            )

        # Warm up icon cache for sections/categories to avoid UI stalls
        try:
            self._warmup_structure_icons(sections_map, categories_map)
        except Exception as exc:
            self.logger.debug("Icon warmup failed: %s", exc, exc_info=True)

        try:
            self.cache_manager.set(
                "all_spheres", [dict(entry) for entry in self._cached_spheres]
            )
            for sphere_id, sections in self._cached_sections.items():
                self.cache_manager.set(
                    f"sections_{sphere_id}",
                    [dict(entry) for entry in sections],
                )
            for section_id, categories in self._cached_categories.items():
                self.cache_manager.set(
                    f"categories_{section_id}",
                    [dict(entry) for entry in categories],
                )
        except Exception as exc:
            self.logger.debug(
                "Failed to propagate structure snapshot to CacheManager: %s",
                exc,
                exc_info=True,
            )
        if self._structure_preload_pending:
            self._schedule_preload_structure_async(reason="pending-after-finish", delay_ms=0)

    def _on_structure_snapshot_error(self, error: Exception, token: int) -> None:
        if token != self._structure_preload_active_token:
            self.logger.debug(
                "Skip stale structure preload error: token=%s active=%s",
                token,
                self._structure_preload_active_token,
            )
            return
        self._structure_preload_in_progress = False
        self._structure_preload_active_token = None
        try:
            self._structure_preload_last_finished_monotonic = time.monotonic()
        except Exception:
            pass
        self.logger.warning("Structure preload failed: %s", error)
        if self._structure_preload_pending:
            self._schedule_preload_structure_async(reason="pending-after-error", delay_ms=250)

    def _warmup_structure_icons(
        self,
        sections_map: dict[int, list[dict[str, Any]]],
        categories_map: dict[int, list[dict[str, Any]]],
    ) -> None:
        """Compatibility shim for legacy preload callback path.

        Older code calls this hook after structure snapshot preload. If no concrete
        implementation is available, silently no-op to avoid exception churn.
        """
        _ = sections_map, categories_map

    def _handle_structure_mutation(self, *args, **kwargs) -> None:
        preserved_section_id: int | None = None
        preserved_categories: list[dict[str, Any]] | None = None
        try:
            item_type = str(args[0]) if args else ""
        except Exception:
            item_type = ""
        if item_type == "category" and len(args) >= 3 and isinstance(args[2], dict):
            try:
                section_hint = args[2].get("section_id", args[1])
                preserved_section_id = int(section_hint)
            except Exception:
                preserved_section_id = None
            if isinstance(preserved_section_id, int) and preserved_section_id > 0:
                try:
                    if preserved_section_id in self._cached_categories:
                        preserved_categories = [
                            dict(item)
                            for item in self._cached_categories.get(preserved_section_id, [])
                            if isinstance(item, dict)
                        ]
                    else:
                        cached = self.cache_manager.get(
                            f"categories_{preserved_section_id}"
                        )
                        if isinstance(cached, list):
                            preserved_categories = [
                                dict(item) for item in cached if isinstance(item, dict)
                            ]
                except Exception:
                    preserved_categories = None

        self._structure_mutation_generation += 1
        self._structure_cache_ready = False
        self._structure_dirty_since_preload = True
        self._cached_spheres.clear()
        self._cached_sections.clear()
        self._cached_categories.clear()
        try:
            self.cache_manager.invalidate()
        except Exception:
            pass
        if (
            isinstance(preserved_section_id, int)
            and preserved_section_id > 0
            and preserved_categories is not None
        ):
            self._cached_categories[preserved_section_id] = [
                dict(item) for item in preserved_categories
            ]
            try:
                self.cache_manager.set(
                    f"categories_{preserved_section_id}",
                    [dict(item) for item in preserved_categories],
                )
            except Exception:
                pass
        self._schedule_preload_structure_async(reason="structure-mutation")

    def current_structure_mutation_generation(self) -> int:
        return int(self._structure_mutation_generation)

    def is_structure_mutation_generation_current(self, generation: int) -> bool:
        try:
            expected = int(generation)
        except Exception:
            return False
        return expected == int(self._structure_mutation_generation)

    def _handle_structure_reloaded(self, *args, **kwargs) -> None:
        self._first_structure_loaded_completed = True

    def suspend_structure_preload(
        self, *, duration_ms: int = 1000, reason: str = "manual"
    ) -> None:
        """Pause background structure preload to avoid lock/UI contention."""
        try:
            duration = max(0, int(duration_ms))
        except Exception:
            duration = 0
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        self._structure_preload_suspended_until_monotonic = max(
            float(self._structure_preload_suspended_until_monotonic or 0.0),
            now + (duration / 1000.0),
        )
        self._structure_preload_suspended_reason = str(reason or "manual")
        try:
            if self._structure_preload_timer.isActive():
                self._structure_preload_timer.stop()
        except Exception:
            pass

    def mark_interactive_structure_activity(
        self, *, duration_ms: int | None = None, reason: str = "interactive"
    ) -> None:
        """Delay background structure preload after user-visible structure actions."""
        try:
            duration = int(duration_ms or self._STRUCTURE_PRELOAD_INTERACTIVE_COOLDOWN_MS)
        except Exception:
            duration = int(self._STRUCTURE_PRELOAD_INTERACTIVE_COOLDOWN_MS)
        duration = max(250, duration)
        try:
            now = time.monotonic()
        except Exception:
            now = 0.0
        self._structure_preload_interactive_until_monotonic = max(
            float(self._structure_preload_interactive_until_monotonic or 0.0),
            now + (duration / 1000.0),
        )
        self._structure_preload_interactive_reason = str(reason or "interactive")
        try:
            if self._structure_preload_timer.isActive():
                self._structure_preload_timer.stop()
        except Exception:
            pass

    def resume_structure_preload(
        self, *, delay_ms: int = 0, reason: str = "manual"
    ) -> None:
        """Release preload pause and reschedule pending preload if needed."""
        self._structure_preload_suspended_until_monotonic = 0.0
        self._structure_preload_suspended_reason = None
        if self._structure_preload_in_progress:
            return
        if self._structure_preload_pending or self._structure_cache_ready:
            self._schedule_preload_structure_async(
                reason=f"resume:{reason}",
                delay_ms=max(0, int(delay_ms or 0)),
            )

    def get_cached_spheres(self) -> list[dict[str, Any]]:
        if not self._structure_cache_ready:
            return []
        return [dict(entry) for entry in self._cached_spheres]

    def get_cached_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        if not self._structure_cache_ready:
            return []
        sections = self._cached_sections.get(int(sphere_id))
        if not sections:
            return []
        return [dict(entry) for entry in sections]

    def get_cached_categories(self, section_id: int) -> list[dict[str, Any]]:
        try:
            sid = int(section_id)
        except Exception:
            return []
        if sid in self._cached_categories:
            categories = self._cached_categories.get(sid) or []
            return [dict(entry) for entry in categories if isinstance(entry, dict)]
        if not self._structure_cache_ready:
            return []
        categories = self._cached_categories.get(sid)
        if not categories:
            return []
        return [dict(entry) for entry in categories if isinstance(entry, dict)]

    def prime_categories_cache(
        self,
        section_id: int,
        categories: list[dict[str, Any]] | None,
        *,
        ttl_s: float = 1.0,
    ) -> None:
        """Prime category caches for a section with already-known payload."""
        try:
            sid = int(section_id)
        except Exception:
            return
        if sid <= 0:
            return
        prepared: list[dict[str, Any]] = []
        for item in categories or []:
            if isinstance(item, dict):
                prepared.append(dict(item))
        self._cached_categories[sid] = prepared
        try:
            self.cache_manager.set(f"categories_{sid}", [dict(item) for item in prepared])
        except Exception:
            self.logger.debug(
                "prime_categories_cache: failed to propagate CacheManager section=%s",
                sid,
                exc_info=True,
            )
        now = time.perf_counter()
        self._last_categories_sync_load_ts[sid] = now
        try:
            ttl = max(0.1, float(ttl_s))
        except Exception:
            ttl = 1.0
        self._optimistic_categories_cache_until_ts[sid] = now + ttl

    def should_preserve_optimistic_categories_cache(self, section_id: int) -> bool:
        try:
            sid = int(section_id)
        except Exception:
            return False
        if sid <= 0:
            return False
        try:
            deadline = float(self._optimistic_categories_cache_until_ts.get(sid, 0.0))
        except Exception:
            deadline = 0.0
        if deadline <= 0:
            return False
        now = time.perf_counter()
        if now <= deadline:
            return True
        self._optimistic_categories_cache_until_ts.pop(sid, None)
        return False

    def set_current_sphere(self, sphere_id: int) -> None:
        """Set the currently active sphere."""
        try:
            old_sphere_id = self.current_sphere_id

            if old_sphere_id == sphere_id:
                self.logger.debug("set_current_sphere: sphere unchanged; skipping")
                return

            try:
                self._last_switch_started_ms = time.monotonic()
            except (RuntimeError, OverflowError):
                self._last_switch_started_ms = None
            try:
                self.logger.info(
                    "[Trace] set_current_sphere start old=%s new=%s started_ms=%.6f",
                    old_sphere_id,
                    sphere_id,
                    float(self._last_switch_started_ms or 0.0),
                )
            except Exception:
                pass

            self.current_sphere_id = sphere_id
            try:
                self._switch_token = getattr(self, "_switch_token", 0) + 1
            except (ValueError, TypeError, AttributeError):
                self._switch_token = 1
            self._suppress_category_restore_once = True

            if old_sphere_id != sphere_id:
                self.cache_service.invalidate_structure_cache(old_sphere_id)

            self.logger.info("Current sphere set: %s", sphere_id)
            self.active_sphere_changed.emit(sphere_id)
            try:
                self.logger.info(
                    "[Trace] set_current_sphere emitted active_sphere_changed sphere=%s",
                    sphere_id,
                )
            except Exception:
                pass

        except Exception as e:
            self._handle_error("Failed to set current sphere", e)

    @handle_exceptions(default_return=[])
    def load_structure(self, sphere_id: int | None = None) -> None:
        """Load structure for the provided sphere using optimised queries."""
        if sphere_id is not None:
            self.current_sphere_id = sphere_id

        if self.current_sphere_id is None:
            self.structure_loaded.emit([])
            return

        self.cache_service.load_structure(int(self.current_sphere_id))

    def load_structure_async(self, sphere_id: int | None = None) -> None:
        """Asynchronously load structure via ``AsyncOperations``."""
        if sphere_id is not None:
            self.current_sphere_id = sphere_id

        if not isinstance(self.current_sphere_id, int) or self.current_sphere_id <= 0:
            try:
                self.structure_loaded.emit([])
            except Exception:
                pass
            return

        try:
            self.async_service.load_structure_async(int(self.current_sphere_id))
        except Exception as e:
            self._handle_error("Failed to load structure asynchronously", e)

    def begin_batch(self) -> None:
        """Enable batch mode so per-item updates are consolidated."""
        self.event_service.begin_batch()

    def end_batch(self) -> None:
        """Disable batch mode and perform consolidated refreshes."""
        self.event_service.end_batch()

    @pyqtSlot(list)
    def _on_structure_loaded_warm_cache(self, payload: list) -> None:
        """Delegate warm-cache processing to the dedicated service."""
        self.warmup_service.warm_after_structure_loaded(payload or [])

    @handle_exceptions()
    def select_section(self, section_id: int) -> None:
        """Emit selection event and load categories for the section."""
        try:
            self._last_selected_section_id = int(section_id)
        except Exception:
            self._last_selected_section_id = None
        self.query_service.select_section(section_id)

    @handle_exceptions()
    def select_category(self, category_id: int) -> None:
        """Emit selection event for the specified category."""
        self.query_service.select_category(category_id)

    @handle_exceptions(default_return=[])
    def get_spheres(self) -> list[dict[str, Any]]:
        """Return cached list of spheres via service layer."""
        return self.query_service.get_spheres()

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        """Return cached sections for a sphere via the service layer."""
        return self.query_service.get_sections(sphere_id)

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        """Return cached categories for a section via the service layer."""
        return self.query_service.get_categories(section_id)

    def mark_tiles_force_fresh(self, section_id: int, *, window_s: float = 1.0) -> None:
        """Force tiles controller to bypass cache for a section during a short window."""
        try:
            sid = int(section_id)
            if sid <= 0:
                return
            now = time.perf_counter()
            # Opportunistic cleanup of expired marks to prevent unbounded growth.
            stale_keys = [
                key
                for key, deadline in self._tiles_force_fresh_until_ts.items()
                if float(deadline) <= now
            ]
            for key in stale_keys:
                self._tiles_force_fresh_until_ts.pop(key, None)
            self._tiles_force_fresh_until_ts[sid] = now + max(0.0, float(window_s))
        except Exception:
            return

    def should_force_fresh_tiles(self, section_id: int) -> bool:
        """Return True when tiles refresh should bypass cache for this section."""
        try:
            sid = int(section_id)
            if sid <= 0:
                return False
            deadline = float(self._tiles_force_fresh_until_ts.get(sid, 0.0))
            if deadline <= 0:
                return False
            now = time.perf_counter()
            if now <= deadline:
                return True
            self._tiles_force_fresh_until_ts.pop(sid, None)
        except Exception:
            return False
        return False

    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        """Return links for a category (legacy interface compatibility)."""
        return self.query_service.get_links(category_id)

    @handle_exceptions()
    def get_section_data(self, section_id: int) -> dict[str, Any] | None:
        """Return section payload for compatibility consumers."""
        return self.query_service.get_section_data(section_id)

    @handle_exceptions()
    def get_category_data(self, category_id: int) -> dict[str, Any] | None:
        """Return category payload for compatibility consumers."""
        return self.query_service.get_category_data(category_id)

    @handle_exceptions()
    def get_categories_by_ids(self, category_ids: list[int]) -> list[dict[str, Any]]:
        """Return categories for multiple IDs in one query."""
        return self.query_service.get_categories_by_ids(category_ids)

    @handle_exceptions()
    def get_item_for_editing(
        self, item_id: int, item_type: str | Any
    ) -> dict[str, Any] | None:
        return self.query_service.get_item_for_editing(item_id, item_type)

    def on_active_sphere_changed(self, *_args: Any) -> None:
        """React to active sphere changes from external wiring.

        Prefer asynchronous reload when available, otherwise fall back to the
        legacy synchronous loader. Errors are logged when neither is available.
        """
        self.query_service.on_active_sphere_changed()

    def get_target_section_id(self) -> int | None:
        """Compatibility wrapper returning the first category of the current sphere."""
        return self.query_service.get_target_section_id()

    @handle_exceptions()
    def create_section(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a section via the structure service and dispatch the result."""

        result = self.structure_service.create_section(data)

        def _on_success(payload: dict[str, Any] | None) -> None:
            if not isinstance(payload, dict):
                return
            sphere_id = payload.get("sphere_id")
            if isinstance(sphere_id, int):
                self.item_added.emit("section", sphere_id, payload)

        return self._dispatch_result(
            result,
            description="structure-business-create-section",
            on_success=_on_success,
        )

    @handle_exceptions()
    def update_section(
        self, section_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a section via the structure service and dispatch the result."""

        result = self.structure_service.update_section(section_id, data)

        def _on_success(payload: dict[str, Any] | None) -> None:
            if isinstance(payload, dict):
                self.item_updated.emit("section", section_id, payload)

        return self._dispatch_result(
            result,
            description="structure-business-update-section",
            on_success=_on_success,
        )

    @handle_exceptions()
    def delete_section(self, section_id: int) -> tuple[bool, dict[str, Any], int, int]:
        """Delete a section via the structure service and dispatch the result."""

        result = self.structure_service.delete_section(section_id)
        payload = result.value if isinstance(result.value, dict) else {}

        def _on_success(_: dict[str, Any] | None) -> None:
            self.item_deleted.emit("section", section_id)

        self._dispatch_result(
            result,
            description="structure-business-delete-section",
            on_success=_on_success,
        )
        categories_deleted = len(
            self.structure_service.db.categories.get_categories(section_id) or []
        )
        return (
            result.is_success(),
            payload,
            categories_deleted,
            0,
        )

    @handle_exceptions()
    def create_category(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a category via the structure service and dispatch the result."""

        result = self.structure_service.create_category(data)

        def _on_success(payload: dict[str, Any] | None) -> None:
            if not isinstance(payload, dict):
                return
            section_id = payload.get("section_id")
            if isinstance(section_id, int):
                self.item_added.emit("category", section_id, payload)

        return self._dispatch_result(
            result,
            description="structure-business-create-category",
            on_success=_on_success,
        )

    @handle_exceptions(default_return=[])
    def move_categories_batch(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        """Move categories via the structure service and handle invalidation."""

        result = self.structure_service.move_categories_to_section_bulk(
            category_ids, target_section_id, base_row
        )

        moved_ids = result.value or []
        if not result.is_success():
            self.logger.warning(
                "move_categories_batch failed: %s", result.error
            )
            self._handle_result_metadata(result)
            return []

        touched_sections: set[int] = set()
        for region in result.invalidate_regions:
            if region.scope == "categories" and isinstance(region.identifier, int):
                touched_sections.add(int(region.identifier))
        if touched_sections:
            self.event_service.replace_touched_sections(touched_sections)
        self._handle_result_metadata(result)
        return moved_ids

    @handle_exceptions(default_return=[])
    def create_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create categories in bulk via the structure service and dispatch."""

        result = self.structure_service.create_categories_bulk(items)
        created = result.value or []
        if not result.is_success():
            self.logger.warning(
                "create_categories_bulk failed: %s", result.error
            )
        self._handle_result_metadata(result)
        return created

    @handle_exceptions()
    def update_category(
        self, category_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a category via the structure service and dispatch the result."""

        result = self.structure_service.update_category(category_id, data)

        def _on_success(payload: dict[str, Any] | None) -> None:
            if isinstance(payload, dict):
                self.item_updated.emit("category", category_id, payload)

        return self._dispatch_result(
            result,
            description="structure-business-update-category",
            on_success=_on_success,
        )

    @handle_exceptions()
    def delete_category(self, category_id: int) -> tuple[bool, dict[str, Any], int]:
        """Delete a category via the structure service and dispatch the result."""

        result = self.structure_service.delete_category(category_id)
        payload = result.value if isinstance(result.value, dict) else {}

        def _on_success(_: dict[str, Any] | None) -> None:
            self.item_deleted.emit("category", category_id)

        self._dispatch_result(
            result,
            description="structure-business-delete-category",
            on_success=_on_success,
        )
        return (
            result.is_success(),
            payload,
            0,
        )

    def load_spheres_async(self) -> None:
        """Load spheres asynchronously and emit ``spheres_loaded``."""
        try:
            self.async_service.load_spheres_async()
        except Exception as e:
            self.logger.error("load_spheres_async failed: %s", e)

    @handle_exceptions()
    def get_sphere_by_id(self, sphere_id: int) -> dict[str, Any] | None:
        """Return sphere data by identifier."""
        return self.query_service.get_sphere_by_id(sphere_id)

    @handle_exceptions()
    def get_next_sphere_id(self) -> int | None:
        """Return the next sphere ID in a cyclical manner."""
        return self.query_service.get_next_sphere_id()

    @handle_exceptions(default_return=False)
    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: int | None = None
    ) -> bool:
        """Check whether a duplicate category exists within the section."""
        return self.query_service.has_duplicate_category(
            section_id, category_name, exclude_id
        )

    @handle_exceptions(default_return=False)
    def has_duplicate_section(
        self, sphere_id: int, section_name: str, exclude_id: int | None = None
    ) -> bool:
        """Check whether a duplicate section exists within the sphere.
        
        Args:
            sphere_id: Sphere ID to check within
            section_name: Section name to check
            exclude_id: Optional section ID to exclude from check (for updates)
            
        Returns:
            True if duplicate exists, False otherwise
        """
        return self.structure_coordinator.has_duplicate_section(
            sphere_id, section_name, exclude_id
        )

    def get_current_sphere_id(self) -> int | None:
        """Return the current active sphere ID."""
        return self.current_sphere_id

    def get_section_for_editing(self, section_id: int) -> dict[str, Any] | None:
        """Fetch section data for editing dialogs."""
        return self.query_service.get_section_for_editing(section_id)

    def get_category_for_editing(self, category_id: int) -> dict[str, Any] | None:
        """Fetch category data for editing dialogs."""
        return self.query_service.get_category_for_editing(category_id)

    @handle_exceptions()
    def get_category_hierarchy(self, category_id: int) -> dict[str, Any] | None:
        """Return category hierarchy (sphere_id, section_id)."""
        return self.db.categories.get_category_hierarchy(category_id)

    @handle_exceptions()
    def create_category_for_import(
        self, category_data: dict[str, Any]
    ) -> int | None:
        """Create a category during import via the structure service."""

        result = self.structure_service.create_category(category_data)

        def _on_success(payload: dict[str, Any] | None) -> None:
            if not isinstance(payload, dict):
                return
            section_id = payload.get("section_id")
            if isinstance(section_id, int):
                self.item_added.emit("category", section_id, payload)

        payload = self._dispatch_result(
            result,
            description="structure-business-create-category-import",
            on_success=_on_success,
        )
        category_id = None
        if isinstance(payload, dict):
            identifier = payload.get("id")
            if isinstance(identifier, int):
                category_id = identifier
        return category_id

    def _validate_section_data(
        self, data: dict[str, Any], section_id: int | None = None
    ) -> ValidationResult:
        """Validate section data via ``ValidationService``."""
        return self.validation_facade.validate_section_data(data, section_id)

    def _validate_category_data(
        self, data: dict[str, Any], category_id: int | None = None
    ) -> ValidationResult:
        """Validate category data via ``ValidationService``."""
        return self.validation_facade.validate_category_data(data, category_id)

    def _invalidate_structure_cache(self) -> None:
        """Backward-compatible wrapper for cache invalidation."""
        self.cache_service.invalidate_structure_cache()

    def _invalidate_categories_cache(self, section_id: int | None) -> None:
        """Backward-compatible wrapper for cache invalidation."""
        self.cache_service.invalidate_categories_cache(section_id)

    def _handle_error(self, title: str, error: Exception) -> None:
        """Log an error and emit a translated message."""
        error_msg = str(error)
        self.logger.error("%s: %s", title, error_msg, exc_info=True)
        self._emit_error(title, error_msg)

    def _emit_error(self, title: str, message: str) -> None:
        """Emit an error signal with the provided message."""
        self.error_occurred.emit(title, message)
        self.logger.error("%s: %s", title, message)

    def get_statistics(self) -> dict[str, Any]:
        """Return structure statistics via the integrity service."""
        return self.integrity_service.get_statistics(
            get_spheres=self.get_spheres,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            current_sphere_id=self.current_sphere_id,
            logger=self.logger,
        )

    def clear_all_cache(self) -> None:
        """Clear all caches for this business logic."""
        self.cache_manager.invalidate()
        self.logger.info("Cache fully cleared")
