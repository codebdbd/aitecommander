"""Business layer for managing spheres, sections, and categories."""

import logging
import time
from typing import Any, Optional, Union, List, Dict, TYPE_CHECKING

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

if TYPE_CHECKING:
    from app.controllers.ui.top_panels_controller import TopPanelsController

from .structure import (
    StructureAsyncService,
    StructureCacheService,
    StructureCrudService,
    StructureEventService,
    StructureQueryService,
    StructureValidationService,
    StructureWarmupService,
)
from .structure.crud_service import MoveCategoriesBatchResult


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
            structure_model=self.structure_model,
            logger=self.logger,
        )
        self.query_service = StructureQueryService(
            owner=self,
            cache_service=self.cache_service,
            validation_facade=self.validation_facade,
            logger=self.logger,
        )
        self._last_switch_started_ms: Optional[float] = None

        self._initialize_system()

        try:
            self.item_added.connect(self.event_service.on_item_added)
            self.item_updated.connect(self.event_service.on_item_updated)
            self.item_deleted.connect(self.event_service.on_item_deleted)
            self.items_batch_deleted.connect(self.event_service.on_items_batch_deleted)
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
            # Disconnect only the signals connected within this class instance
            try:
                self.item_added.disconnect(self.event_service.on_item_added)
                self.item_updated.disconnect(self.event_service.on_item_updated)
                self.item_deleted.disconnect(self.event_service.on_item_deleted)
                self.items_batch_deleted.disconnect(self.event_service.on_items_batch_deleted)
                self.structure_loaded.disconnect(self._on_structure_loaded_warm_cache)
            except (TypeError, RuntimeError) as e:
                self.logger.debug("Error while disconnecting signals: %s", e)

            self.async_service.shutdown(timeout=timeout)
            self.cache_manager.invalidate()
            self.logger.info("StructureBusinessLogic shutdown completed")
        except Exception as exc:
            self.logger.error(
                "Error during StructureBusinessLogic shutdown: %s", exc, exc_info=True
            )

    def set_top_panels_controller(self, top_panels_controller: 'TopPanelsController') -> None:
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
            self._handle_error("Failed to set current sphere", e)

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
        self.query_service.select_section(section_id)

    @handle_exceptions()
    def select_category(self, category_id: int) -> None:
        """Emit selection event for the specified category."""
        self.query_service.select_category(category_id)

    @handle_exceptions(default_return=[])
    def get_spheres(self) -> List[Dict[str, Any]]:
        """Return cached list of spheres via service layer."""
        return self.query_service.get_spheres()

    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Return cached sections for a sphere via the service layer."""
        return self.query_service.get_sections(sphere_id)

    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        """Return cached categories for a section via the service layer."""
        return self.query_service.get_categories(section_id)

    def get_links(self, category_id: int) -> List[Dict[str, Any]]:
        """Return links for a category (legacy interface compatibility)."""
        return self.query_service.get_links(category_id)

    @handle_exceptions()
    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Return section payload for compatibility consumers."""
        return self.query_service.get_section_data(section_id)

    @handle_exceptions()
    def get_category_data(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Return category payload for compatibility consumers."""
        return self.query_service.get_category_data(category_id)

    @handle_exceptions()
    def get_item_for_editing(self, item_id: int, item_type: Union[str, Any]) -> Optional[Dict[str, Any]]:
        return self.query_service.get_item_for_editing(item_id, item_type)

    def on_active_sphere_changed(self, *_args: Any) -> None:
        """React to active sphere changes from external wiring.

        Prefer asynchronous reload when available, otherwise fall back to the
        legacy synchronous loader. Errors are logged when neither is available.
        """
        self.query_service.on_active_sphere_changed()

    def get_target_section_id(self) -> Optional[int]:
        """Compatibility wrapper returning the first category of the current sphere."""
        return self.query_service.get_target_section_id()

    @handle_exceptions()
    def create_section(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a section via the CRUD service."""
        return self.crud_service.create_section(data)

    @handle_exceptions()
    def update_section(
        self, section_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a section via the CRUD service."""
        return self.crud_service.update_section(section_id, data)

    @handle_exceptions()
    def delete_section(self, section_id: int) -> tuple[bool, Dict[str, Any], int, int]:
        """Delegate section removal to the CRUD service."""
        return self.crud_service.delete_section(section_id)

    @handle_exceptions()
    def create_category(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a category via the CRUD service."""
        return self.crud_service.create_category(data)

    @handle_exceptions(default_return=[])
    def move_categories_batch(
        self, category_ids: List[int], target_section_id: int, base_row: int = 0
    ) -> List[int]:
        """Move categories via the CRUD service."""
        result = self.crud_service.move_categories_batch(
            category_ids, target_section_id, base_row
        )
        if isinstance(result, MoveCategoriesBatchResult):
            if result.touched_sections:
                self.event_service.replace_touched_sections(result.touched_sections)
            return result.moved_ids
        return result or []

    @handle_exceptions(default_return=[])
    def create_categories_bulk(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create categories in bulk via the CRUD service."""
        return self.crud_service.create_categories_bulk(items)

    @handle_exceptions()
    def update_category(
        self, category_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a category via the CRUD service."""
        return self.crud_service.update_category(category_id, data)

    @handle_exceptions()
    def delete_category(self, category_id: int) -> tuple[bool, Dict[str, Any], int]:
        """Delete a category via the CRUD service."""
        return self.crud_service.delete_category(category_id)

    def load_spheres_async(self) -> None:
        """Load spheres asynchronously and emit ``spheres_loaded``."""
        try:
            self.async_service.load_spheres_async()
        except Exception as e:
            self.logger.error("load_spheres_async failed: %s", e)

    @handle_exceptions()
    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Return sphere data by identifier."""
        return self.query_service.get_sphere_by_id(sphere_id)

    @handle_exceptions()
    def get_next_sphere_id(self) -> Optional[int]:
        """Return the next sphere ID in a cyclical manner."""
        return self.query_service.get_next_sphere_id()

    @handle_exceptions(default_return=False)
    def has_duplicate_category(
        self, section_id: int, category_name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """Check whether a duplicate category exists within the section."""
        return self.query_service.has_duplicate_category(
            section_id, category_name, exclude_id
        )

    def get_current_sphere_id(self) -> Optional[int]:
        """Return the current active sphere ID."""
        return self.current_sphere_id

    def get_section_for_editing(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Fetch section data for editing dialogs."""
        return self.query_service.get_section_for_editing(section_id)

    def get_category_for_editing(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Fetch category data for editing dialogs."""
        return self.query_service.get_category_for_editing(category_id)

    @handle_exceptions()
    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        """Return category hierarchy (sphere_id, section_id)."""
        return self.structure_model.get_category_hierarchy(category_id)

    @handle_exceptions()
    def create_category_for_import(
        self, category_data: Dict[str, Any]
    ) -> Optional[int]:
        """Create a category during import via the CRUD service."""
        return self.crud_service.create_category_for_import(category_data)

    def _validate_section_data(
        self, data: Dict[str, Any], section_id: Optional[int] = None
    ) -> ValidationResult:
        """Validate section data via ``ValidationService``."""
        return self.validation_facade.validate_section_data(data, section_id)

    def _validate_category_data(
        self, data: Dict[str, Any], category_id: Optional[int] = None
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

    def get_statistics(self) -> Dict[str, Any]:
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