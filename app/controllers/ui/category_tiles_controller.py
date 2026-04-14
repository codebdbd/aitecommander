# app/controllers/ui/category_tiles_controller.py

import logging
import time
from typing import Optional, Protocol

from PyQt6.QtCore import QTimer

from app.config_data.runtime_config import is_fast_tiles_from_cache_enabled
from app.utils.metrics import get_metrics

logger = logging.getLogger(__name__)


class CategoryTilesLike(Protocol):
    def set_categories(self, categories: list[dict]) -> None: ...


class CategoryTilesController:
    """Single control point for category tiles.

    Required dependencies: `ui_state`, `structure_business`.
    Direct interaction with tiles widget is optional and can be attached via
    `attach_tiles_widget()`.
    """

    def __init__(self, ui_state, structure_business, *, main_window=None) -> None:
        if ui_state is None or structure_business is None:
            raise ValueError(
                "CategoryTilesController requires ui_state and structure_business"
            )
        self.ui_state = ui_state
        self.business = structure_business
        self._tiles: Optional[CategoryTilesLike] = None

    def attach_tiles_widget(self, tiles_widget: CategoryTilesLike) -> None:
        """Optionally set tiles widget for direct update operations."""
        self._tiles = tiles_widget

    def refresh(self, section_id: int, *, switch_view: bool = True) -> None:
        """Refresh tiles for the specified section."""
        started_ts = time.perf_counter()
        if not isinstance(section_id, int) or section_id <= 0:
            logger.warning(
                "CategoryTilesController.refresh: invalid section_id=%s", section_id
            )
            return

        if self._try_apply_cached(section_id, switch_view=switch_view):
            total_ms = (time.perf_counter() - started_ts) * 1000
            self._record_pipeline_metric("categories.pipeline.total_ms", total_ms)
            logger.info(
                "[Perf] Categories pipeline section=%s source=cache total=%.2f ms",
                section_id,
                total_ms,
            )
            return

        source_label = self._detect_fetch_source(section_id)
        fetch_started_ts = time.perf_counter()
        try:
            categories = self.business.get_categories(int(section_id))
        except (ValueError, RuntimeError):
            # Expected data retrieval errors — log and finish without raising
            logger.exception(
                "CategoryTilesController.refresh: get_categories failed for section #%s",
                section_id,
            )
            return

        fetch_ms = (time.perf_counter() - fetch_started_ts) * 1000
        apply_started_ts = time.perf_counter()
        applied_categories = categories or []
        self._apply_categories(
            applied_categories, section_id=section_id, switch_view=switch_view
        )
        apply_ms = (time.perf_counter() - apply_started_ts) * 1000
        total_ms = (time.perf_counter() - started_ts) * 1000
        self._record_pipeline_metric("categories.pipeline.fetch_ms", fetch_ms)
        self._record_pipeline_metric("categories.pipeline.apply_ms", apply_ms)
        self._record_pipeline_metric("categories.pipeline.total_ms", total_ms)
        logger.info(
            "[Perf] Categories pipeline section=%s source=%s count=%s fetch=%.2f ms apply=%.2f ms total=%.2f ms",
            section_id,
            source_label,
            len(applied_categories),
            fetch_ms,
            apply_ms,
            total_ms,
        )

    def clear(self) -> None:
        """Clear category tiles (show empty set)."""
        applied_via_ui_state = False
        try:
            applied_via_ui_state = bool(self.ui_state.switch_to_category_tiles([]))
        except (ValueError, RuntimeError):
            logger.exception("CategoryTilesController.clear: ui_state switch failed")
            return
        if (not applied_via_ui_state) and self._tiles is not None:
            try:
                self._tiles.set_categories([])
            except (ValueError, RuntimeError):
                logger.exception(
                    "CategoryTilesController.clear: tiles.set_categories failed"
                )
                return

    def _try_apply_cached(self, section_id: int, *, switch_view: bool) -> bool:
        """Fast-path: render cached categories immediately, refresh later."""
        try:
            force_fresh = getattr(self.business, "should_force_fresh_tiles", None)
            if callable(force_fresh) and bool(force_fresh(int(section_id))):
                logger.info(
                    "[Perf] Categories cache bypass section=%s reason=force_fresh_window",
                    section_id,
                )
                return False
        except Exception:
            pass

        try:
            use_cache = is_fast_tiles_from_cache_enabled(True)
        except Exception:
            use_cache = True
        if not use_cache:
            return False

        cached = []
        try:
            if hasattr(self.business, "get_cached_categories"):
                cached = self.business.get_cached_categories(int(section_id)) or []
        except Exception:
            cached = []

        if not cached:
            return False

        cached_started_ts = time.perf_counter()
        self._apply_categories(cached, section_id=section_id, switch_view=switch_view)
        cached_apply_ms = (time.perf_counter() - cached_started_ts) * 1000
        self._record_pipeline_metric("categories.cache.apply_ms", cached_apply_ms)
        logger.info(
            "[Perf] Categories cache apply section=%s count=%s apply=%.2f ms",
            section_id,
            len(cached),
            cached_apply_ms,
        )

        # Schedule background refresh to ensure data is current.
        def _refresh():
            refresh_started_ts = time.perf_counter()
            try:
                fetch_started_ts = time.perf_counter()
                fresh = self.business.get_categories(int(section_id)) or []
                fetch_ms = (time.perf_counter() - fetch_started_ts) * 1000
                if fresh and fresh != cached:
                    apply_started_ts = time.perf_counter()
                    self._apply_categories(
                        fresh, section_id=section_id, switch_view=switch_view
                    )
                    apply_ms = (time.perf_counter() - apply_started_ts) * 1000
                    total_ms = (time.perf_counter() - refresh_started_ts) * 1000
                    self._record_pipeline_metric(
                        "categories.cache_refresh.fetch_ms", fetch_ms
                    )
                    self._record_pipeline_metric(
                        "categories.cache_refresh.apply_ms", apply_ms
                    )
                    self._record_pipeline_metric(
                        "categories.cache_refresh.total_ms", total_ms
                    )
                    logger.info(
                        "[Perf] Categories cache-refresh section=%s count=%s fetch=%.2f ms apply=%.2f ms total=%.2f ms",
                        section_id,
                        len(fresh),
                        fetch_ms,
                        apply_ms,
                        total_ms,
                    )
            except Exception:
                logger.debug(
                    "CategoryTilesController: background refresh failed for section #%s",
                    section_id,
                    exc_info=True,
                )

        try:
            QTimer.singleShot(0, _refresh)
        except Exception:
            _refresh()

        return True

    def _detect_fetch_source(self, section_id: int) -> str:
        """Classify refresh source for diagnostics before calling get_categories()."""
        try:
            force_fresh = getattr(self.business, "should_force_fresh_tiles", None)
            if callable(force_fresh) and bool(force_fresh(int(section_id))):
                return "db"
        except Exception:
            return "db"

        try:
            cache_manager = getattr(self.business, "cache_manager", None)
            if cache_manager is None:
                return "db"
            cached = cache_manager.get(f"categories_{int(section_id)}")
            if cached is not None:
                return "cache/optimistic"
        except Exception:
            return "db"
        return "db"

    def _apply_categories(
        self, categories: list[dict], *, section_id: int, switch_view: bool
    ) -> None:
        t0 = time.perf_counter()
        t_ui_state_done = t0
        t_fallback_done = t0
        applied_via_ui_state = False
        if switch_view:
            # Primary path: via ui_state (centralizes stack switching)
            try:
                applied_via_ui_state = bool(
                    self.ui_state.switch_to_category_tiles(
                        categories or [],
                        force_show_when_empty=True,
                    )
                )
            except (ValueError, RuntimeError):
                logger.exception(
                    "CategoryTilesController.refresh: ui_state switch failed for section #%s",
                    section_id,
                )
                return
            t_ui_state_done = time.perf_counter()
        else:
            # Update tiles data without changing current stack view.
            try:
                if hasattr(self.ui_state, "set_tiles_data"):
                    applied_via_ui_state = bool(
                        self.ui_state.set_tiles_data(categories or [])
                    )
            except (ValueError, RuntimeError):
                logger.exception(
                    "CategoryTilesController.refresh: ui_state set_tiles_data failed for section #%s",
                    section_id,
                )
                return
            t_ui_state_done = time.perf_counter()
        # Fallback path for legacy wiring where ui_state cannot reach tiles widget.
        if (not applied_via_ui_state) and self._tiles is not None:
            try:
                self._tiles.set_categories(categories or [])
            except (ValueError, RuntimeError):
                logger.exception(
                    "CategoryTilesController.refresh: tiles.set_categories failed for section #%s",
                    section_id,
                )
                return
            t_fallback_done = time.perf_counter()
        else:
            t_fallback_done = time.perf_counter()

        logger.info(
            "[Perf] CategoryTilesController.apply section=%s count=%s switch_view=%s ui_state=%.2f ms fallback=%.2f ms total=%.2f ms applied_via_ui_state=%s",
            section_id,
            len(categories or []),
            switch_view,
            (t_ui_state_done - t0) * 1000.0,
            (t_fallback_done - t_ui_state_done) * 1000.0,
            (t_fallback_done - t0) * 1000.0,
            applied_via_ui_state,
        )

    @staticmethod
    def _record_pipeline_metric(metric_name: str, value_ms: float) -> None:
        metrics = get_metrics()
        metrics.record_timing(metric_name, value_ms)
        stats = metrics.get_stats(metric_name)
        count = int(stats.get("count", 0))
        if count > 0 and count % 20 == 0:
            logger.info(
                "[PerfAgg] %s: n=%s p50=%.2f ms p95=%.2f ms avg=%.2f ms",
                metric_name,
                count,
                float(stats.get("p50", 0.0)),
                float(stats.get("p95", 0.0)),
                float(stats.get("avg", 0.0)),
            )
