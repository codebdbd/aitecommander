# app/controllers/structure_modules/signal_handlers.py

"""Signal handlers for asynchronous structure operations.

Inherits from QObject for proper use of PyQt6 slots.
"""

import logging
import time
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSlot

from app.config_data.runtime_config import is_drop_stale_structure_snapshots
from app.utils.metrics import get_metrics

from ..models.types import (
    AnyItemData,
    CategoryData,
    LinkData,
    SearchResultItem,
    SectionData,
    SphereData,
)

logger = logging.getLogger(__name__)


class AsyncSignalHandlers(QObject):
    """Class for handling signals from asynchronous operations.

    Inherits from QObject for proper use of PyQt6 slots.
    """

    def __init__(
        self,
        controller_instance,
        top_panels_controller: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.controller = controller_instance
        self.logger = controller_instance.logger
        # ✅ Explicit dependency passing instead of injection
        self.top_panels: Optional[Any] = top_panels_controller

    @pyqtSlot(list)
    def on_spheres_loaded(self, spheres: list[SphereData]) -> None:
        """Handler for sphere loading completion."""
        try:
            self.logger.info("Loaded spheres: %s", len(spheres))
            if hasattr(self.controller, "spheres_loaded"):
                self.controller.spheres_loaded.emit(spheres)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_spheres_loaded: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_spheres_loaded: %s", e)
            raise

    @pyqtSlot(list, int)
    def on_structure_loaded(self, structure: list[SectionData], sphere_id: int) -> None:
        """Handler for structure loading completion."""
        t0 = time.perf_counter()
        try:
            self.logger.debug(
                "Loaded structure for sphere %s: %s sections",
                sphere_id,
                len(structure),
            )
            t1 = time.perf_counter()
            self._log_switch_metrics(sphere_id)
            t2 = time.perf_counter()
            if self._should_skip_structure_update(sphere_id):
                self.logger.info(
                    "[Perf] AsyncSignalHandlers.on_structure_loaded sphere=%s skipped=True log_switch=%.2f ms total=%.2f ms",
                    sphere_id,
                    (t2 - t1) * 1000.0,
                    (time.perf_counter() - t0) * 1000.0,
                )
                return
            t3 = time.perf_counter()
            self._cache_structure_snapshot(sphere_id, structure)
            t4 = time.perf_counter()
            self._emit_structure_loaded(structure)
            t5 = time.perf_counter()
            self.logger.info(
                "[Perf] AsyncSignalHandlers.on_structure_loaded sphere=%s sections=%s should_skip=%.2f ms log_switch=%.2f ms cache_snapshot=%.2f ms emit_structure_loaded=%.2f ms total=%.2f ms",
                sphere_id,
                len(structure),
                (t3 - t2) * 1000.0,
                (t2 - t1) * 1000.0,
                (t4 - t3) * 1000.0,
                (t5 - t4) * 1000.0,
                (t5 - t0) * 1000.0,
            )
        except (AttributeError, TypeError) as e:
            # ✅ Expected errors - log as warning
            self.logger.warning("Expected error in on_structure_loaded: %s", e)
        except Exception as e:
            # ✅ Unexpected errors - full traceback
            self.logger.exception("Critical error in on_structure_loaded: %s", e)
            raise

    def _log_switch_metrics(self, sphere_id: int) -> None:
        """Log elapsed time for sphere switch if metrics are available."""

        try:
            start = getattr(self.controller, "_last_switch_started_ms", None)
            if not (isinstance(start, (int, float)) and start > 0):
                return

            import time as _time

            elapsed_ms = int((_time.monotonic() - float(start)) * 1000)
            self.logger.info(
                "[Perf] Sphere switch %s: structure loaded in %d ms",
                sphere_id,
                elapsed_ms,
            )
            try:
                self.controller._last_switch_started_ms = None
            except Exception:
                pass
        except Exception:
            # Metrics are auxiliary; never break the UI if they fail.
            pass

    def _should_skip_structure_update(self, sphere_id: int) -> bool:
        """Return True when stale structure updates should be dropped."""

        try:
            drop_stale = is_drop_stale_structure_snapshots(False)
        except Exception:
            drop_stale = False

        if not drop_stale:
            return False

        try:
            current = getattr(self.controller, "current_sphere_id", None)
            if (
                isinstance(current, int)
                and current > 0
                and current != sphere_id
            ):
                self.logger.info(
                    "Skipping structure_loaded: sphere %s loaded, current = %s (drop_stale enabled)",
                    sphere_id,
                    current,
                )
                return True
        except Exception:
            pass

        return False

    def _cache_structure_snapshot(
        self, sphere_id: int, structure: list[SectionData]
    ) -> None:
        """Store structure snapshot in cache when available."""

        try:
            cache = getattr(self.controller, "cache_manager", None)
            if cache and hasattr(cache, "set"):
                cache.set(f"structure_{int(sphere_id)}", structure or [])
        except Exception:
            # Cache is an optimization; errors should not surface to the UI.
            pass

    def _emit_structure_loaded(self, structure: list[SectionData]) -> None:
        """Forward the structure_loaded signal when the controller supports it."""

        if hasattr(self.controller, "structure_loaded"):
            self.controller.structure_loaded.emit(structure)

    @pyqtSlot(list, int)
    def on_sections_loaded(self, sections: list[SectionData], sphere_id: int) -> None:
        """Handler for section loading completion."""
        try:
            self.logger.info(
                "Loaded %s sections for sphere %s", len(sections), sphere_id
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
        self, categories: list[CategoryData], section_id: int
    ) -> None:
        """Handler for category loading completion.

        IMPORTANT: re-emit correct signal `categories_loaded(categories, section_id)`
        when available. Legacy fallback emits `section_selected` only for the
        currently selected section to avoid tiles flicker.
        """
        try:
            import time as _time

            try:
                async_service = getattr(self.controller, "async_service", None)
                if async_service and hasattr(async_service, "should_drop_categories_emit"):
                    if bool(async_service.should_drop_categories_emit(section_id)):
                        self.logger.debug(
                            "Skipping stale categories_loaded for section %s (newer reload pending)",
                            section_id,
                        )
                        return
            except Exception:
                pass

            started_ts = None
            try:
                async_service = getattr(self.controller, "async_service", None)
                if async_service and hasattr(async_service, "pop_category_load_started_ts"):
                    started_ts = async_service.pop_category_load_started_ts(section_id)
            except Exception:
                started_ts = None
            self.logger.info(
                "Loaded %s categories for section %s", len(categories), section_id
            )
            if isinstance(started_ts, (int, float)) and started_ts > 0:
                elapsed_ms = (_time.perf_counter() - float(started_ts)) * 1000
                metrics = get_metrics()
                metrics.record_timing("categories.async_to_signal_ms", elapsed_ms)
                stats = metrics.get_stats("categories.async_to_signal_ms")
                self.logger.info(
                    "[Perf] Categories async->signal section=%s: %.2f ms (count=%s)",
                    section_id,
                    elapsed_ms,
                    len(categories),
                )
                if stats.get("count", 0) % 20 == 0 and stats.get("count", 0) > 0:
                    self.logger.info(
                        "[PerfAgg] categories.async_to_signal_ms: n=%s p50=%.2f ms p95=%.2f ms avg=%.2f ms",
                        stats.get("count", 0),
                        float(stats.get("p50", 0.0)),
                        float(stats.get("p95", 0.0)),
                        float(stats.get("avg", 0.0)),
                    )
            if hasattr(self.controller, "categories_loaded"):
                self.controller.categories_loaded.emit(categories, section_id)
            else:
                # Fallback: only re-emit for current selection to avoid UI jumps
                last_selected = getattr(
                    self.controller, "_last_selected_section_id", None
                )
                if (
                    hasattr(self.controller, "section_selected")
                    and isinstance(last_selected, int)
                    and last_selected == int(section_id)
                ):
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
        """Structure item created."""
        try:
            name = (
                item_data.get("name", "Unknown")
                if isinstance(item_data, dict)
                else "Unknown"
            )
            self.logger.info(
                "Created %s (parent_id=%s): %s", item_type, parent_id, name
            )
            # Controller (StructureBusinessLogic) uses item_added signal
            if hasattr(self.controller, "item_added"):
                self.controller.item_added.emit(item_type, parent_id, item_data)
            # Обновляем кэш и запускаем перезагрузку соответствующих данных
            try:
                if item_type == "category":
                    # Инвалидируем кэш категорий текущего раздела и общую структуру
                    if hasattr(self.controller, "_invalidate_categories_cache"):
                        self.controller._invalidate_categories_cache(parent_id)
                elif item_type == "section":
                    sphere_id = getattr(self.controller, "current_sphere_id", None)
                    if hasattr(self.controller, "_invalidate_structure_cache"):
                        self.controller._invalidate_structure_cache()
                    # Incremental UI update already handled; avoid full reload to
                    # prevent selection jumps after edits.
                    return
            except Exception as e2:
                self.logger.warning(
                    "Failed to initiate UI update after creating %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error("Error in on_item_created handler: %s", e, exc_info=True)

    @pyqtSlot(str, int, dict)
    def on_item_updated(
        self, item_type: str, item_id: int, item_data: AnyItemData
    ) -> None:
        """Structure item updated."""
        try:
            self.logger.info("Updated %s id=%s", item_type, item_id)
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
                    "Failed to initiate UI update after updating %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error("Error in on_item_updated handler: %s", e, exc_info=True)

    @pyqtSlot(str, int, dict)
    def on_item_deleted(
        self, item_type: str, item_id: int, old_data: AnyItemData
    ) -> None:
        """Structure item deleted.

        Note: controller expects signature (str, int), so `old_data`
        is used only for logging and not passed further.
        """
        try:
            self.logger.info("Deleted %s id=%s", item_type, item_id)
            if hasattr(self.controller, "item_deleted"):
                self.controller.item_deleted.emit(item_type, item_id)
            # Update after deletion
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
                    "Failed to initiate UI update after deleting %s: %s",
                    item_type,
                    e2,
                )
        except Exception as e:
            self.logger.error("Error in on_item_deleted handler: %s", e, exc_info=True)

    @pyqtSlot(str, str)
    def on_error(self, title: str, message: str) -> None:
        try:
            self.logger.error("%s: %s", title, message)
            # New controller signal
            if hasattr(self.controller, "error_occurred"):
                self.controller.error_occurred.emit(title, message)
            # Backward compatibility with old name
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
            self.logger.debug("Loading started...")
            if hasattr(self.controller, "loading_started"):
                self.controller.loading_started.emit()
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_loading_started: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_loading_started: %s", e)
            raise

    # ===== UI Update =====
    @pyqtSlot(int)
    def on_update_ui(self, category_id: int) -> None:
        try:
            self.logger.debug("Updating UI for category %s", category_id)
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
            self.logger.debug("Updating favorites (via TopPanelsController)")
            if not self.top_panels:
                self.logger.warning(
                    "top_panels not injected; skipping favorites update"
                )
                return
            if hasattr(self.top_panels, "request_refresh"):
                if getattr(self.top_panels, "_pending_refresh", False):
                    return
                self.top_panels.request_refresh()
            else:
                if getattr(self.top_panels, "_pending_fav_refresh", False):
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
            self.logger.debug("Updating recent links (via TopPanelsController)")
            if not self.top_panels:
                self.logger.warning(
                    "top_panels not injected; skipping recent links update"
                )
                return
            if hasattr(self.top_panels, "request_refresh"):
                if getattr(self.top_panels, "_pending_refresh", False):
                    return
                self.top_panels.request_refresh()
            else:
                if getattr(self.top_panels, "_pending_recent_refresh", False):
                    return
                self.top_panels.request_recents_refresh()
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_update_recent_links: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_update_recent_links: %s", e)
            raise

    # ===== Search / Links / Count =====
    @pyqtSlot(list)
    def on_search_results(self, results: list[SearchResultItem]) -> None:
        try:
            self.logger.info("Search results: %s", len(results))
            if hasattr(self.controller, "search_results"):
                self.controller.search_results.emit(results)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_search_results: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_search_results: %s", e)
            raise

    @pyqtSlot(list, int, int)
    def on_links_loaded(
        self, links: list[LinkData], category_id: int, task_id: int
    ) -> None:
        try:
            self.logger.info(
                "Loaded links: %s (category_id=%s, task_id=%s)",
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
            self.logger.debug("Received link information")
            if hasattr(self.controller, "link_info_finished"):
                self.controller.link_info_finished.emit(info)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_link_info_finished: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_link_info_finished: %s", e)
            raise

    @pyqtSlot(int, list, object)
    def on_count_finished(
        self, fav_count: int, links: list[LinkData], link: object
    ) -> None:
        try:
            self.logger.info("Favorite count completed: %s", fav_count)
            if hasattr(self.controller, "count_finished"):
                self.controller.count_finished.emit(fav_count, links, link)
        except (AttributeError, TypeError) as e:
            self.logger.warning("Expected error in on_count_finished: %s", e)
        except Exception as e:
            self.logger.exception("Critical error in on_count_finished: %s", e)
            raise
