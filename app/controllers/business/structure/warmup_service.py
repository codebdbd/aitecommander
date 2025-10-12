"""Warm cache helpers for structure business logic."""

from __future__ import annotations

from logging import Logger
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QTimer

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.controllers.business.structure_business import StructureBusinessLogic
    from app.controllers.structure_modules import CacheManager
    from app.controllers.structure_services.utilities import UtilityService

    from .async_service import StructureAsyncService
    from .cache_service import StructureCacheService


class StructureWarmupService:
    """Encapsulates structure warm-cache routines after load."""

    def __init__(
        self,
        owner: StructureBusinessLogic,
        cache_manager: CacheManager,
        utility_service: UtilityService,
        cache_service: StructureCacheService,
        async_service: StructureAsyncService,
        logger: Logger,
    ) -> None:
        self._owner = owner
        self._cache_manager = cache_manager
        self._utility_service = utility_service
        self._cache_service = cache_service
        self._async_service = async_service
        self._logger = logger

    def warm_after_structure_loaded(self, payload: list[dict[str, Any]]) -> None:
        """Warm caches using loaded payload and service helpers."""
        try:
            sphere_id = getattr(self._owner, "current_sphere_id", None)
            if not isinstance(sphere_id, int) or sphere_id <= 0:
                return

            self._cache_service.warm_first_category(sphere_id, payload)
            self._prime_target_section_cache(sphere_id)
            self._schedule_category_preload(payload, sphere_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            try:
                self._logger.debug("Warm cache after structure_loaded failed: %s", exc, exc_info=True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _prime_target_section_cache(self, sphere_id: int) -> None:
        def _deferred_warmup() -> None:
            try:
                self._utility_service.get_target_section_id(
                    current_sphere_id=sphere_id,
                    get_sections=self._owner.get_sections,
                    get_categories=self._owner.get_categories,
                    cache_get=self._cache_manager.get,
                    cache_set=self._cache_manager.set,
                )
            except Exception as ex:  # pragma: no cover - defensive logging
                self._logger.debug("Deferred warm cache failed: %s", ex, exc_info=True)

        try:
            QTimer.singleShot(0, _deferred_warmup)
        except (RuntimeError, TypeError):  # pragma: no cover - Qt edge cases
            _deferred_warmup()

        try:
            _deferred_warmup()
        except Exception as ex:  # pragma: no cover - defensive logging
            self._logger.debug("Immediate warm cache failed: %s", ex, exc_info=True)

    def _schedule_category_preload(self, payload: list[dict[str, Any]], sphere_id: int) -> None:
        try:
            if not isinstance(payload, list) or not payload:
                return

            from app.config_data import app_config

            preload_limit = int(app_config.ui.get_preload_categories_limit())
            delay_step_ms = int(app_config.ui.get_preload_delay_step_ms())
            planned_token = int(getattr(self._owner, "_switch_token", 0))
            planned_sphere = sphere_id

            for idx, section in enumerate(payload[:preload_limit]):
                section_id = section.get("id") if isinstance(section, dict) else None
                if not isinstance(section_id, int) or section_id <= 0:
                    continue
                delay = max(0, int(idx) * delay_step_ms)

                QTimer.singleShot(
                    delay,
                    lambda sid=section_id, token=planned_token, psid=planned_sphere: self._preload_section(
                        sid, token, psid
                    ),
                )
        except Exception:  # pragma: no cover - defensive logging
            self._logger.debug("Warm cache: preload categories scheduling failed", exc_info=True)

    def _preload_section(self, section_id: int, planned_token: int, planned_sphere: int) -> None:
        try:
            current_token = int(getattr(self._owner, "_switch_token", 0))
            if current_token != int(planned_token):
                return
            current_sphere = getattr(self._owner, "current_sphere_id", None)
            if current_sphere != planned_sphere:
                return

            ops = getattr(self._owner, "async_operations", None)
            if ops and hasattr(ops, "load_categories_async"):
                ops.load_categories_async(section_id)
                return
            async_ops = getattr(self._async_service, "async_operations", None)
            if async_ops and hasattr(async_ops, "load_categories_async"):
                async_ops.load_categories_async(section_id)
        except Exception as ex:  # pragma: no cover - defensive logging
            self._logger.debug("Preload categories failed: %s", ex, exc_info=True)
