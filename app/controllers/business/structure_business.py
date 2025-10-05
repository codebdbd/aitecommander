"""Business layer for managing spheres, sections, and categories."""

import logging
import time
from typing import Any, Optional, Union

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from app.controllers.structure_modules import CacheManager, ValidationResult, handle_exceptions
from app.controllers.structure_services.exporter import ExportService
from app.controllers.structure_services.importer import ImportService
from app.controllers.structure_services.integrity import IntegrityService
from app.controllers.structure_services.loader import LoaderService
from app.controllers.structure_services.selection import SelectionService
from app.controllers.structure_services.utilities import UtilityService
from app.controllers.structure_services.validation import ValidationService
from app.models import Database, StructureModel
from app.services.structure_service import StructureService

from .structure import (
    StructureAsyncService,
    StructureCacheService,
    StructureCrudService,
    StructureValidationService,
)


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

        self.async_service = StructureAsyncService(self, self.db, self.logger)
        self.cache_service = StructureCacheService(
            owner=self,
            cache_manager=self.cache_manager,
            structure_service=self.structure_service,
            loader_service=self.loader_service,
            utility_service=self.utility_service,
            structure_model=self.structure_model,
            logger=self.logger,
        )
        self.crud_service = StructureCrudService(
            owner=self,
            structure_service=self.structure_service,
            cache_service=self.cache_service,
            async_service=self.async_service,
            import_service=self.import_service,
            structure_model=self.structure_model,
            logger=self.logger,
        )
        self.validation_facade = StructureValidationService(
            owner=self,
            validation_service=self.validation_service,
            utility_service=self.utility_service,
            cache_service=self.cache_service,
            structure_service=self.structure_service,
            structure_model=self.structure_model,
            logger=self.logger,
        )

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
            self.async_service.shutdown(timeout=timeout)
            self.cache_manager.invalidate()
            self.logger.info("StructureBusinessLogic shutdown completed")
        except Exception as exc:
            self.logger.error(
                "Error during StructureBusinessLogic shutdown: %s", exc, exc_info=True
            )

    def set_top_panels_controller(self, top_panels_controller: Any) -> None:
        """Inject ``TopPanelsController`` into asynchronous layers."""
        self.top_panels_controller = top_panels_controller
        self.async_service.set_top_panels_controller(top_panels_controller)

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
                self.cache_service.invalidate_structure_cache(old_sphere_id)

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

        self.cache_service.load_structure(int(self.current_sphere_id))

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
            self.async_service.load_structure_async(int(self.current_sphere_id))
        except Exception as e:
            self._handle_error(self.tr("Failed to load structure asynchronously"), e)

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
                self.cache_service.invalidate_categories_cache(category_id)
                self.async_service.schedule_structure_reload()
                return
            if item_type == "category":
                section_id = parent_id or (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                self.cache_service.invalidate_categories_cache(section_id)
                if isinstance(section_id, int) and section_id > 0:
                    self.async_service.load_categories_async(section_id)
            self.cache_service.invalidate_structure_cache()
            from app.config_data import app_config
            self.async_service.schedule_structure_reload(
                int(app_config.ui.get_structure_reload_immediate_delay_ms())
            )
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
                self.cache_service.invalidate_categories_cache(category_id)
                return
            if item_type == "category":
                section_id = (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                self.cache_service.invalidate_categories_cache(section_id)
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
                    self.async_service.load_categories_async(section_id)
            self.cache_service.invalidate_structure_cache()
            self.async_service.schedule_structure_reload(0)
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
                        self.async_service.load_categories_async(int(sid))
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
            self.cache_service.invalidate_structure_cache()
            from app.config_data import app_config
            self.async_service.schedule_structure_reload(
                int(app_config.ui.get_structure_reload_immediate_delay_ms())
            )
        except Exception as exc:
            self.logger.debug(
                "end_batch: failed to schedule structure reload: %s", exc, exc_info=True
            )

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
                self.async_service.schedule_structure_reload()
                return
            self.cache_service.invalidate_structure_cache()
            self.async_service.schedule_structure_reload(0)
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
                self.async_service.schedule_structure_reload()
                return
            self.cache_service.invalidate_structure_cache()
            self.async_service.schedule_structure_reload(0)
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
        return self.cache_service.get_spheres()

    def get_sections(self, sphere_id: int) -> list[dict[str, Any]]:
        """Return cached sections for a sphere via the service layer."""
        return self.cache_service.get_sections(sphere_id)

    def get_categories(self, section_id: int) -> list[dict[str, Any]]:
        """Return cached categories for a section via the service layer."""
        return self.cache_service.get_categories(section_id)

    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        """Return links for a category (legacy interface compatibility)."""
        return self.validation_facade.get_links(category_id)

    @handle_exceptions()
    def get_section_data(self, section_id: int) -> Optional[dict[str, Any]]:
        """Return section payload for compatibility consumers."""
        return self.validation_facade.get_section_data(section_id)

    @handle_exceptions()
    def get_category_data(self, category_id: int) -> Optional[dict[str, Any]]:
        """Return category payload for compatibility consumers."""
        return self.validation_facade.get_category_data(category_id)

    @handle_exceptions()
    def get_item_for_editing(self, item_id: int, item_type: Union[str, Any]) -> Optional[dict[str, Any]]:
        return self.validation_facade.get_item_for_editing(item_id, item_type)

    def on_active_sphere_changed(self, *_args: Any) -> None:
        """React to active sphere changes from external wiring.

        Prefer asynchronous reload when available, otherwise fall back to the
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
        return self.cache_service.get_target_section_id()

    @handle_exceptions()
    def create_section(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Create a section via the CRUD service."""
        return self.crud_service.create_section(data)

    @handle_exceptions()
    def update_section(
        self, section_id: int, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a section via the CRUD service."""
        return self.crud_service.update_section(section_id, data)

    @handle_exceptions()
    def delete_section(self, section_id: int) -> tuple[bool, dict[str, Any], int, int]:
        """Delegate section removal to the CRUD service."""
        return self.crud_service.delete_section(section_id)

    @handle_exceptions()
    def create_category(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Create a category via the CRUD service."""
        return self.crud_service.create_category(data)

    @handle_exceptions(default_return=[])
    def move_categories_batch(
        self, category_ids: list[int], target_section_id: int, base_row: int = 0
    ) -> list[int]:
        """Move categories via the CRUD service."""
        return self.crud_service.move_categories_batch(
            category_ids, target_section_id, base_row
        )

    @handle_exceptions(default_return=[])
    def create_categories_bulk(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create categories in bulk via the CRUD service."""
        return self.crud_service.create_categories_bulk(items)

    @handle_exceptions()
    def update_category(
        self, category_id: int, data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a category via the CRUD service."""
        return self.crud_service.update_category(category_id, data)

    @handle_exceptions()
    def delete_category(self, category_id: int) -> tuple[bool, dict[str, Any], int]:
        """Delete a category via the CRUD service."""
        return self.crud_service.delete_category(category_id)

    def load_spheres_async(self) -> None:
        """Load spheres asynchronously and emit ``spheres_loaded``."""
        try:
            self.async_service.load_spheres_async()
        except Exception as e:
            self.logger.error("load_spheres_async failed: %s", e)

    @handle_exceptions()
    def get_sphere_by_id(self, sphere_id: int) -> Optional[dict[str, Any]]:
        """Return sphere data by identifier."""
        return self.validation_facade.get_sphere_by_id(sphere_id)

    @handle_exceptions()
    def get_next_sphere_id(self) -> Optional[int]:
        """Return the next sphere ID in a cyclical manner."""
        return self.validation_facade.get_next_sphere_id()

    @handle_exceptions(default_return=False)
    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Check whether a duplicate category exists within the section."""
        return self.validation_facade.has_duplicate_category(
            section_id, category_name, exclude_id
        )

    def get_current_sphere_id(self) -> Optional[int]:
        """Return the current active sphere ID."""
        return self.current_sphere_id

    def get_section_for_editing(self, section_id: int) -> Optional[dict[str, Any]]:
        """Fetch section data for editing dialogs."""
        return self.validation_facade.get_section_for_editing(section_id)

    def get_category_for_editing(self, category_id: int) -> Optional[dict[str, Any]]:
        """Fetch category data for editing dialogs."""
        return self.validation_facade.get_category_for_editing(category_id)

    @handle_exceptions()
    def create_category_for_import(
        self, category_data: dict[str, Any]
    ) -> Optional[int]:
        """Create a category during import via the CRUD service."""
        return self.crud_service.create_category_for_import(category_data)

    def _validate_section_data(
        self, data: dict[str, Any], section_id: Optional[int] = None
    ) -> ValidationResult:
        """Validate section data via ``ValidationService``."""
        return self.validation_facade.validate_section_data(data, section_id)

    def _validate_category_data(
        self, data: dict[str, Any], category_id: Optional[int] = None
    ) -> ValidationResult:
        """Validate category data via ``ValidationService``."""
        return self.validation_facade.validate_category_data(data, category_id)

    def _invalidate_structure_cache(self) -> None:
        """Backward-compatible wrapper for cache invalidation."""
        self.cache_service.invalidate_structure_cache()

    def _invalidate_categories_cache(self, section_id: Optional[int]) -> None:
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
