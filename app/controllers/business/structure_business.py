
"""Business layer for managing spheres, sections, and categories."""

import logging
import time
from typing import Any, Optional, Union

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from app.controllers.structure_modules import (
    AsyncOperations,
    AsyncSignalHandlers,
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
from app.models import Database, StructureModel
from app.services.structure_service import StructureService


class StructureBusinessLogic(QObject):
    """Refactored structure business logic compatible with the legacy UI."""

    structure_loaded = pyqtSignal(list, name='structureLoaded')
    active_sphere_changed = pyqtSignal(int, name='activeSphereChanged')

    item_added = pyqtSignal(str, int, dict, name='itemAdded')
    item_updated = pyqtSignal(str, int, dict, name='itemUpdated')
    item_deleted = pyqtSignal(str, int, name='itemDeleted')
    items_batch_deleted = pyqtSignal(str, list, name='itemsBatchDeleted')

    section_selected = pyqtSignal(int, name='sectionSelected')
    category_selected = pyqtSignal(int, name='categorySelected')

    error_occurred = pyqtSignal(str, str, name='errorOccurred')
    spheres_loaded = pyqtSignal(list, name='spheresLoaded')

    def __init__(self, db: Database, parent: QObject = None, logger: Optional[logging.Logger] = None):
        """Initialise structure business logic."""
        super().__init__(parent)

        self.db = db
        self.structure_model = StructureModel(db)
        self.structure_service = StructureService(db)
        self.logger = logger or logging.getLogger(__name__)

        self.current_sphere_id: Optional[int] = None

        self.cache_manager = CacheManager(self.logger)

        self.export_service = ExportService()
        self.integrity_service = IntegrityService()
        self.loader_service = LoaderService()
        self.selection_service = SelectionService()
        self.validation_service = ValidationService()
        self.import_service = ImportService()
        self.utility_service = UtilityService()

        self.async_operations = AsyncOperations(self.db, self.logger)
        self._async_handlers = AsyncSignalHandlers(self)
        self.async_operations.connect_signal_handlers(self._async_handlers)

        self._structure_reload_timer: Optional[QTimer] = QTimer(self)
        self._structure_reload_timer.setSingleShot(True)
        self._structure_reload_timer.timeout.connect(self._perform_structure_reload)

        self._batch_mode: bool = False
        self._batch_touched_sections: set[int] = set()

        self._last_switch_started_ms: Optional[float] = None

        self._initialize_system()

        try:
            self.item_added.connect(self._on_item_added)
            self.item_updated.connect(self._on_item_updated)
            self.item_deleted.connect(self._on_item_deleted)
            self.items_batch_deleted.connect(self._on_items_batch_deleted)
        except (AttributeError, RuntimeError) as e:
            self.logger.warning(
                "Failed to attach internal signal handlers: %s",
                e, exc_info=True,
            )

        try:
            self.structure_loaded.connect(self._on_structure_loaded_warm_cache)
        except (AttributeError, RuntimeError) as e:
            self.logger.debug(
                "Failed to attach warm-cache handler to structure_loaded: %s",
                e, exc_info=True,
            )

    def shutdown(self, timeout: int = 5000) -> None:
        """Perform a graceful shutdown of internal services."""
        try:
            if self._structure_reload_timer and self._structure_reload_timer.isActive():
                self._structure_reload_timer.stop()
            async_ops = getattr(self, "async_operations", None)
            if async_ops and hasattr(async_ops, "shutdown"):
                async_ops.shutdown(timeout=timeout)
            self.cache_manager.invalidate()
            self.logger.info("StructureBusinessLogic shutdown completed")
        except Exception as exc:
            self.logger.error(
                "Error during StructureBusinessLogic shutdown: %s", exc, exc_info=True
            )

    def set_top_panels_controller(self, top_panels_controller: Any) -> None:
        """Inject ``TopPanelsController`` into asynchronous layers."""
        self.top_panels_controller = top_panels_controller
        try:
            if hasattr(self, "async_operations") and self.async_operations:
                self.async_operations.top_panels = top_panels_controller
        except AttributeError as e:
            self.logger.warning(
                "Failed to inject TopPanelsController into AsyncOperations: %s",
                e,
                exc_info=True,
            )
        try:
            if hasattr(self, "_async_handlers") and self._async_handlers:
                self._async_handlers.top_panels = top_panels_controller
        except AttributeError as e:
            self.logger.warning(
                "Failed to inject TopPanelsController into AsyncSignalHandlers: %s",
                e,
                exc_info=True,
            )

    def _initialize_system(self) -> None:
        """Initialise auxiliary components."""
        self.logger.info("StructureBusinessLogic initialised")

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

            self.current_sphere_id = sphere_id
            try:
                self._switch_token = getattr(self, "_switch_token", 0) + 1
            except (ValueError, TypeError, AttributeError):
                self._switch_token = 1
            self._suppress_category_restore_once = True

            if old_sphere_id != sphere_id:
                self.cache_manager.invalidate(f"sphere_{old_sphere_id}")

            self.logger.info("Current sphere set: %s", sphere_id)
            self.active_sphere_changed.emit(sphere_id)

        except Exception as e:
            self._handle_error(self.tr("Failed to set current sphere"), e)

    @handle_exceptions(default_return=[])
    def load_structure(self, sphere_id: Optional[int] = None) -> None:
        """Load structure for the provided sphere using optimised queries."""
        if sphere_id is not None:
            self.current_sphere_id = sphere_id

        if self.current_sphere_id is None:
            self.structure_loaded.emit([])
            return

        cache_key = f"structure_{self.current_sphere_id}"
        cached_structure = self.cache_manager.get(cache_key)

        if cached_structure is not None:
            self.structure_loaded.emit(cached_structure)
            return

        structure_data = self._load_structure_from_db(self.current_sphere_id)

        self.cache_manager.set(cache_key, structure_data)

        self.structure_loaded.emit(structure_data)
        self.logger.debug("Structure loaded for sphere %s", self.current_sphere_id)

    def load_structure_async(self, sphere_id: Optional[int] = None) -> None:
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
            self.async_operations.load_structure_async(int(self.current_sphere_id))
        except Exception as e:
            self._handle_error(self.tr("Failed to load structure asynchronously"), e)

    def _load_structure_from_db(self, sphere_id: int) -> list[dict[str, Any]]:
        """Load structure from the database (delegated to service)."""
        return self.loader_service.load_structure_from_db(
            structure_model=self.structure_model,
            sphere_id=sphere_id,
            logger=self.logger,
        )

    @pyqtSlot(str, int, dict)
    def _on_item_added(
        self, item_type: str, parent_id: int, item_data: dict[str, Any]
    ) -> None:
        """Handle item addition: invalidate cache and schedule reload."""
        try:
            self.logger.info(
                "[BL] item_added: type=%s, parent_id=%s", item_type, parent_id
            )
            if item_type == "link":
                category_id = (
                    item_data.get("category_id")
                    if isinstance(item_data, dict)
                    else None
                )
                self._invalidate_categories_cache(category_id)
                self._schedule_structure_reload()
                return
            if item_type == "category":
                section_id = parent_id or (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                self._invalidate_categories_cache(section_id)
                if isinstance(section_id, int) and section_id > 0:
                    self.async_operations.load_categories_async(section_id)
            self._invalidate_structure_cache()
            from app.config_data import app_config
            self._schedule_structure_reload(int(app_config.ui.get_structure_reload_immediate_delay_ms()))
        except Exception as e:
            self.logger.error(
                "Error in _on_item_added handler: %s", e, exc_info=True
            )

    @pyqtSlot(str, int, dict)
    def _on_item_updated(
        self, item_type: str, item_id: int, item_data: dict[str, Any]
    ) -> None:
        """Handle item update: invalidate cache and schedule reloads."""
        try:
            self.logger.info("[BL] item_updated: type=%s, id=%s", item_type, item_id)
            if item_type == "link":
                category_id = (
                    item_data.get("category_id")
                    if isinstance(item_data, dict)
                    else None
                )
                self._invalidate_categories_cache(category_id)
                return
            if item_type == "category":
                section_id = (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                self._invalidate_categories_cache(section_id)
                if self._batch_mode:
                    try:
                        if isinstance(section_id, int) and section_id > 0:
                            self._batch_touched_sections.add(int(section_id))
                    except (ValueError, TypeError) as ex:
                        self.logger.debug(
                            "_on_item_updated: batch mode failed to add touched section id=%s: %s",
                            section_id,
                            ex,
                        )
                    return
                if isinstance(section_id, int) and section_id > 0:
                    self.async_operations.load_categories_async(section_id)
            self._invalidate_structure_cache()
            self._schedule_structure_reload(0)
        except Exception as e:
            self.logger.error(
                "Error in _on_item_updated handler: %s", e
            )

    def begin_batch(self) -> None:
        """Enable batch mode so per-item updates are consolidated."""
        try:
            self._batch_mode = True
            self._batch_touched_sections.clear()
        except Exception:
            self._batch_mode = True

    def end_batch(self) -> None:
        """Disable batch mode and perform consolidated refreshes."""
        try:
            touched = set(self._batch_touched_sections)
        except Exception as exc:
            self.logger.debug("end_batch: failed to copy touched sections: %s", exc)
            touched = set()
        finally:
            self._batch_touched_sections.clear()
            self._batch_mode = False

        try:
            for sid in touched:
                try:
                    if isinstance(sid, int) and sid > 0:
                        self.async_operations.load_categories_async(int(sid))
                except Exception as exc:
                    self.logger.debug(
                        "end_batch: failed to schedule load_categories_async for %s: %s",
                        sid,
                        exc,
                        exc_info=True,
                    )
        except Exception as exc:
            self.logger.debug(
                "end_batch: failed to iterate touched sections: %s", exc, exc_info=True
            )

        try:
            self._invalidate_structure_cache()
            from app.config_data import app_config
            self._schedule_structure_reload(int(app_config.ui.get_structure_reload_immediate_delay_ms()))
        except Exception as exc:
            self.logger.debug(
                "end_batch: failed to schedule structure reload: %s", exc, exc_info=True
            )

    def _schedule_structure_reload(self, delay_ms: Optional[int] = None) -> None:
        """Schedule a delayed structure reload (debounces frequent events)."""
        try:
            from app.config_data import app_config
            if delay_ms is None:
                delay_ms = int(app_config.ui.get_structure_reload_delay_ms())
            if not isinstance(delay_ms, int) or delay_ms < 0:
                delay_ms = int(app_config.ui.get_structure_reload_delay_ms())
            if self._structure_reload_timer.isActive():
                self._structure_reload_timer.stop()
            self._structure_reload_timer.start(delay_ms)
        except Exception as e:
            self.logger.warning(
                "_schedule_structure_reload failed to schedule: %s", e, exc_info=True
            )

    def _perform_structure_reload(self) -> None:
        """Perform the actual reload for the current sphere structure."""
        try:
            self._invalidate_structure_cache()
            sphere_id = self.current_sphere_id
            if isinstance(sphere_id, int) and sphere_id > 0:
                self.async_operations.load_structure_async(sphere_id)
        except Exception as e:
            self.logger.error("_perform_structure_reload: %s", e, exc_info=True)

    @pyqtSlot(list)
    def _on_structure_loaded_warm_cache(self, _payload: list) -> None:  # noqa: C901
        """Warm per-sphere cache for the first category after structure load.

        Prefer using the loaded payload to avoid additional synchronous DB queries
        during sphere switches. If the payload lacks categories, defer computation
        via ``QTimer.singleShot(0)`` to keep the UI responsive. Errors are logged at
        debug level only.
        """
        try:
            sphere_id = self.current_sphere_id
            if not isinstance(sphere_id, int) or sphere_id <= 0:
                return

            if isinstance(_payload, list):
                for section in _payload:
                    try:
                        cats = section.get("categories") if isinstance(section, dict) else None
                    except (AttributeError, TypeError):
                        cats = None
                    if cats:
                        first = cats[0]
                        cid = first.get("id") if isinstance(first, dict) else None
                        if isinstance(cid, int) and cid > 0:
                            self.cache_manager.set(f"first_category_id:{sphere_id}", cid)

            def _deferred_warmup() -> None:
                try:
                    _ = self.utility_service.get_target_section_id(
                        current_sphere_id=sphere_id,
                        get_sections=self.get_sections,
                        get_categories=self.get_categories,
                        cache_get=self.cache_manager.get,
                        cache_set=self.cache_manager.set,
                    )
                except Exception as ex:
                    self.logger.debug("Deferred warm cache failed: %s", ex, exc_info=True)

            try:
                QTimer.singleShot(0, _deferred_warmup)
            except (RuntimeError, TypeError):
                _deferred_warmup()

            try:
                _deferred_warmup()
            except Exception as ex:
                self.logger.debug("Immediate warm cache failed: %s", ex, exc_info=True)

            try:
                if isinstance(_payload, list) and _payload:
                    from app.config_data import app_config
                    preload_limit = int(app_config.ui.get_preload_categories_limit())
                    delay_step_ms = int(app_config.ui.get_preload_delay_step_ms())
                    planned_token = int(getattr(self, "_switch_token", 0))
                    planned_sphere = sphere_id
                    for idx, section in enumerate(_payload[:preload_limit]):
                        sid = section.get("id") if isinstance(section, dict) else None
                        if not isinstance(sid, int) or sid <= 0:
                            continue
                        delay = max(0, int(idx) * delay_step_ms)

                        def _preload_one(section_id: int = sid, token: int = planned_token, psid: int = planned_sphere) -> None:
                            try:
                                if int(getattr(self, "_switch_token", 0)) != int(token):
                                    return
                                cur = getattr(self, "current_sphere_id", None)
                                if cur != psid:
                                    return
                                ops = getattr(self, "async_operations", None)
                                if ops and hasattr(ops, "load_categories_async"):
                                    ops.load_categories_async(section_id)
                            except Exception as ex:
                                self.logger.debug("Preload categories failed: %s", ex, exc_info=True)

                        QTimer.singleShot(delay, _preload_one)
            except Exception:
                self.logger.debug("Warm cache: preload categories scheduling failed", exc_info=True)
        except Exception as e:
            try:
                self.logger.debug("Warm cache after structure_loaded failed: %s", e, exc_info=True)
            except Exception:
                pass

    @pyqtSlot(str, int)
    def _on_item_deleted(self, item_type: str, item_id: int) -> None:
        """Handle deletion: invalidate caches and schedule asynchronous reload."""
        try:
            self.logger.info("[BL] item_deleted: type=%s, id=%s", item_type, item_id)
            if item_type == "link":
                self._schedule_structure_reload()
                return
            self._invalidate_structure_cache()
            self._schedule_structure_reload(0)
        except Exception as e:
            self.logger.error(
                "Error in _on_item_deleted handler: %s", e, exc_info=True
            )

    @pyqtSlot(str, list)
    def _on_items_batch_deleted(self, item_type: str, ids: list) -> None:
        """Handle batch deletions with a single cache invalidation and reload."""
        try:
            total = len(ids) if isinstance(ids, (list, tuple)) else 0
            self.logger.info(
                "[BL] items_batch_deleted: type=%s, count=%s", item_type, total
            )
            if item_type == "link":
                self._schedule_structure_reload()
                return
            self._invalidate_structure_cache()
            self._schedule_structure_reload(0)
        except Exception as e:
            self.logger.error(
                "Error in _on_items_batch_deleted handler: %s", e, exc_info=True
            )

    @handle_exceptions()
    def select_section(self, section_id: int) -> None:
        """Emit selection event and load categories for the section."""
        categories = self.get_categories(section_id)
        self.section_selected.emit(section_id)
        self.logger.debug(
            "Section %s selected with %s categories", section_id, len(categories)
        )

    @handle_exceptions()
    def select_category(self, category_id: int) -> None:
        """Emit selection event for the specified category."""
        self.category_selected.emit(category_id)
        self.logger.debug("Category %s selected", category_id)

    @handle_exceptions(default_return=[])
    def get_spheres(self) -> list[dict[str, Any]]:
        """Return cached list of spheres via service layer."""
        cache_key = "all_spheres"
        cached_spheres = self.cache_manager.get(cache_key)
        if cached_spheres is not None:
            return cached_spheres
        spheres = self.structure_service.get_spheres()
        self.cache_manager.set(cache_key, spheres)
        return spheres or []

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        """Return cached sections for a sphere via the service layer."""
        cache_key = f"sections_{sphere_id}"
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
        sections = self.structure_service.get_sections(sphere_id)
        self.cache_manager.set(cache_key, sections)
        return sections or []

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        """Return cached categories for a section via the service layer."""
        cache_key = f"categories_{section_id}"
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            return cached
        categories = self.structure_service.get_categories(section_id)
        self.cache_manager.set(cache_key, categories)
        return categories or []

    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        """Return links for a category (legacy interface compatibility)."""
        return self.utility_service.get_links(
            self.structure_model, category_id, self.logger
        )

    @handle_exceptions()
    def get_item_for_editing(self, item_id: int, item_type: Union[str, Any]) -> Optional[dict[str, Any]]:
        return self.utility_service.get_item_for_editing(
            item_id=item_id,
            item_type=item_type,
            get_section_data=self.structure_model.get_section_data,
            get_category_data=self.structure_model.get_category_data,
            logger=self.logger,
        )

    def on_active_sphere_changed(self, *_args: Any) -> None:
        """React to active sphere changes from external wiring.

        Prefer asynchronous reload when available, otherwise fall back to the
        synchronous ``load_structure()`` helper.
{{ ... }}
        """
        loader_async = getattr(self, "load_structure_async", None)
        if callable(loader_async):
            loader_async()
            return

        loader_sync = getattr(self, "load_structure", None)
        if callable(loader_sync):
            loader_sync()
            return

        self.logger.error(
            "StructureBusinessLogic has no load_structure_async() or load_structure(); skipping reload"
        )

    def get_target_section_id(self) -> Optional[int]:
        """Compatibility wrapper returning the first category of the current sphere."""
        return self.utility_service.get_target_section_id(
            current_sphere_id=self.current_sphere_id,
            get_sections=self.get_sections,
            get_categories=self.get_categories,
            cache_get=self.cache_manager.get,
            cache_set=self.cache_manager.set,
        )

    @handle_exceptions()
    def create_section(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Create a section, emit signals, and invalidate caches."""
        section_id = self.structure_service.create_section(data)
        if not section_id:
            return None
        section_data = self.structure_service.get_section_by_id(section_id) or {}
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        try:
            self.item_added.emit(
                "section", int(sphere_id) if sphere_id else 0, section_data
            )
        finally:
            if sphere_id:
                self.cache_manager.invalidate(f"sections_{sphere_id}")
            self._invalidate_structure_cache()
        return section_data or None

    @handle_exceptions()
    def update_section(
        self, section_id: int, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a section via the service, emit signals, and invalidate caches."""
        ok = self.structure_service.update_section(section_id, data)
        if not ok:
            return None
        section_data = self.structure_service.get_section_by_id(section_id) or {}
        sphere_id = (
            section_data.get("sphere_id") if isinstance(section_data, dict) else None
        )
        try:
            self.item_updated.emit("section", section_id, section_data)
        finally:
            if sphere_id:
                self.cache_manager.invalidate(f"sections_{sphere_id}")
            self._invalidate_structure_cache()
        return section_data or None

    @handle_exceptions()
    def delete_section(self, section_id: int) -> tuple[bool, dict[str, Any], int, int]:
        """Delete a section. Return (success flag, data, categories count, links count)."""
        section_before = self.structure_service.get_section_by_id(section_id) or {}
        if not section_before:
            return False, {}, 0, 0
        sphere_id = (
            section_before.get("sphere_id")
            if isinstance(section_before, dict)
            else None
        )
        categories_before = (
            self.structure_service.get_categories(section_before.get("id", section_id))
            if section_before
            else []
        )
        categories_count = len(categories_before or [])
        success = self.structure_service.delete_section(section_id)
        if success:
            try:
                self.item_deleted.emit("section", section_id)
            finally:
                if sphere_id:
                    self.cache_manager.invalidate(f"sections_{sphere_id}")
                self._invalidate_structure_cache()
        return success, section_before, categories_count, 0

    @handle_exceptions()
    def create_category(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Create a category via the service and invalidate caches."""
        category_id = self.structure_service.create_category(data)
        if not category_id:
            return None
        category_data = self.structure_service.get_category_by_id(category_id) or {}
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        try:
            self.item_added.emit(
                "category", int(section_id) if section_id else 0, category_data
            )
        finally:
            self._invalidate_categories_cache(section_id)
        return category_data or None

    @handle_exceptions(default_return=[])
    def move_categories_batch(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        """Move categories to the target section in a single batch transaction."""
        if (
            not category_ids
            or not isinstance(target_section_id, int)
            or target_section_id <= 0
        ):
            return []

        source_sections: set[int] = set()
        try:
            for cid in category_ids:
                try:
                    cdata = self.structure_service.get_category_by_id(int(cid))
                except Exception:
                    cdata = None
                if isinstance(cdata, dict):
                    sid = cdata.get("section_id")
                    if isinstance(sid, int) and sid > 0 and sid != target_section_id:
                        source_sections.add(int(sid))
        except Exception:
            source_sections = set()

        self.begin_batch()
        try:
            moved_ids = self.structure_service.move_categories_to_section_bulk(
                category_ids, target_section_id, base_row
            )

            try:
                for sid in source_sections:
                    self._invalidate_categories_cache(sid)
            except Exception:
                pass
            self._invalidate_categories_cache(target_section_id)

            return moved_ids or []
        finally:
            self.end_batch()

    @handle_exceptions(default_return=[])
    def create_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create categories in bulk and emit UI signals."""
        if not items:
            return []
        created_or_existing = self.structure_service.create_categories_bulk(items)
        try:
            touched_sections = {
                c.get("section_id")
                for c in (created_or_existing or [])
                if isinstance(c, dict)
            }
            for sid in touched_sections:
                if sid:
                    self._invalidate_categories_cache(sid)
            from app.config_data import app_config
            self._schedule_structure_reload(int(app_config.ui.get_structure_reload_immediate_delay_ms()))
        except Exception:
            pass
        return created_or_existing or []

    @handle_exceptions()
    def update_category(
        self, category_id: int, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a category via the service, emit signal, and invalidate cache."""
        ok = self.structure_service.update_category(category_id, data)
        if not ok:
            return None
        category_data = self.structure_service.get_category_by_id(category_id) or {}
        section_id = (
            category_data.get("section_id") if isinstance(category_data, dict) else None
        )
        try:
            self.item_updated.emit("category", category_id, category_data)
        finally:
            self._invalidate_categories_cache(section_id)
        return category_data or None

    @handle_exceptions()
    def delete_category(self, category_id: int) -> tuple[bool, dict[str, Any], int]:
        """Delete a category. Return (success, payload, links count placeholder)."""
        category_before = self.structure_service.get_category_by_id(category_id) or {}
        if not category_before:
            return False, {}, 0
        section_id = (
            category_before.get("section_id")
            if isinstance(category_before, dict)
            else None
        )
        success = self.structure_service.delete_category(category_id)
        if success:
            try:
                self.item_deleted.emit("category", category_id)
            finally:
                self._invalidate_categories_cache(section_id)
        return success, category_before, 0

    def load_spheres_async(self) -> None:
        """Load spheres asynchronously and emit ``spheres_loaded``."""
        try:
            self.async_operations.load_spheres_async()
        except Exception as e:
            self.logger.error("load_spheres_async failed: %s", e)

    @handle_exceptions()
    def get_sphere_by_id(self, sphere_id: int) -> Optional[dict[str, Any]]:
        """Return sphere data by identifier."""
        spheres = self.get_spheres()
        return next((sphere for sphere in spheres if sphere["id"] == sphere_id), None)

    @handle_exceptions()
    def get_next_sphere_id(self) -> Optional[int]:
        """Return the next sphere ID in a cyclical manner."""
        spheres = self.get_spheres()
        if not spheres:
            return None

        if self.current_sphere_id is None:
            return spheres[0]["id"]

        current_index = next(
            (
                i
                for i, sphere in enumerate(spheres)
                if sphere["id"] == self.current_sphere_id
            ),
            -1,
        )

        if current_index == -1:
            return spheres[0]["id"]

        next_index = (current_index + 1) % len(spheres)
        return spheres[next_index]["id"]

    @handle_exceptions(default_return=False)
    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Check whether a duplicate category exists within the section."""
        categories = self.get_categories(section_id)

        for category in categories:
            if (
                category["name"].lower() == category_name.lower().strip()
                and category["id"] != exclude_id
            ):
                return True

        return False

    def get_current_sphere_id(self) -> Optional[int]:
        """Return the current active sphere ID."""
        return self.current_sphere_id

    def get_section_for_editing(self, section_id: int) -> Optional[dict[str, Any]]:
        """Fetch section data for editing dialogs."""
        return self.get_item_for_editing(section_id, "section")

    def get_category_for_editing(self, category_id: int) -> Optional[dict[str, Any]]:
        """Fetch category data for editing dialogs."""
        return self.get_item_for_editing(category_id, "category")

    @handle_exceptions()
    def create_category_for_import(
        self, category_data: dict[str, Any]
    ) -> Optional[int]:
        """Create a category during import (delegated to the service layer)."""
        category_id = self.import_service.create_category_for_import(
            self.structure_model, category_data, self.logger
        )
        if category_id:
            section_id = category_data.get("section_id")
            if section_id:
                self._invalidate_categories_cache(section_id)
        return category_id

    def _validate_section_data(
        self, data: dict[str, Any], section_id: Optional[int] = None
    ) -> ValidationResult:
        """Validate section data via ``ValidationService``."""
        return self.validation_service.validate_section_data(
            data=data,
            section_id=section_id,
            get_sections=self.get_sections,
        )

    def _validate_category_data(
        self, data: dict[str, Any], category_id: Optional[int] = None
    ) -> ValidationResult:
        """Validate category data via ``ValidationService``."""
        return self.validation_service.validate_category_data(
            data=data,
            category_id=category_id,
            has_duplicate_category=self.has_duplicate_category,
        )

    def _invalidate_structure_cache(self) -> None:
        """Invalidate cached structure data."""
        if self.current_sphere_id:
            self.cache_manager.invalidate(f"structure_{self.current_sphere_id}")
            self.cache_manager.invalidate(f"sections_{self.current_sphere_id}")
            self.cache_manager.invalidate(f"first_category_id:{self.current_sphere_id}")

    def _invalidate_categories_cache(self, section_id: Optional[int]) -> None:
        """Invalidate cached categories for the provided section."""
        if section_id:
            self.cache_manager.invalidate(f"categories_{section_id}")

        self._invalidate_structure_cache()

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
