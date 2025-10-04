# app/controllers/structure_modules/positioning_operations.py

"""Модуль для операций с позиционированием элементов."""

import logging
import time
from typing import List, Optional, Tuple

from app.services.structure_service import StructureService

from .base import BaseOperations

# Тип-алиас для батч-обновлений: (имя_таблицы, список_ID)
UpdateSpec = Tuple[str, List[int]]

# Ленивый доступ к конфигурации приложения (без прямой зависимости от config_loader)
try:
    from app.config_data import app_config  # type: ignore
except Exception:  # pragma: no cover - на случай проблем с импортом
    app_config = None  # type: ignore


class PositioningOperations(BaseOperations):
    """Класс для операций с позиционированием элементов."""

    def __init__(
        self, structure_model, logger: logging.Logger, execute_with_error_handling
    ):
        super().__init__(structure_model, logger, execute_with_error_handling)
        # Порог медленного обновления (секунды), читаем из конфига с безопасным фолбэком
        self._slow_threshold: float = 1.0
        try:
            if app_config is not None:
                val = app_config.get("limits.slow_update_positions_threshold_sec", None)
                if isinstance(val, (int, float)) and val > 0:
                    self._slow_threshold = float(val)
        except Exception:
            # Тихо используем значение по умолчанию, чтобы не ломать выполнение
            pass
        # Используем сервис структуры для атомарных перестановок (UnitOfWork)
        try:
            self._structure_service: Optional[StructureService] = (
                StructureService(structure_model.db)
                if hasattr(structure_model, "db")
                else None
            )
        except Exception:
            # На случай проблем инициализации сервиса — сохраняем совместимость
            self._structure_service = None

    def update_item_positions(self, table_name: str, ids_in_order: List[int]) -> bool:
        """Обновляет позиции элементов в указанной таблице.

        Args:
            table_name (str): Название таблицы для обновления позиций.
                            Не может быть None или пустой строкой.
            ids_in_order (List[int]): Список ID элементов в желаемом порядке.
                                    Должен содержать уникальные положительные числа.

        Returns:
            bool: True при успешном обновлении позиций, False при ошибке.

        Note:
            Метод сохраняет обратную совместимость - возвращает False при любых
            ошибках валидации или выполнения, чтобы не нарушить работу других модулей.

        Example:
            >>> pos_ops = PositioningOperations()
            >>> pos_ops.update_item_positions("users", [3, 1, 5, 2])
            True
        """
        # Начальное логирование
        self.logger.debug(
            "Запуск update_item_positions для таблицы '%s' с %s элементами",
            table_name,
            (len(ids_in_order) if ids_in_order else 0),
        )

        # Валидация входных данных с возвратом False для обратной совместимости
        validation_error = self._validate_positioning_params(table_name, ids_in_order)
        if validation_error:
            self.logger.warning(
                "Ошибка валидации при обновлении позиций: %s",
                validation_error,
            )
            return False

        def _update_positions_operation():
            start_time = time.time()

            # Дополнительное логирование для отладки
            self.logger.debug("Порядок ID для обновления: %s", ids_in_order)

            # Проверка существования записей (если метод доступен)
            if hasattr(self.structure_model, "validate_ids_exist"):
                if not self.structure_model.validate_ids_exist(
                    table_name, ids_in_order
                ):
                    self.logger.warning(
                        "Некоторые ID не найдены в таблице %s: %s",
                        table_name,
                        ids_in_order,
                    )
                    # Продолжаем выполнение для обратной совместимости

            # Основная операция обновления через сервисный слой
            if not self._structure_service:
                raise RuntimeError("StructureService недоступен для обновления позиций")
            self._structure_service.update_item_positions(table_name, ids_in_order)

            # Расчет времени выполнения
            duration = time.time() - start_time

            # Детальное логирование результата
            self.logger.info(
                "Успешно обновлены позиции в таблице '%s': %s элементов за %.3fс",
                table_name,
                len(ids_in_order),
                duration,
            )

            if duration > self._slow_threshold:  # Предупреждение о медленном выполнении
                self.logger.warning(
                    "Медленное обновление позиций в таблице '%s': %.3fс (порог %.3fс)",
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
                "update_item_positions завершен успешно для таблицы '%s'",
                table_name,
            )
        else:
            self.logger.error(
                "update_item_positions завершился с ошибкой для таблицы '%s'",
                table_name,
            )

        return result if result is not None else False

    def _validate_positioning_params(
        self, table_name: str, ids_in_order: List[int]
    ) -> Optional[str]:
        """Валидирует параметры для операций с позиционированием.

        Args:
            table_name (str): Название таблицы
            ids_in_order (List[int]): Список ID для проверки

        Returns:
            Optional[str]: Сообщение об ошибке если валидация не прошла, None если все корректно
        """
        # Проверка table_name
        if not table_name:
            return "Название таблицы не может быть None"

        if not isinstance(table_name, str):
            return f"Название таблицы должно быть строкой, получено: {type(table_name).__name__}"

        if not table_name.strip():
            return "Название таблицы не может быть пустой строкой"

        # Проверка ids_in_order
        if not ids_in_order:
            return "Список ID не может быть пустым или None"

        if not isinstance(ids_in_order, list):
            return f"ids_in_order должен быть списком, получено: {type(ids_in_order).__name__}"

        # Проверка типов элементов списка
        for i, id_val in enumerate(ids_in_order):
            if not isinstance(id_val, int):
                return f"Элемент {i} должен быть целым числом, получено: {type(id_val).__name__}"

            if id_val <= 0:
                return f"ID должны быть положительными числами, получено: {id_val} в позиции {i}"

        # Проверка на дубликаты
        if len(set(ids_in_order)) != len(ids_in_order):
            duplicates = [
                id_val for id_val in set(ids_in_order) if ids_in_order.count(id_val) > 1
            ]
            return f"Список ID содержит дубликаты: {duplicates}"

        # Проверка разумного размера списка
        if len(ids_in_order) > 10000:  # Настраиваемый лимит
            return f"Слишком много элементов для обновления позиций: {len(ids_in_order)} (максимум 10000)"

        return None  # Валидация прошла успешно

    def batch_update_positions(self, updates: List[UpdateSpec]) -> bool:
        """Пакетное обновление позиций для нескольких таблиц.

        Args:
            updates (List[UpdateSpec]): Список кортежей (table_name, ids_in_order)

        Returns:
            bool: True если все обновления прошли успешно, False если была хотя бы одна ошибка
        """
        if not updates:
            self.logger.warning("Пустой список обновлений для batch_update_positions")
            return False

        self.logger.info(
            "Начинается пакетное обновление позиций для %s таблиц",
            len(updates),
        )

        success_count = 0
        total_count = len(updates)

        for i, update_data in enumerate(updates):
            if not isinstance(update_data, tuple) or len(update_data) != 2:
                self.logger.error(
                    "Некорректный формат данных в позиции %s: ожидается кортеж (table_name, ids)",
                    i,
                )
                continue

            table_name, ids_in_order = update_data

            if self.update_item_positions(table_name, ids_in_order):
                success_count += 1
            else:
                self.logger.error(
                    "Ошибка при обновлении позиций для таблицы '%s'",
                    table_name,
                )

        self.logger.info(
            "Пакетное обновление завершено: %s/%s таблиц обновлено успешно",
            success_count,
            total_count,
        )

        return success_count == total_count
