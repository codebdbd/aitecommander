# app/controllers/structure_modules/positioning_operations.py

"""Module for element positioning operations."""

import logging
import time
from typing import Optional

from app.config_data.runtime_config import get_slow_update_positions_threshold_sec
from app.services.structure_service import StructureService

from .base import BaseOperations

# Type alias for batch updates: (table_name, list_of_ids)
UpdateSpec = tuple[str, list[int]]

class PositioningOperations(BaseOperations):
    """Class for element positioning operations."""

    def __init__(
        self, structure_model, logger: logging.Logger, execute_with_error_handling
    ):
        super().__init__(structure_model, logger, execute_with_error_handling)
        # Slow update threshold (seconds), read from config with safe fallback
        self._slow_threshold: float = 1.0
        try:
            val = get_slow_update_positions_threshold_sec(1.0)
            if isinstance(val, (int, float)) and val > 0:
                self._slow_threshold = float(val)
        except Exception:
            # Quietly use default value to avoid breaking execution
            pass
        # Use structure service for atomic reordering (UnitOfWork)
        try:
            self._structure_service: Optional[StructureService] = (
                StructureService(structure_model.db)
                if hasattr(structure_model, "db")
                else None
            )
        except Exception:
            # In case of service initialization issues — maintain compatibility
            self._structure_service = None

    def update_item_positions(self, table_name: str, ids_in_order: list[int]) -> bool:
        """Update element positions in the specified table.

        Args:
            table_name (str): Table name for position updates.
                            Cannot be None or empty string.
            ids_in_order (List[int]): List of element IDs in desired order.
                                    Must contain unique positive numbers.

        Returns:
            bool: True on successful position update, False on error.

        Note:
            Method maintains backward compatibility - returns False on any
            validation or execution errors to avoid breaking other modules.

        Example:
            >>> pos_ops = PositioningOperations()
            >>> pos_ops.update_item_positions("users", [3, 1, 5, 2])
            True
        """
        # Initial logging
        self.logger.debug(
            "Starting update_item_positions for table '%s' with %s elements",
            table_name,
            (len(ids_in_order) if ids_in_order else 0),
        )

        # Validate input data with False return for backward compatibility
        validation_error = self._validate_positioning_params(table_name, ids_in_order)
        if validation_error:
            self.logger.warning(
                "Validation error during position update: %s",
                validation_error,
            )
            return False

        def _update_positions_operation():
            start_time = time.time()

            # Additional logging for debugging
            self.logger.debug("ID order for update: %s", ids_in_order)

            # Check record existence (if method is available)
            if hasattr(self.structure_model, "validate_ids_exist"):
                if not self.structure_model.validate_ids_exist(
                    table_name, ids_in_order
                ):
                    self.logger.warning(
                        "Some IDs not found in table %s: %s",
                        table_name,
                        ids_in_order,
                    )
                    # Continue execution for backward compatibility

            # Main update operation through service layer
            if not self._structure_service:
                raise RuntimeError("StructureService unavailable for position updates")
            self._structure_service.update_item_positions(table_name, ids_in_order)

            # Calculate execution time
            duration = time.time() - start_time

            # Detailed result logging
            self.logger.info(
                "Successfully updated positions in table '%s': %s elements in %.3fs",
                table_name,
                len(ids_in_order),
                duration,
            )

            if duration > self._slow_threshold:  # Slow execution warning
                self.logger.warning(
                    "Slow position update in table '%s': %.3fs (threshold %.3fs)",
                    table_name,
                    duration,
                    self._slow_threshold,
                )

            return True

        # Выполнение с обработкой ошибок
        result = self._execute_with_error_handling(
            _update_positions_operation,
            f"обновить позиции в таблице {table_name}",
            default_return=False,
        )

        # Логирование итогового результата
        if result:
            self.logger.debug(
                "update_item_positions completed successfully for table '%s'",
                table_name,
            )
        else:
            self.logger.error(
                "update_item_positions failed for table '%s'",
                table_name,
            )

        return result if result is not None else False

    def _validate_positioning_params(
        self, table_name: str, ids_in_order: list[int]
    ) -> Optional[str]:
        """Validate parameters for positioning operations.

        Args:
            table_name (str): Table name
            ids_in_order (List[int]): List of IDs to check

        Returns:
            Optional[str]: Error message if validation failed, None if all correct
        """
        # Проверка table_name
        if not table_name:
            return "Table name cannot be None"

        if not isinstance(table_name, str):
            return f"Table name must be a string, received: {type(table_name).__name__}"

        if not table_name.strip():
            return "Table name cannot be an empty string"

        # Проверка ids_in_order
        if not ids_in_order:
            return "ID list cannot be empty or None"

        if not isinstance(ids_in_order, list):
            return (
                f"ids_in_order must be a list, received: {type(ids_in_order).__name__}"
            )

        # Проверка типов элементов списка
        for i, id_val in enumerate(ids_in_order):
            if not isinstance(id_val, int):
                return (
                    f"Element {i} must be an integer, received: {type(id_val).__name__}"
                )

            if id_val <= 0:
                return (
                    f"IDs must be positive numbers, received: {id_val} at position {i}"
                )

        # Проверка на дубликаты
        if len(set(ids_in_order)) != len(ids_in_order):
            duplicates = [
                id_val for id_val in set(ids_in_order) if ids_in_order.count(id_val) > 1
            ]
            return f"ID list contains duplicates: {duplicates}"

        # Проверка разумного размера списка
        if len(ids_in_order) > 10000:  # Настраиваемый лимит
            return f"Too many elements for position updates: {len(ids_in_order)} (maximum 10000)"

        return None  # Валидация прошла успешно

    def batch_update_positions(self, updates: list[UpdateSpec]) -> bool:
        """Batch update positions for multiple tables.

        Args:
            updates (List[UpdateSpec]): List of tuples (table_name, ids_in_order)

        Returns:
            bool: True if all updates succeeded, False if there was at least one error
        """
        if not updates:
            self.logger.warning("Empty update list for batch_update_positions")
            return False

        self.logger.info(
            "Starting batch position update for %s tables",
            len(updates),
        )

        success_count = 0
        total_count = len(updates)

        for i, update_data in enumerate(updates):
            if not isinstance(update_data, tuple) or len(update_data) != 2:
                self.logger.error(
                    "Incorrect data format at position %s: expected tuple (table_name, ids)",
                    i,
                )
                continue

            table_name, ids_in_order = update_data

            if self.update_item_positions(table_name, ids_in_order):
                success_count += 1
            else:
                self.logger.error(
                    "Error updating positions for table '%s'",
                    table_name,
                )

        self.logger.info(
            "Batch update completed: %s/%s tables updated successfully",
            success_count,
            total_count,
        )

        return success_count == total_count
