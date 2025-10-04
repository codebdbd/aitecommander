# app/controllers/structure_modules/section_operations.py

"""Модуль для операций с разделами."""

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
    """Информация об удалении раздела."""

    success: bool
    section_data: SectionData
    categories_count: int
    links_count: int

    @classmethod
    def create_empty(cls) -> "DeletionInfo":
        """Создаёт пустой объект для случаев ошибок."""
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
    """Класс для операций с разделами."""

    def __init__(
        self,
        structure_model: StructureModel,
        logger: logging.Logger,
        execute_with_error_handling: Callable,
        execute_with_validation: Callable,
        emit_signal_callback: Callable,
    ):
        """
        Инициализация операций с разделами.

        Args:
            structure_model: Модель для работы со структурой данных
            logger: Логгер для записи событий
            execute_with_error_handling: Функция обработки ошибок
            execute_with_validation: Функция валидации
            emit_signal_callback: Функция эмиссии сигналов
        """
        super().__init__(structure_model, logger, execute_with_error_handling)
        self._execute_with_validation = execute_with_validation
        self._emit_signal = emit_signal_callback
        # Сервисный слой для транзакционных операций и чтений
        try:
            self._structure_service = StructureService(structure_model.db)
        except Exception:
            # Фоллбек на прямую модель (не должен использоваться при нормальной конфигурации)
            self._structure_service = None

    def create_section(self, data: SectionCreateData) -> bool:
        """
        Создает новый раздел.

        Args:
            data: Данные для создания раздела

        Returns:
            bool: True если раздел создан успешно, False иначе
        """
        self._log_operation_start("создание раздела")
        # Делегируем в универсальный метод базового класса
        return self.create_item(StructureItemType.SECTION, data)

    def update_section(self, section_id: int, data: SectionUpdateData) -> bool:
        """
        Обновляет существующий раздел.

        Args:
            section_id: ID раздела для обновления
            data: Новые данные раздела

        Returns:
            bool: True если раздел обновлен успешно, False иначе
        """
        self._log_operation_start(f"обновление раздела {section_id}")
        # Делегируем в универсальный метод базового класса
        return self.update_item(StructureItemType.SECTION, section_id, data)

    def delete_section(self, section_id: int) -> DeletionInfo:
        """Удаляет раздел. Возвращает информацию об удалении.

        Args:
            section_id: ID раздела для удаления

        Returns:
            DeletionInfo: Информация об удалении (успех, данные, количество категорий, количество ссылок)
        """
        self._log_operation_start(f"подготовка удаления раздела {section_id}")

        return self._prepare_section_deletion(section_id)

    def confirm_delete_section(self, section_id: int) -> bool:
        """
        Подтверждает и выполняет удаление раздела.

        Args:
            section_id: ID раздела для удаления

        Returns:
            bool: True если раздел удален успешно, False иначе
        """
        self._log_operation_start(f"подтверждение удаления раздела {section_id}")
        return self._execute_section_deletion(section_id)

    def get_section_data(self, section_id: int) -> Optional[Dict[str, Any]]:
        """
        Получает данные раздела с гарантированной нормализацией.

        Args:
            section_id: ID раздела

        Returns:
            Optional[Dict[str, Any]]: Данные раздела или None если не найден
        """
        self._log_operation_start(f"получение данных раздела {section_id}")
        return self._fetch_section_data(section_id)

    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        """
        Получает список разделов для указанной сферы.

        Args:
            sphere_id: ID сферы

        Returns:
            List[Dict[str, Any]]: Список разделов
        """
        self._log_operation_start(f"получение разделов для сферы {sphere_id}")
        return self._fetch_sections_for_sphere(sphere_id)

    # Приватные методы для улучшения читаемости и тестируемости

    def _prepare_section_deletion(self, section_id: int) -> DeletionInfo:
        """Подготавливает данные для удаления раздела."""

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
            f"получить данные раздела {section_id}",
            default_return=DeletionInfo.create_empty(),
        )

    def _execute_section_deletion(self, section_id: int) -> bool:
        """Выполняет фактическое удаление раздела."""
        if not self._structure_service:
            def _raise_service_error():
                raise RuntimeError("StructureService недоступен для удаления раздела")
            
            return self._execute_with_error_handling(
                _raise_service_error,
                f"удалить раздел {section_id}",
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
        """Получает данные раздела."""

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
            f"загрузить данные раздела {section_id}",
            default_return=None,
        )

    def _fetch_sections_for_sphere(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Получает разделы для сферы."""

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
            f"загрузить разделы для сферы {sphere_id}",
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
        """Переопределяем обработку для разделов: используем StructureService для мутаций.

        Для других типов элементов передаём выполнение базовой реализации.
        """
        # Если это не раздел — используем базовую реализацию
        if item_type is not StructureItemType.SECTION:
            return super()._process_item(
                data, item_type, item_id, is_update, require_parent=require_parent
            )

        # Если сервис недоступен — фоллбек на базовую реализацию (upsert в модели)
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
                    "обновлен",
                    item_type.value,
                    current.get("name", "без имени"),
                    "раздел",
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
                    "создан",
                    item_type.value,
                    current.get("name", "без имени"),
                    "раздел",
                )
                return True

        operation_name = "обновления" if is_update else "создания"
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
        Подсчитывает категории и ссылки в разделе.

        Args:
            section_id: ID раздела

        Returns:
            tuple[int, int]: Количество категорий и ссылок
        """
        return self.structure_model.count_nested_objects_for_section(section_id)

    def _count_nested_objects_for_section(self, section_id: int) -> tuple[int, int]:
        """
        Подсчитывает категории и ссылки в разделе через единый интерфейс модели.

        Этот метод сохранен для полной совместимости с оригинальным кодом.

        Args:
            section_id: ID раздела

        Returns:
            tuple[int, int]: Количество категорий и ссылок
        """
        return self.structure_model.count_nested_objects_for_section(section_id)

    def _emit_section_deleted_signal(self, section_id: int) -> None:
        """Отправляет сигнал об удалении раздела."""
        self._emit_signal("item_deleted", StructureItemType.SECTION.value, section_id)

    # Методы логирования для централизации и улучшения читаемости

    def _log_operation_start(self, operation_name: str) -> None:
        """Логирует начало операции."""
        self.logger.debug("Начало операции: %s", operation_name)

    def _log_section_found(self, section_id: int) -> None:
        """Логирует успешное нахождение раздела."""
        self.logger.debug("Найден раздел %s", section_id)

    def _log_section_not_found(self, section_id: int) -> None:
        """Логирует ненахождение раздела."""
        error_msg = f"Раздел с ID {section_id} не найден"
        self.logger.error(error_msg)

    def _log_deletion_preparation(
        self, section_id: int, cats_count: int, links_count: int
    ) -> None:
        """Логирует подготовку к удалению раздела."""
        self.logger.info(
            "Подготовка к удалению раздела %s: %s категорий, %s ссылок",
            section_id,
            cats_count,
            links_count,
        )

    def _log_successful_deletion(self, section_id: int) -> None:
        """Логирует успешное удаление раздела."""
        self.logger.info("Удален раздел %s", section_id)

    def _log_sections_loaded(self, count: int, sphere_id: int) -> None:
        """Логирует загрузку разделов."""
        self.logger.debug("Загружено %s разделов для сферы %s", count, sphere_id)
