# app/controllers/structure_modules/signal_handlers.py

"""Обработчики сигналов для асинхронных операций структуры.

Наследуется от QObject для правильного использования слотов PyQt6.
"""

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSlot

from .signals import StructureSignals
from ..models.types import (
    SphereData,
    SectionData,
    CategoryData,
    LinkData,
    SearchResultItem,
    AnyItemData,
)

logger = logging.getLogger(__name__)


class AsyncSignalHandlers(QObject):
    """Класс для обработки сигналов от асинхронных операций.

    Наследуется от QObject для правильного использования слотов PyQt6.
    """

    def __init__(self, controller_instance, top_panels_controller: Optional[Any] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.controller = controller_instance
        self.logger = controller_instance.logger
        # ✅ Явная передача зависимости вместо инъекции
        self.top_panels: Optional[Any] = top_panels_controller

    @pyqtSlot(list)
    def on_spheres_loaded(self, spheres: List[SphereData]) -> None:
        """Обработчик завершения загрузки сфер."""
        try:
            self.logger.info("Загружено сфер: %s", len(spheres))
            if hasattr(self.controller, "spheres_loaded"):
                self.controller.spheres_loaded.emit(spheres)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_spheres_loaded: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_spheres_loaded: %s", e)
            raise

    @pyqtSlot(list, int)
    def on_structure_loaded(
        self, structure: List[SectionData], sphere_id: int
    ) -> None:
        """Обработчик завершения загрузки структуры."""
        try:
            self.logger.debug(
                "Загружена структура для сферы %s: %s разделов",
                sphere_id,
                len(structure),
            )
            # Перф-метрика: время от начала переключения сферы до готовности структуры
            try:
                start = getattr(self.controller, "_last_switch_started_ms", None)
                if isinstance(start, (int, float)) and start > 0:
                    import time as _time

                    elapsed_ms = int((_time.monotonic() - float(start)) * 1000)
                    self.logger.info(
                        "[Perf] Переключение сферы %s: структура загружена за %d мс",
                        sphere_id,
                        elapsed_ms,
                    )
                    # Сбрасываем маркер, чтобы не мешал последующим измерениям
                    try:
                        setattr(self.controller, "_last_switch_started_ms", None)
                    except Exception:
                        pass
            except Exception:
                # Никогда не ломаем UI из-за метрик
                pass
            # Опционально отбрасываем устаревшие снапшоты, если включен флаг в конфиге
            try:
                from app.config_data import app_config
                drop_stale = bool(app_config.ui.get_drop_stale_structure_snapshots())
            except Exception:
                drop_stale = False
            if drop_stale:
                try:
                    current = getattr(self.controller, "current_sphere_id", None)
                    if (
                        isinstance(current, int)
                        and current > 0
                        and current != sphere_id
                    ):
                        self.logger.info(
                            "Пропуск structure_loaded: загружена сфера %s, текущая = %s (drop_stale enabled)",
                            sphere_id,
                            current,
                        )
                        return
                except Exception:
                    # Никогда не ломаем UI из-за диагностики
                    pass

            # Кэшируем результат в бизнес-логике, если доступен cache_manager
            try:
                cache = getattr(self.controller, "cache_manager", None)
                if cache and hasattr(cache, "set"):
                    cache.set(f"structure_{int(sphere_id)}", structure or [])
            except Exception:
                # Кэш — вспомогательная оптимизация; ошибки кэширования не критичны
                pass
            if hasattr(self.controller, "structure_loaded"):
                self.controller.structure_loaded.emit(structure)
        except (AttributeError, TypeError) as e:
            # ✅ Ожидаемые ошибки - логируем warning
            self.logger.warning("Expected error in on_structure_loaded: %s", e)
        except Exception as e:
            # ✅ Неожиданные ошибки - полный traceback
            self.logger.exception("Critical error in on_structure_loaded: %s", e)
            raise

    @pyqtSlot(list, int)
    def on_sections_loaded(
        self, sections: List[SectionData], sphere_id: int
    ) -> None:
        """Обработчик завершения загрузки разделов."""
        try:
            self.logger.info(
                "Загружено %s разделов для сферы %s", len(sections), sphere_id
            )
            if hasattr(self.controller, "sections_loaded"):
                self.controller.sections_loaded.emit(sections, sphere_id)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_sections_loaded: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_sections_loaded: %s", e)
            raise

    @pyqtSlot(list, int)
    def on_categories_loaded(
        self, categories: List[CategoryData], section_id: int
    ) -> None:
        """Обработчик завершения загрузки категорий.

        ВАЖНО: ретранслируем корректный сигнал `categories_loaded(categories, section_id)`,
        а не `section_selected`, чтобы UI получил именно событие загрузки категорий.
        """
        try:
            self.logger.info(
                "Загружено %s категорий для раздела %s", len(categories), section_id
            )
            if hasattr(self.controller, "categories_loaded"):
                self.controller.categories_loaded.emit(categories, section_id)
            else:
                # Fallback: если у контроллера нет нового сигнала categories_loaded,
                # ретранслируем уведомление о выборе раздела без передачи категорий
                if hasattr(self.controller, "section_selected"):
                    self.controller.section_selected.emit(section_id)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_categories_loaded: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_categories_loaded: %s", e)
            raise

    # ===== CRUD =====
    @pyqtSlot(str, int, dict)
    def on_item_created(
        self, item_type: str, parent_id: int, item_data: AnyItemData
    ) -> None:
        """Создан элемент структуры."""
        try:
            name = (
                item_data.get("name", "Unknown")
                if isinstance(item_data, dict)
                else "Unknown"
            )
            self.logger.info("Создан %s (parent_id=%s): %s", item_type, parent_id, name)
            # Контроллер (StructureBusinessLogic) использует сигнал item_added
            if hasattr(self.controller, "item_added"):
                self.controller.item_added.emit(item_type, parent_id, item_data)
            # Обновляем кэш и запускаем перезагрузку соответствующих данных
            try:
                if item_type == "category":
                    # Инвалидируем кэш категорий текущего раздела и общую структуру
                    if hasattr(self.controller, "_invalidate_categories_cache"):
                        self.controller._invalidate_categories_cache(parent_id)
                    if hasattr(self.controller, "async_operations"):
                        self.controller.async_operations.load_categories_async(
                            parent_id
                        )
                elif item_type == "section":
                    sphere_id = getattr(self.controller, "current_sphere_id", None)
                    if hasattr(self.controller, "_invalidate_structure_cache"):
                        self.controller._invalidate_structure_cache()
                    if isinstance(sphere_id, int) and sphere_id > 0:
                        # Централизуем перезагрузку структуры в бизнес-логике с дебаунсом
                        if hasattr(self.controller, "_schedule_structure_reload"):
                            self.controller._schedule_structure_reload(delay_ms=150)
            except Exception as e2:
                self.logger.warning(
                    "Не удалось инициировать обновление UI после создания %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_item_created: %s", e, exc_info=True
            )

    @pyqtSlot(str, int, dict)
    def on_item_updated(
        self, item_type: str, item_id: int, item_data: AnyItemData
    ) -> None:
        """Обновлён элемент структуры."""
        try:
            self.logger.info("Обновлён %s id=%s", item_type, item_id)
            if hasattr(self.controller, "item_updated"):
                self.controller.item_updated.emit(item_type, item_id, item_data)
            # Обновляем кэш и запускаем перезагрузку соответствующих данных
            try:
                if item_type == "category":
                    # Инвалидируем кэш категорий текущего раздела и общую структуру
                    if hasattr(self.controller, "_invalidate_categories_cache"):
                        self.controller._invalidate_categories_cache(
                            item_data.get("section_id")
                        )
                    if hasattr(self.controller, "async_operations"):
                        self.controller.async_operations.load_categories_async(
                            item_data.get("section_id")
                        )
                elif item_type == "section":
                    sphere_id = getattr(self.controller, "current_sphere_id", None)
                    if hasattr(self.controller, "_invalidate_structure_cache"):
                        self.controller._invalidate_structure_cache()
                    if isinstance(sphere_id, int) and sphere_id > 0:
                        # Централизуем перезагрузку структуры в бизнес-логике с дебаунсом
                        if hasattr(self.controller, "_schedule_structure_reload"):
                            self.controller._schedule_structure_reload(delay_ms=150)
            except Exception as e2:
                self.logger.warning(
                    "Не удалось инициировать обновление UI после обновления %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_item_updated: %s", e, exc_info=True
            )

    @pyqtSlot(str, int, dict)
    def on_item_deleted(
        self, item_type: str, item_id: int, old_data: AnyItemData
    ) -> None:
        """Удалён элемент структуры.

        Примечание: контроллер ожидает сигнатуру (str, int), поэтому `old_data`
        используется только для логирования и не передается далее.
        """
        try:
            self.logger.info("Удалён %s id=%s", item_type, item_id)
            if hasattr(self.controller, "item_deleted"):
                self.controller.item_deleted.emit(item_type, item_id)
            # Обновление после удаления
            try:
                if item_type == "category":
                    section_id = (
                        (old_data or {}).get("section_id")
                        if isinstance(old_data, dict)
                        else None
                    )
                    if section_id and hasattr(
                        self.controller, "_invalidate_categories_cache"
                    ):
                        self.controller._invalidate_categories_cache(section_id)
                    if section_id and hasattr(self.controller, "async_operations"):
                        self.controller.async_operations.load_categories_async(
                            section_id
                        )
                elif item_type == "section":
                    if hasattr(self.controller, "_invalidate_structure_cache"):
                        self.controller._invalidate_structure_cache()
                    sphere_id = getattr(self.controller, "current_sphere_id", None)
                    if isinstance(sphere_id, int) and sphere_id > 0:
                        # Централизуем перезагрузку структуры в бизнес-логике с дебаунсом
                        if hasattr(self.controller, "_schedule_structure_reload"):
                            self.controller._schedule_structure_reload(delay_ms=150)
            except Exception as e2:
                self.logger.warning(
                    "Не удалось инициировать обновление UI после удаления %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error(
                "Ошибка в обработчике on_item_deleted: %s", e, exc_info=True
            )

    @pyqtSlot(str, str)
    def on_error(self, title: str, message: str) -> None:
        try:
            self.logger.error("%s: %s", title, message)
            # Новый сигнал контроллера
            if hasattr(self.controller, "error_occurred"):
                self.controller.error_occurred.emit(title, message)
            # Совместимость со старым именем
            elif hasattr(self.controller, "error"):
                self.controller.error.emit(title, message)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_error: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_error: %s", e)
            raise

    @pyqtSlot(str)
    def on_simple_error(self, message: str) -> None:
        try:
            self.logger.error(message)
            if hasattr(self.controller, "simple_error"):
                self.controller.simple_error.emit(message)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_simple_error: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_simple_error: %s", e)
            raise

    @pyqtSlot(str)
    def on_operation_started(self, description: str) -> None:
        try:
            # Сообщения о структуре чрезмерно частые — логируем их на DEBUG
            if "структур" in description.lower():
                self.logger.debug(description)
            else:
                self.logger.info(description)
            if hasattr(self.controller, "operation_started"):
                self.controller.operation_started.emit(description)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_operation_started: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_operation_started: %s", e)
            raise

    @pyqtSlot(str)
    def on_operation_finished(self, description: str) -> None:
        try:
            # Сообщения о структуре чрезмерно частые — логируем их на DEBUG
            if "структур" in description.lower():
                self.logger.debug(description)
            else:
                self.logger.info(description)
            if hasattr(self.controller, "operation_finished"):
                self.controller.operation_finished.emit(description)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_operation_finished: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_operation_finished: %s", e)
            raise

    @pyqtSlot()
    def on_loading_started(self) -> None:
        try:
            self.logger.debug("Начата загрузка...")
            if hasattr(self.controller, "loading_started"):
                self.controller.loading_started.emit()
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_loading_started: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_loading_started: %s", e)
            raise

    # ===== Обновление UI =====
    @pyqtSlot(int)
    def on_update_ui(self, category_id: int) -> None:
        try:
            self.logger.debug("Обновление UI для категории %s", category_id)
            if hasattr(self.controller, "update_ui"):
                self.controller.update_ui.emit(category_id)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_update_ui: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_update_ui: %s", e)
            raise

    @pyqtSlot()
    def on_update_favorites(self) -> None:
        try:
            self.logger.debug("Обновление избранного (через TopPanelsController)")
            if not self.top_panels:
                self.logger.warning(
                    "top_panels не инжектирован; пропускаем обновление избранного"
                )
                return
            self.top_panels.request_favorites_refresh()
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_update_favorites: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_update_favorites: %s", e)
            raise

    @pyqtSlot()
    def on_update_recent_links(self) -> None:
        try:
            self.logger.debug("Обновление недавних ссылок (через TopPanelsController)")
            if not self.top_panels:
                self.logger.warning(
                    "top_panels не инжектирован; пропускаем обновление недавних ссылок"
                )
                return
            self.top_panels.request_recents_refresh()
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_update_recent_links: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_update_recent_links: %s", e)
            raise

    # ===== Поиск / Ссылки / Подсчёт =====
    @pyqtSlot(list)
    def on_search_results(self, results: List[SearchResultItem]) -> None:
        try:
            self.logger.info("Результаты поиска: %s", len(results))
            if hasattr(self.controller, "search_results"):
                self.controller.search_results.emit(results)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_search_results: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_search_results: %s", e)
            raise

    @pyqtSlot(list, int, int)
    def on_links_loaded(
        self, links: List[LinkData], category_id: int, task_id: int
    ) -> None:
        try:
            self.logger.info(
                "Загружено ссылок: %s (category_id=%s, task_id=%s)",
                len(links),
                category_id,
                task_id,
            )
            if hasattr(self.controller, "links_loaded"):
                self.controller.links_loaded.emit(links, category_id, task_id)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_links_loaded: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_links_loaded: %s", e)
            raise

    @pyqtSlot(dict)
    def on_link_info_finished(self, info: LinkData) -> None:
        try:
            self.logger.debug("Получена информация о ссылке")
            if hasattr(self.controller, "link_info_finished"):
                self.controller.link_info_finished.emit(info)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_link_info_finished: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_link_info_finished: %s", e)
            raise

    @pyqtSlot(int, list, object)
    def on_count_finished(
        self, fav_count: int, links: List[LinkData], link: object
    ) -> None:
        try:
            self.logger.info("Подсчёт избранных завершён: %s", fav_count)
            if hasattr(self.controller, "count_finished"):
                self.controller.count_finished.emit(fav_count, links, link)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_count_finished: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_count_finished: %s", e)
            raise
