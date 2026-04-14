"""Event handling helpers for structure business logic."""

from __future__ import annotations

from logging import Logger
import os
import time
from typing import TYPE_CHECKING, Any

from app.config_data.runtime_config import get_structure_reload_immediate_delay_ms

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.controllers.business.structure_business import StructureBusinessLogic

    from .async_service import StructureAsyncService
    from .cache_service import StructureCacheService


class StructureEventService:
    """Encapsulates item event handlers and batch-mode tracking."""

    _TOP_PANELS_MIN_INTERVAL_S = 0.25

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        raw = os.getenv(name, str(default))
        try:
            return int(str(raw).strip() or str(default))
        except Exception:
            return int(default)

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        raw = os.getenv(name, str(default))
        try:
            return float(str(raw).strip() or str(default))
        except Exception:
            return float(default)

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
        self._batch_touched_spheres: set[int] = set()
        self._last_top_panels_refresh_ts = 0.0

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
        self._batch_touched_spheres.clear()

    def _schedule_top_panels_refresh(self) -> None:
        """Best-effort refresh for top panels after structure changes."""
        try:
            import time

            if (time.perf_counter() - self._last_top_panels_refresh_ts) < self._TOP_PANELS_MIN_INTERVAL_S:
                return
            controller = getattr(self._owner, "top_panels_controller", None)
            if controller is None:
                return
            if hasattr(controller, "schedule_structure_refresh"):
                controller.schedule_structure_refresh()
                self._last_top_panels_refresh_ts = time.perf_counter()
                return
            if hasattr(controller, "request_refresh"):
                controller.request_refresh()
                self._last_top_panels_refresh_ts = time.perf_counter()
        except Exception:
            self._logger.debug(
                "StructureEventService: top panels refresh failed",
                exc_info=True,
            )

    def _try_optimistic_category_refresh(
        self,
        section_id: int | None,
        item_data: dict[str, Any] | None,
        *,
        allow_insert: bool,
    ) -> bool:
        try:
            sid = int(section_id)
        except Exception:
            return False
        if sid <= 0 or not isinstance(item_data, dict):
            return False
        cache_manager = getattr(self._owner, "cache_manager", None)
        if cache_manager is None or not hasattr(cache_manager, "get"):
            return False
        try:
            cached = cache_manager.get(f"categories_{sid}")
        except Exception:
            cached = None
        if not isinstance(cached, list):
            return False

        category_id = item_data.get("id")
        prepared: list[dict[str, Any]] = []
        found = False
        for entry in cached:
            if not isinstance(entry, dict):
                continue
            cloned = dict(entry)
            if isinstance(category_id, int) and int(cloned.get("id", -1)) == category_id:
                cloned.update(item_data)
                found = True
            prepared.append(cloned)

        if not found:
            if not allow_insert:
                return False
            prepared.append(dict(item_data))

        try:
            prepared.sort(
                key=lambda item: (
                    int(item.get("position"))
                    if isinstance(item.get("position"), int)
                    else 0,
                    str(item.get("name", "")).lower(),
                )
            )
        except Exception:
            pass

        prime_cache = getattr(self._owner, "prime_categories_cache", None)
        if not callable(prime_cache):
            return False
        try:
            prime_cache(sid, prepared, ttl_s=1.5)
        except Exception:
            self._logger.debug(
                "StructureEventService: optimistic category cache prime failed for section %s",
                sid,
                exc_info=True,
            )
            return False

        try:
            selected_section = getattr(self._owner, "_last_selected_section_id", None)
            if isinstance(selected_section, int) and selected_section == sid:
                self._owner.section_selected.emit(sid)
        except Exception:
            self._logger.debug(
                "StructureEventService: optimistic category section_selected emit failed for %s",
                sid,
                exc_info=True,
            )
        return True

    def end_batch(self) -> None:
        """Завершает batch режим и применяет отложенные обновления.

        Перезагружает категории для всех затронутых разделов и
        инвалидирует кэш структуры.
        """
        touched = set(self._batch_touched_sections)
        touched_spheres = set(self._batch_touched_spheres)
        self._logger.info(
            "[BL] end_batch: touched_sections=%s, touched_spheres=%s",
            sorted(touched),
            sorted(touched_spheres),
        )
        self._batch_touched_sections.clear()
        self._batch_touched_spheres.clear()
        self._batch_mode = False
        try:
            marker = getattr(self._owner, "mark_interactive_structure_activity", None)
            if callable(marker) and (touched or touched_spheres):
                marker(reason="batch-end")
        except Exception:
            self._logger.debug("end_batch: interactive cooldown mark failed", exc_info=True)

        max_section_loads = self._env_int("AITE_MAX_BATCH_SECTION_LOADS", 5)
        recent_sync_guard_s = self._env_float("AITE_RECENT_SYNC_GUARD_S", 0.40)
        do_section_loads = max_section_loads > 0 and len(touched) <= max_section_loads
        force_fresh_window_s = self._env_float("AITE_FORCE_FRESH_TILES_WINDOW_S", 1.00)
        selected_section = getattr(self._owner, "_last_selected_section_id", None)
        preferred_section = getattr(self._owner, "_batch_preferred_section_id", None)
        try:
            setattr(self._owner, "_batch_preferred_section_id", None)
        except Exception:
            pass
        load_selected_only = str(
            os.getenv("AITE_BATCH_LOAD_SELECTED_ONLY", "1")
        ).lower() in {"1", "true", "yes", "on"}

        sections_to_load = set(touched)
        preserved_sections: set[int] = set()
        preserve_cache = getattr(
            self._owner, "should_preserve_optimistic_categories_cache", None
        )
        if (
            do_section_loads
            and load_selected_only
            and len(sections_to_load) > 1
        ):
            candidate: int | None = None
            source = "selected"
            if isinstance(preferred_section, int) and preferred_section in sections_to_load:
                candidate = int(preferred_section)
                source = "preferred"
            elif isinstance(selected_section, int) and selected_section in sections_to_load:
                candidate = int(selected_section)
            if isinstance(candidate, int):
                sections_to_load = {candidate}
                self._logger.info(
                    "[BL] end_batch: loading %s section only=%s, skipped=%s",
                    source,
                    candidate,
                    len(touched) - 1,
                )
        try:
            marker = getattr(self._owner, "mark_tiles_force_fresh", None)
            if callable(marker):
                for sid in sections_to_load:
                    if callable(preserve_cache) and bool(preserve_cache(int(sid))):
                        preserved_sections.add(int(sid))
                        continue
                    marker(int(sid), window_s=force_fresh_window_s)
        except Exception:
            pass

        for section_id in touched:
            if not isinstance(section_id, int) or section_id <= 0:
                continue
            preserve_section_cache = False
            try:
                preserve_section_cache = bool(
                    int(section_id) in preserved_sections
                    or (
                        callable(preserve_cache)
                        and bool(preserve_cache(int(section_id)))
                    )
                )
            except Exception:
                preserve_section_cache = False
            if preserve_section_cache:
                preserved_sections.add(int(section_id))
            else:
                try:
                    self._cache_service.invalidate_categories_cache(int(section_id))
                except Exception:
                    self._logger.debug(
                        "end_batch: invalidate categories cache failed for %s",
                        section_id,
                        exc_info=True,
                    )
            if do_section_loads and int(section_id) in sections_to_load:
                if preserve_section_cache:
                    self._logger.info(
                        "[BL] end_batch: skip async reload for section %s (optimistic cache primed)",
                        section_id,
                    )
                    continue
                try:
                    sync_map = getattr(self._owner, "_last_categories_sync_load_ts", {})
                    last_sync_ts = (
                        float(sync_map.get(int(section_id), 0.0))
                        if isinstance(sync_map, dict)
                        else 0.0
                    )
                    if (
                        recent_sync_guard_s > 0
                        and last_sync_ts > 0
                        and (time.perf_counter() - last_sync_ts) < recent_sync_guard_s
                    ):
                        self._logger.info(
                            "[BL] end_batch: skip async reload for section %s (recent sync %.0f ms ago)",
                            section_id,
                            (time.perf_counter() - last_sync_ts) * 1000,
                        )
                        continue
                except Exception:
                    pass
                try:
                    self._async_service.load_categories_async(int(section_id))
                except Exception as exc:  # pragma: no cover - defensive logging
                    self._logger.debug(
                        "end_batch: failed to schedule load_categories_async for %s: %s",
                        section_id,
                        exc,
                        exc_info=True,
                    )

        if touched_spheres:
            try:
                self._cache_service.invalidate_structure_cache()
            except Exception as exc:
                self._logger.debug(
                    "end_batch: failed to invalidate structure cache: %s",
                    exc,
                    exc_info=True,
                )
            try:
                delay = get_structure_reload_immediate_delay_ms()
                try:
                    setattr(self._owner, "_suppress_tree_sort_once", True)
                except Exception:
                    pass
                self._async_service.schedule_structure_reload(delay)
            except Exception as exc:
                self._logger.debug(
                    "end_batch: failed to schedule structure reload: %s",
                    exc,
                    exc_info=True,
                )
            self._schedule_top_panels_refresh()
            return

        # Category-only batch updates: avoid full structure reload.
        self._schedule_top_panels_refresh()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_item_added(
        self, item_type: str, parent_id: int, item_data: dict[str, Any]
    ) -> None:
        """Обработчик события добавления элемента.

        ✅ ИСПРАВЛЕНИЕ: Улучшена обработка ошибок и добавлена проверка на None.
        """
        try:
            self._logger.info(
                "[BL] item_added: type=%s, parent_id=%s", item_type, parent_id
            )
            marker = getattr(self._owner, "mark_interactive_structure_activity", None)
            if callable(marker) and item_type in {"section", "category", "link"}:
                marker(reason=f"item-added:{item_type}")
            if item_type == "link":
                category_id = (
                    item_data.get("category_id")
                    if isinstance(item_data, dict)
                    else None
                )
                if category_id is not None:
                    self._cache_service.invalidate_categories_cache(category_id)
                self._schedule_top_panels_refresh()
                return

            if item_type == "category":
                section_id = parent_id or (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                if self._batch_mode:
                    self.add_batch_section(section_id)
                    return
                optimistic_applied = self._try_optimistic_category_refresh(
                    section_id,
                    item_data if isinstance(item_data, dict) else None,
                    allow_insert=True,
                )
                if not optimistic_applied:
                    self._cache_service.invalidate_categories_cache(section_id)
                if (
                    not optimistic_applied
                    and isinstance(section_id, int)
                    and section_id > 0
                ):
                    self._async_service.load_categories_async(section_id)
                # Category insert is handled incrementally by tree UI.
                # Avoid full structure reload to prevent global tree/icon repaint.
                self._logger.info(
                    "[BL] category add: targeted section refresh only (no full structure reload), section=%s optimistic=%s",
                    section_id,
                    optimistic_applied,
                )
                self._schedule_top_panels_refresh()
                return

            if item_type == "section":
                sphere_id = (
                    item_data.get("sphere_id") if isinstance(item_data, dict) else None
                )
                if self._batch_mode:
                    self.add_batch_sphere(sphere_id)
                    section_id = (
                        item_data.get("id") if isinstance(item_data, dict) else None
                    )
                    self.add_batch_section(section_id)
                    return
                if isinstance(sphere_id, int) and sphere_id > 0:
                    try:
                        self._cache_service.invalidate_sections_cache(sphere_id)
                    except Exception:
                        pass
                self._cache_service.invalidate_structure_cache()
                # Section add is applied incrementally in tree UI via item_added.
                # Avoid full structure reload to prevent global tree/icon repaint.
                self._logger.info(
                    "[BL] section add: incremental tree update only (no full structure reload), sphere=%s",
                    sphere_id,
                )
                self._schedule_top_panels_refresh()
                return

            self._cache_service.invalidate_structure_cache()
            delay = get_structure_reload_immediate_delay_ms()
            self._async_service.schedule_structure_reload(delay)
            self._schedule_top_panels_refresh()
        except (ValueError, KeyError, TypeError) as exc:
            # ✅ Ожидаемые ошибки валидации данных
            self._logger.error(
                "Validation error in on_item_added handler: %s", exc, exc_info=True
            )
        except AttributeError as exc:
            # ✅ Неожиданные ошибки - отсутствие атрибутов
            self._logger.exception("Critical error in on_item_added handler: %s", exc)
            raise
        except Exception as exc:
            # ✅ Все остальные критические ошибки
            self._logger.exception("Unexpected error in on_item_added handler: %s", exc)
            raise

    def on_item_updated(
        self, item_type: str, item_id: int, item_data: dict[str, Any]
    ) -> None:
        """Обработчик события обновления элемента.

        ✅ ИСПРАВЛЕНИЕ: Улучшена обработка ошибок и добавлена проверка на None.
        """
        try:
            self._logger.info("[BL] item_updated: type=%s, id=%s", item_type, item_id)
            marker = getattr(self._owner, "mark_interactive_structure_activity", None)
            if callable(marker) and item_type in {"section", "category", "link"}:
                marker(reason=f"item-updated:{item_type}")
            if item_type == "link":
                category_id = (
                    item_data.get("category_id")
                    if isinstance(item_data, dict)
                    else None
                )
                # ✅ Проверка на None перед использованием
                if category_id is not None:
                    self._cache_service.invalidate_categories_cache(category_id)
                self._schedule_top_panels_refresh()
                return

            if item_type == "category":
                section_id = (
                    item_data.get("section_id") if isinstance(item_data, dict) else None
                )
                if self._batch_mode:
                    self.add_batch_section(section_id)
                    return
                optimistic_applied = self._try_optimistic_category_refresh(
                    section_id,
                    item_data if isinstance(item_data, dict) else None,
                    allow_insert=False,
                )
                if not optimistic_applied:
                    self._cache_service.invalidate_categories_cache(section_id)
                if (
                    not optimistic_applied
                    and isinstance(section_id, int)
                    and section_id > 0
                ):
                    self._async_service.load_categories_async(section_id)
                # Category update is also incremental in the tree model.
                # Keep targeted section refresh only.
                self._logger.info(
                    "[BL] category update: targeted section refresh only (no full structure reload), section=%s optimistic=%s",
                    section_id,
                    optimistic_applied,
                )
                self._schedule_top_panels_refresh()
                return

            if item_type == "section":
                sphere_id = (
                    item_data.get("sphere_id") if isinstance(item_data, dict) else None
                )
                if isinstance(sphere_id, int) and sphere_id > 0:
                    try:
                        self._cache_service.invalidate_sections_cache(sphere_id)
                    except Exception:
                        pass
                self._cache_service.invalidate_structure_cache()
                # Section update is applied incrementally in tree UI.
                # Avoid full structure reload to prevent global tree/icon repaint.
                self._logger.info(
                    "[BL] section update: incremental tree update only (no full structure reload), section=%s",
                    item_id,
                )
                self._schedule_top_panels_refresh()
                return

            self._cache_service.invalidate_structure_cache()
            self._async_service.schedule_structure_reload(0)
            self._schedule_top_panels_refresh()
        except (ValueError, KeyError, TypeError) as exc:
            # ✅ Ожидаемые ошибки валидации данных
            self._logger.error(
                "Validation error in on_item_updated handler: %s", exc, exc_info=True
            )
        except AttributeError as exc:
            # ✅ Неожиданные ошибки - отсутствие атрибутов
            self._logger.exception("Critical error in on_item_updated handler: %s", exc)
            raise
        except Exception as exc:
            # ✅ Все остальные критические ошибки
            self._logger.exception(
                "Unexpected error in on_item_updated handler: %s", exc
            )
            raise

    def on_item_deleted(self, item_type: str, item_id: int) -> None:
        """Обработчик события удаления элемента.

        ✅ ИСПРАВЛЕНИЕ: Улучшена обработка ошибок.
        """
        try:
            marker = getattr(self._owner, "mark_interactive_structure_activity", None)
            if callable(marker) and item_type in {"section", "category", "link"}:
                marker(reason=f"item-deleted:{item_type}")
            if item_type == "link":
                self._schedule_top_panels_refresh()
                return
            if item_type in ("category", "section"):
                self._cache_service.invalidate_structure_cache()
                if item_type == "section":
                    self._logger.info(
                        "[BL] section delete: incremental tree update only (no full structure reload), section=%s",
                        item_id,
                    )
                else:
                    self._logger.info(
                        "[BL] category delete: incremental tree update only (no full structure reload), category=%s",
                        item_id,
                    )
                self._schedule_top_panels_refresh()
                return
            if self._batch_mode and self._batch_touched_sections:
                return
            self._cache_service.invalidate_structure_cache()
            self._async_service.schedule_structure_reload(0)
            self._schedule_top_panels_refresh()
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
            marker = getattr(self._owner, "mark_interactive_structure_activity", None)
            if callable(marker) and item_type in {"section", "category", "link"} and total > 0:
                marker(reason=f"items-batch-deleted:{item_type}")
            if item_type == "link":
                self._schedule_top_panels_refresh()
                return
            if item_type in ("category", "section"):
                self._cache_service.invalidate_structure_cache()
                force_reload = str(
                    os.getenv("AITE_FORCE_STRUCTURE_RELOAD_ON_BATCH_DELETE", "0")
                ).lower() in {"1", "true", "yes", "on"}
                if force_reload:
                    delay = get_structure_reload_immediate_delay_ms()
                    try:
                        setattr(self._owner, "_suppress_tree_sort_once", True)
                    except Exception:
                        pass
                    self._async_service.schedule_structure_reload(delay)
                self._schedule_top_panels_refresh()
                return
            self._cache_service.invalidate_structure_cache()
            self._async_service.schedule_structure_reload(0)
            self._schedule_top_panels_refresh()
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

    def add_batch_section(self, section_id: int | None) -> None:
        if not self._batch_mode:
            return
        if isinstance(section_id, int) and section_id > 0:
            self._batch_touched_sections.add(int(section_id))

    def add_batch_sphere(self, sphere_id: int | None) -> None:
        if not self._batch_mode:
            return
        if isinstance(sphere_id, int) and sphere_id > 0:
            self._batch_touched_spheres.add(int(sphere_id))

    @property
    def touched_sections(self) -> set[int]:
        return set(self._batch_touched_sections)

    def replace_touched_sections(self, sections: set[int]) -> None:
        normalized = {int(sid) for sid in sections if isinstance(sid, int) and sid > 0}
        if not normalized:
            if self._batch_mode:
                self._batch_touched_sections.clear()
            return
        if not self._batch_mode:
            for section_id in normalized:
                try:
                    self._async_service.load_categories_async(section_id)
                except Exception as exc:  # pragma: no cover - defensive logging
                    self._logger.debug(
                        "replace_touched_sections: failed to load section %s immediately: %s",
                        section_id,
                        exc,
                        exc_info=True,
                    )
            return
        self._batch_touched_sections = normalized
