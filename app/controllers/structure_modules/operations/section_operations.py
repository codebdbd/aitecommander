# app/controllers/structure_modules/section_operations.py

"""Module providing operations for sections."""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..models.types import (
    SectionData,
    SectionCreateData,
    SectionUpdateData,
)

from app.models import StructureModel
from app.services.structure_service import StructureService

from .base import BaseOperations, StructureItemType


@dataclass
class DeletionInfo:
    """Information about section deletion."""

    success: bool
    section_data: SectionData
    categories_count: int
    links_count: int

    @classmethod
    def create_empty(cls) -> "DeletionInfo":
        """Creates an empty object for error cases."""
        empty_section: SectionData = {  # type: ignore
            "id": 0,
            "name": "",
            "sphere_id": 0,
            "description": None,
            "position": 0,
            "is_active": False,
            "created_at": None,
            "updated_at": None
        }
        return cls(False, empty_section, 0, 0)


class SectionOperations(BaseOperations):
    """Operations handler for sections."""

    def __init__(
        self,
        structure_model: StructureModel,
        logger: logging.Logger,
        execute_with_error_handling: Callable,
        execute_with_validation: Callable,
        emit_signal_callback: Callable,
    ):
        """
        Initialize section operations.

        Args:
            structure_model: Model for working with structure data
            logger: Logger for recording events
            execute_with_error_handling: Error handling function
            execute_with_validation: Validation function
            emit_signal_callback: Signal emission function
        """
        super().__init__(structure_model, logger, execute_with_error_handling)
        self._execute_with_validation = execute_with_validation
        self._emit_signal = emit_signal_callback
        # Service layer for transactional operations and reads
        try:
            self._structure_service = StructureService(structure_model.db)
        except Exception:
            # Fallback to direct model (should not be used with normal configuration)
            self._structure_service = None

    def create_section(self, data: SectionCreateData) -> bool:
        """
        Create a new section.

        Args:
            data: Data for creating a section

        Returns:
            bool: True if section created successfully, False otherwise
        """
        self._log_operation_start("creating section")
        # Delegate to universal method of base class
        return self.create_item(StructureItemType.SECTION, data)

    def update_section(self, section_id: int, data: SectionUpdateData) -> bool:
        """
        Update an existing section.

        Args:
            section_id: ID of section to update
            data: New section data

        Returns:
            bool: True if section updated successfully, False otherwise
        """
        self._log_operation_start(f"updating section {section_id}")
        # Delegate to universal method of base class
        return self.update_item(StructureItemType.SECTION, section_id, data)

    def delete_section(self, section_id: int) -> DeletionInfo:
        """Delete a section. Returns deletion information.

        Args:
            section_id: ID of section to delete

        Returns:
            DeletionInfo: Deletion information (success, data, category count, link count)
        """
        self._log_operation_start(f"preparing deletion of section {section_id}")

        return self._prepare_section_deletion(section_id)

    def confirm_delete_section(self, section_id: int) -> bool:
        """
        Confirm and execute section deletion.

        Args:
            section_id: ID of section to delete

        Returns:
            bool: True if section deleted successfully, False otherwise
        """
        self._log_operation_start(f"confirming deletion of section {section_id}")
        return self._execute_section_deletion(section_id)

    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """
        Get section data with guaranteed normalization.

        Args:
            section_id: Section ID

        Returns:
            Optional[Dict[str, Any]]: Section data or None if not found
        """
        self._log_operation_start(f"fetching data for section {section_id}")
        return self._fetch_section_data(section_id)

    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """
        Get list of sections for specified sphere.

        Args:
            sphere_id: Sphere ID

        Returns:
            List[Dict[str, Any]]: List of sections
        """
        self._log_operation_start(f"fetching sections for sphere {sphere_id}")
        return self._fetch_sections_for_sphere(sphere_id)

    # Приватные методы для улучшения читаемости и тестируемости

    def _prepare_section_deletion(self, section_id: int) -> DeletionInfo:
        """Prepare data for section deletion."""

        def _deletion_preparation():
            section_data = (
                self._structure_service.get_section_by_id(section_id)
                if self._structure_service
                else self.structure_model.get_section_by_id(section_id)
            )
            if not section_data:
                self._log_section_not_found(section_id)
                return DeletionInfo.create_empty()

            # Получаем нормализованные данные раздела
            normalized_section_data = section_data

            # Подсчитываем вложенные объекты
            if self._structure_service:
                categories_count, links_count = (
                    self._structure_service.count_nested_objects_for_section(section_id)
                )
            else:
                categories_count, links_count = self._count_nested_objects(section_id)

            self._log_deletion_preparation(section_id, categories_count, links_count)

            return DeletionInfo(
                success=True,
                section_data=normalized_section_data,
                categories_count=categories_count,
                links_count=links_count,
            )

        return self._execute_with_error_handling(
            _deletion_preparation,
            f"fetch data for section {section_id}",
            default_return=DeletionInfo.create_empty(),
        )

    def _execute_section_deletion(self, section_id: int) -> bool:
        """Execute actual section deletion."""
        if not self._structure_service:
            def _raise_service_error():
                raise RuntimeError("StructureService unavailable for section deletion")
            
            return self._execute_with_error_handling(
                _raise_service_error,
                f"delete section {section_id}",
                default_return=False,
            )

        def _delete():
            self._structure_service.delete_section(section_id)

        result = self.delete_item(
            StructureItemType.SECTION,
            section_id,
            delete_func=_delete,
            emit_data=None,
        )
        if result:
            self._log_successful_deletion(section_id)
        return result

    def _fetch_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """Fetch section data."""

        def _fetch_operation():
            section_data = (
                self._structure_service.get_section_by_id(section_id)
                if self._structure_service
                else self.structure_model.get_section_by_id(section_id)
            )
            if section_data:
                self._log_section_found(section_id)
                return section_data
            else:
                self._log_section_not_found(section_id)
                return None

        return self._exec_with_norm(
            _fetch_operation,
            f"load data for section {section_id}",
            default_return=None,
        )

    def _fetch_sections_for_sphere(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Fetch sections for sphere."""

        def _fetch_operation():
            sections_data = (
                self._structure_service.get_sections(sphere_id)
                if self._structure_service
                else self.structure_model.get_sections(sphere_id)
            )
            result = sections_data if sections_data else []
            self._log_sections_loaded(len(result), sphere_id)
            return result

        return self._exec_with_norm(
            _fetch_operation,
            f"load sections for sphere {sphere_id}",
            default_return=[],
        )

    def _process_item(
        self,
        data: Dict[str, Any],
        item_type: StructureItemType,
        item_id: Optional[int] = None,
        is_update: bool = False,
        *,
        require_parent: bool = True,
    ) -> bool:
        """Override processing for sections: use StructureService for mutations.

        For other item types, delegate to base implementation.
        """
        # If not a section — use base implementation
        if item_type is not StructureItemType.SECTION:
            return super()._process_item(
                data, item_type, item_id, is_update, require_parent=require_parent
            )

        # If service unavailable — fallback to base implementation (upsert in model)
        if not getattr(self, "_structure_service", None):
            return super()._process_item(
                data, item_type, item_id, is_update, require_parent=require_parent
            )

        def _operation():
            if is_update:
                # Обновление через сервис
                self._structure_service.update_section(int(item_id), data)  # type: ignore[arg-type]
                current = self._structure_service.get_section_by_id(int(item_id)) or {}
                # Эмитим сигнал обновления (parent_or_id = id элемента)
                self._emit_signal(
                    "item_updated", item_type.value, int(item_id), current
                )  # type: ignore[arg-type]
                # Логирование
                self.slogger.log_operation(
                    "updated",
                    item_type.value,
                    current.get("name", "unnamed"),
                    "section",
                )
                return True
            else:
                # Создание через сервис
                new_id = self._structure_service.create_section(data)
                if not new_id:
                    return False
                current = self._structure_service.get_section_by_id(int(new_id)) or {
                    **data,
                    "id": int(new_id),
                }
                parent_id = (
                    (current.get("sphere_id") if isinstance(current, dict) else None)
                    or data.get("sphere_id")
                    or 0
                )
                # Эмитим сигнал добавления (parent_or_id = sphere_id)
                self._emit_signal(
                    "item_added", item_type.value, int(parent_id), current
                )
                # Логирование
                self.slogger.log_operation(
                    "created",
                    item_type.value,
                    current.get("name", "unnamed"),
                    "section",
                )
                return True

        operation_name = "update" if is_update else "create"
        result = self._execute_with_validation(
            _operation,
            data,
            item_type,
            operation_name,
            require_parent=require_parent,
        )
        return result if result is not None else False

    def _count_nested_objects(self, section_id: int) -> tuple[int, int]:
        """
        Count categories and links in section.

        Args:
            section_id: Section ID

        Returns:
            tuple[int, int]: Number of categories and links
        """
        return self.structure_model.count_nested_objects_for_section(section_id)

    def _count_nested_objects_for_section(self, section_id: int) -> tuple[int, int]:
        """
        Count categories and links in section through unified model interface.

        This method is preserved for full compatibility with original code.

        Args:
            section_id: Section ID

        Returns:
            tuple[int, int]: Number of categories and links
        """
        return self.structure_model.count_nested_objects_for_section(section_id)

    def _emit_section_deleted_signal(self, section_id: int) -> None:
        """Emit section deletion signal."""
        self._emit_signal("item_deleted", StructureItemType.SECTION.value, section_id)

    # Методы логирования для централизации и улучшения читаемости

    def _log_operation_start(self, operation_name: str) -> None:
        """Log operation start."""
        self.logger.debug("Starting operation: %s", operation_name)

    def _log_section_found(self, section_id: int) -> None:
        """Log successful section finding."""
        self.logger.debug("Found section %s", section_id)

    def _log_section_not_found(self, section_id: int) -> None:
        """Log section not found."""
        error_msg = f"Section with ID {section_id} not found"
        self.logger.error(error_msg)

    def _log_deletion_preparation(
        self, section_id: int, cats_count: int, links_count: int
    ) -> None:
        """Log section deletion preparation."""
        self.logger.info(
            "Preparing to delete section %s: %s categories, %s links",
            section_id,
            cats_count,
            links_count,
        )

    def _log_successful_deletion(self, section_id: int) -> None:
        """Log successful section deletion."""
        self.logger.info("Deleted section %s", section_id)

    def _log_sections_loaded(self, count: int, sphere_id: int) -> None:
        """Log sections loading."""
        self.logger.debug("Loaded %s sections for sphere %s", count, sphere_id)
