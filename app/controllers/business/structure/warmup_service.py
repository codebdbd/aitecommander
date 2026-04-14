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

            self._prime_target_section_cache(sphere_id)
            self._schedule_category_preload(payload, sphere_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            try:
                self._logger.debug(
                    "Warm cache after structure_loaded failed: %s", exc, exc_info=True
                )
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

    def _schedule_category_preload(
        self, payload: list[dict[str, Any]], sphere_id: int
    ) -> None:
        """Отключена множественная предзагрузка для устранения рывков интерфейса."""
        # ВРЕМЕННО ОТКЛЮЧЕНО: множественные вызовы load_categories_async
        # вызывают мерцание правой панели при загрузке каждого раздела отдельно
        try:
            self._logger.debug("Category preload disabled to prevent UI flickering")
        except Exception:
            pass

    def _preload_section(
        self, section_id: int, planned_token: int, planned_sphere: int
    ) -> None:
        """Отключен метод предзагрузки раздела для устранения рывков интерфейса."""
        # ВРЕМЕННО ОТКЛЮЧЕНО: вызывает множественные обновления UI
        # Заглушки для параметров, чтобы избежать предупреждений vulture
        _ = planned_token, planned_sphere
        try:
            self._logger.debug("Section preload disabled to prevent UI flickering")
        except Exception:
            pass
