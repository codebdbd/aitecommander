"""Event handling helpers for structure business logic."""

from __future__ import annotations

from logging import Logger
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.controllers.business.structure_business import StructureBusinessLogic
    from .async_service import StructureAsyncService
    from .cache_service import StructureCacheService


class StructureEventService:
    """Encapsulates item event handlers and batch-mode tracking."""

    def __init__(
        self,
        owner: StructureBusinessLogic,
        cache_service: StructureCacheService,
        async_service: StructureAsyncService,
        logger: Logger,
    ) -> None:
        self._owner = owner
        self._cache_service = cache_service
        self._async_service = async_service
        self._logger = logger
        self._batch_mode = False
        self._batch_touched_sections: set[int] = set()

    # ------------------------------------------------------------------
    # Batch mode management
    # ------------------------------------------------------------------
    def begin_batch(self) -> None:
        """Начинает batch режим для группировки операций.
        
        В batch режиме обновления кэша откладываются до вызова end_batch().
        Это оптимизирует производительность при массовых операциях.
        """
        self._batch_mode = True
        self._batch_touched_sections.clear()

    def end_batch(self) -> None:
        """Завершает batch режим и применяет отложенные обновления.
        
        Перезагружает категории для всех затронутых разделов и
        инвалидирует кэш структуры.
        """
        touched = set(self._batch_touched_sections)
        self._batch_touched_sections.clear()
        self._batch_mode = False

        for section_id in touched:
            if not isinstance(section_id, int) or section_id <= 0:
                continue
            try:
                self._async_service.load_categories_async(int(section_id))
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.debug(
                    "end_batch: failed to schedule load_categories_async for %s: %s",
                    section_id,
                    exc,
                    exc_info=True,
                )

        try:
            self._cache_service.invalidate_structure_cache()
            from app.config_data import app_config

            delay = int(app_config.ui.get_structure_reload_immediate_delay_ms())
            self._async_service.schedule_structure_reload(delay)
        except Exception as exc:
            self._logger.debug(
                "end_batch: failed to schedule structure reload: %s",
                exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_item_added(self, item_type: str, parent_id: int, item_data: dict[str, Any]) -> None:
        """Обработчик события добавления элемента.
        
        ✅ ИСПРАВЛЕНИЕ: Улучшена обработка ошибок и добавлена проверка на None.
        """
        try:
            self._logger.info(
                "[BL] item_added: type=%s, parent_id=%s", item_type, parent_id
            )
            if item_type == "link":
                category_id = (
                    item_data.get("category_id")
                    if isinstance(item_data, dict)
                    else None
                )
                # ✅ Проверка на None перед использованием
                if category_id is not None:
                    self._cache_service.invalidate_categories_cache(category_id)
                self._async_service.schedule_structure_reload(None)
                return

            if item_type == "category":
                section_id = parent_id or (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                self._cache_service.invalidate_categories_cache(section_id)
                if isinstance(section_id, int) and section_id > 0:
                    self._async_service.load_categories_async(section_id)

            self._cache_service.invalidate_structure_cache()
            from app.config_data import app_config

            delay = int(app_config.ui.get_structure_reload_immediate_delay_ms())
            self._async_service.schedule_structure_reload(delay)
        except (ValueError, KeyError, TypeError) as exc:
            # ✅ Ожидаемые ошибки валидации данных
            self._logger.error("Validation error in on_item_added handler: %s", exc, exc_info=True)
        except AttributeError as exc:
            # ✅ Неожиданные ошибки - отсутствие атрибутов
            self._logger.exception("Critical error in on_item_added handler: %s", exc)
            raise
        except Exception as exc:
            # ✅ Все остальные критические ошибки
            self._logger.exception("Unexpected error in on_item_added handler: %s", exc)
            raise

    def on_item_updated(self, item_type: str, item_id: int, item_data: dict[str, Any]) -> None:
        """Обработчик события обновления элемента.
        
        ✅ ИСПРАВЛЕНИЕ: Улучшена обработка ошибок и добавлена проверка на None.
        """
        try:
            self._logger.info("[BL] item_updated: type=%s, id=%s", item_type, item_id)
            if item_type == "link":
                category_id = (
                    item_data.get("category_id")
                    if isinstance(item_data, dict)
                    else None
                )
                # ✅ Проверка на None перед использованием
                if category_id is not None:
                    self._cache_service.invalidate_categories_cache(category_id)
                return

            if item_type == "category":
                section_id = (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                self._cache_service.invalidate_categories_cache(section_id)
                if self._batch_mode:
                    self.add_batch_section(section_id)
                    return
                if isinstance(section_id, int) and section_id > 0:
                    self._async_service.load_categories_async(section_id)

            self._cache_service.invalidate_structure_cache()
            self._async_service.schedule_structure_reload(0)
        except (ValueError, KeyError, TypeError) as exc:
            # ✅ Ожидаемые ошибки валидации данных
            self._logger.error("Validation error in on_item_updated handler: %s", exc, exc_info=True)
        except AttributeError as exc:
            # ✅ Неожиданные ошибки - отсутствие атрибутов
            self._logger.exception("Critical error in on_item_updated handler: %s", exc)
            raise
        except Exception as exc:
            # ✅ Все остальные критические ошибки
            self._logger.exception("Unexpected error in on_item_updated handler: %s", exc)
            raise

    def on_item_deleted(self, item_type: str, item_id: int) -> None:
        """Обработчик события удаления элемента.
        
        ✅ ИСПРАВЛЕНИЕ: Улучшена обработка ошибок.
        """
        try:
            if item_type == "link":
                self._async_service.schedule_structure_reload(None)
                return
            self._cache_service.invalidate_structure_cache()
            self._async_service.schedule_structure_reload(0)
        except (ValueError, KeyError, TypeError) as exc:
            # ✅ Ожидаемые ошибки валидации данных
            self._logger.error(
                "Validation error in on_item_deleted handler: %s",
                exc,
                exc_info=True,
            )
        except AttributeError as exc:
            # ✅ Неожиданные ошибки - отсутствие атрибутов
            self._logger.exception(
                "Critical error in on_item_deleted handler: %s",
                exc,
            )
            raise
        except Exception as exc:
            # ✅ Все остальные критические ошибки
            self._logger.exception(
                "Unexpected error in on_item_deleted handler: %s",
                exc,
            )
            raise

    def on_items_batch_deleted(self, item_type: str, ids: list[Any]) -> None:
        try:
            total = len(ids) if isinstance(ids, (list, tuple)) else 0
            self._logger.info(
                "[BL] items_batch_deleted: type=%s, count=%s", item_type, total
            )
            if item_type == "link":
                self._async_service.schedule_structure_reload(None)
                return
            self._cache_service.invalidate_structure_cache()
            self._async_service.schedule_structure_reload(0)
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.error(
                "Error in on_items_batch_deleted handler: %s",
                exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Helpers accessed by owner
    # ------------------------------------------------------------------
    @property
    def batch_mode(self) -> bool:
        return self._batch_mode

    def add_batch_section(self, section_id: Optional[int]) -> None:
        if not self._batch_mode:
            return
        if isinstance(section_id, int) and section_id > 0:
            self._batch_touched_sections.add(int(section_id))

    @property
    def touched_sections(self) -> set[int]:
        return set(self._batch_touched_sections)

    def replace_touched_sections(self, sections: set[int]) -> None:
        self._batch_touched_sections = set(sections)
