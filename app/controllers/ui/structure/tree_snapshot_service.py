from __future__ import annotations

import logging
import time
from typing import Callable

from app.config_data.runtime_config import (
    is_tree_snapshot_icon_warmup,
    is_tree_snapshot_suspend_updates,
)
from app.utils.ui.icon.loading_policy import get_tree_icon_loading_policy
from app.utils.ui.icon.icon_resolver import resolve_icon_path
from app.utils.ui.icon.validation import _validate_icon_name

from PyQt6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class TreeSnapshotService(QObject):
    """Asynchronous application of structure tree model snapshots."""

    _ICON_WARMUP_LIMIT = 250

    def __init__(self, *, manager, model) -> None:
        parent = manager if isinstance(manager, QObject) else None
        super().__init__(parent=parent)
        self._model = model
        self._pending: list[dict] | None = None
        self._pending_mode: str = "fast_switch"
        self._on_success: Callable[[], None] | None = None
        self._on_error: Callable[[], None] | None = None
        self._pending_scheduled_ts: float | None = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._apply_pending_snapshot)

    def schedule_snapshot(
        self,
        snapshot: list[dict],
        *,
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[], None] | None = None,
        mode: str = "fast_switch",
    ) -> None:
        """Defer snapshot application until the next Qt event loop cycle."""
        # Create a copy so changes to the original list won't affect application
        self._pending = list(snapshot or [])
        self._pending_mode = str(mode or "fast_switch")
        self._on_success = on_success
        self._on_error = on_error
        self._pending_scheduled_ts = time.perf_counter()
        if self._should_apply_immediately() and not self._timer.isActive():
            self._apply_pending_snapshot()
            return
        if not self._timer.isActive():
            self._timer.start(0)

    def _should_apply_immediately(self) -> bool:
        manager = self.parent()
        if manager is None:
            return False
        try:
            checker = getattr(manager, "_is_initial_structure_load", None)
            if callable(checker):
                return bool(checker())
        except Exception:
            logger.debug(
                "TreeSnapshotService: initial-load snapshot probe failed",
                exc_info=True,
            )
        return False

    def _apply_pending_snapshot(self) -> None:
        t0 = time.perf_counter()
        snapshot = self._pending or []
        snapshot_mode = self._pending_mode or "fast_switch"
        on_success = self._on_success
        on_error = self._on_error
        queue_delay_ms = (
            (t0 - self._pending_scheduled_ts) * 1000.0
            if isinstance(self._pending_scheduled_ts, (int, float))
            else -1.0
        )
        # Reset references before execution to avoid repeated calls
        self._pending = None
        self._pending_mode = "fast_switch"
        self._on_success = None
        self._on_error = None
        self._pending_scheduled_ts = None

        t_pre0 = time.perf_counter()
        processed_snapshot = self._preprocess_snapshot(snapshot)
        t_pre1 = time.perf_counter()
        # Section icon prewarm is intentionally skipped on the critical path.
        # Synchronous icon resolution here caused visible freezes on sphere switch.
        t_secwarm0 = time.perf_counter()
        secwarm_count, secwarm_ms_direct = 0, 0.0
        t_secwarm1 = time.perf_counter()
        tree = getattr(self.parent(), "tree", None)
        suspend_updates = False
        try:
            suspend_updates = is_tree_snapshot_suspend_updates(True)
        except Exception:
            suspend_updates = True

        if tree is not None and suspend_updates:
            try:
                tree.setUpdatesEnabled(False)
            except Exception:
                pass

        apply_ok = False
        t_set0 = t_set1 = None
        reenable_updates_ms = 0.0
        try:
            t_set0 = time.perf_counter()
            try:
                policy = get_tree_icon_loading_policy(snapshot_mode=snapshot_mode)
                sections_first_enabled = policy.sections_first_render
                defer_category_icon_loads = policy.defer_category_loads
            except Exception:
                sections_first_enabled = True
                defer_category_icon_loads = True
            allow_sync_section_fallback = self._should_apply_immediately()
            if not allow_sync_section_fallback and 0.0 <= queue_delay_ms <= 1.0:
                # Initial tree snapshot is applied inline, so the manager's
                # "initial load" probe may already be cleared by this point.
                # Preserve immediate section icons for that one cold-start path.
                allow_sync_section_fallback = True
            self._model.set_snapshot(
                processed_snapshot,
                sections_first=sections_first_enabled,
                defer_category_icon_loads=defer_category_icon_loads,
                allow_sync_section_fallback=allow_sync_section_fallback,
            )
            t_set1 = time.perf_counter()
            apply_ok = True
        except Exception:
            logger.exception(
                "TreeSnapshotService: model failed to accept snapshot",
            )
            if on_error:
                try:
                    on_error()
                except Exception:
                    logger.debug(
                        "TreeSnapshotService: on_error callback failed",
                        exc_info=True,
                    )
        finally:
            if tree is not None and suspend_updates:
                _tr0 = time.perf_counter()
                try:
                    tree.setUpdatesEnabled(True)
                except Exception:
                    pass
                reenable_updates_ms = (time.perf_counter() - _tr0) * 1000.0

        if apply_ok:
            t_ok0 = time.perf_counter()
            if on_success:
                try:
                    on_success()
                except Exception:
                    logger.debug(
                        "TreeSnapshotService: on_success callback failed",
                        exc_info=True,
                    )
            t_ok1 = time.perf_counter()
            t_warm0 = time.perf_counter()
            self._schedule_warmup(processed_snapshot)
            t_warm1 = time.perf_counter()
            sections_count = len(processed_snapshot)
            categories_count = 0
            try:
                categories_count = sum(
                    len(s.get("categories") or [])
                    for s in processed_snapshot
                    if isinstance(s, dict)
                )
            except Exception:
                categories_count = -1
            model_set_ms = (
                (float(t_set1) - float(t_set0)) * 1000.0
                if isinstance(t_set0, (int, float)) and isinstance(t_set1, (int, float))
                else -1.0
            )
            logger.info(
                "[Perf] TreeSnapshotService.apply sections=%s categories=%s queue_delay=%.2fms preprocess=%.2fms section_icon_prewarm=%.2fms(sec=%s direct=%.2fms) model_set_snapshot=%.2fms reenable_updates=%.2fms on_success=%.2fms warmup_schedule=%.2fms total=%.2fms suspend_updates=%s",
                sections_count,
                categories_count,
                queue_delay_ms,
                (t_pre1 - t_pre0) * 1000.0,
                (t_secwarm1 - t_secwarm0) * 1000.0,
                secwarm_count,
                secwarm_ms_direct,
                model_set_ms,
                reenable_updates_ms,
                (t_ok1 - t_ok0) * 1000.0,
                (t_warm1 - t_warm0) * 1000.0,
                (t_warm1 - t0) * 1000.0,
                suspend_updates,
            )

    def _prewarm_section_icons_before_apply(
        self, snapshot: list[dict], *, mode: str = "fast_switch"
    ) -> tuple[int, float]:
        """Inject ready QIcon objects for section rows before model.set_snapshot().

        This removes the expensive per-section sync fallback path inside
        ``StructureTreeModel.set_snapshot()`` while preserving immediate section icons.
        Categories remain async-loaded as before.
        """
        if not snapshot:
            return 0, 0.0

        try:
            manager = self.parent()
            checker = getattr(manager, "_is_initial_structure_load", None)
            if callable(checker) and checker():
                return 0, 0.0
        except Exception:
            logger.debug(
                "TreeSnapshotService: initial-load section icon prewarm probe failed",
                exc_info=True,
            )

        # In full_restore mode prefer visual completeness (all restored section icons),
        # while fast_switch mode warms only top visible sections.
        if str(mode or "fast_switch") == "full_restore":
            max_sections = len(snapshot)
        else:
            try:
                policy = get_tree_icon_loading_policy(snapshot_mode=mode)
                max_sections = max(0, int(policy.section_sync_limit))
            except Exception:
                max_sections = 6
        warmed = 0
        direct_ms = 0.0

        for section in snapshot[:max_sections]:
            if not isinstance(section, dict):
                continue
            icon_val = section.get("icon")
            try:
                if icon_val is not None and hasattr(icon_val, "isNull") and not icon_val.isNull():
                    continue
            except Exception:
                pass

            icon_path = self._extract_icon_path(section) or self._extract_icon_path(
                section, "icon_path"
            )
            if not icon_path:
                continue

            try:
                t0 = time.perf_counter()
                from app.utils.ui.icon.icon_service import get_icon

                # Use the same resolution path as the model sync fallback to maximize hits.
                icon = get_icon(str(icon_path).strip(), source="tree_snapshot_section_prewarm")
                direct_ms += (time.perf_counter() - t0) * 1000.0
                if icon is not None and hasattr(icon, "isNull") and not icon.isNull():
                    section["icon"] = icon
                    warmed += 1
            except Exception:
                logger.debug(
                    "TreeSnapshotService: section icon prewarm failed for %r",
                    icon_path,
                    exc_info=True,
                )

        return warmed, direct_ms

    def _schedule_warmup(self, snapshot: list[dict]) -> None:
        """Warm icon cache after snapshot is applied to avoid blocking UI."""
        try:
            enabled = is_tree_snapshot_icon_warmup(False)
        except Exception:
            enabled = False
        if not enabled:
            return

        def _run():
            warmup_ready, warmup_expected, warmup_warmed = self._warmup_icons(snapshot)
            self._apply_warmup_state(
                warmup_ready, warmup_expected, warmup_warmed
            )

        try:
            QTimer.singleShot(0, _run)
        except Exception:
            _run()

    @staticmethod
    def _extract_icon_path(payload: dict, field: str = "icon") -> str | None:
        """Return trimmed icon path from payload if available."""
        value = payload.get(field)
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
        return None

    def _preprocess_snapshot(self, snapshot: list[dict]) -> list[dict]:
        """Preserve icon paths without blocking the UI thread."""
        processed: list[dict] = []
        resolved_paths: dict[str, str] = {}

        def _resolve_cached_icon_path(icon_path: str) -> str:
            cached = resolved_paths.get(icon_path)
            if cached is not None:
                return cached
            resolved = resolve_icon_path(icon_path) or icon_path
            resolved_paths[icon_path] = resolved
            return resolved

        for section in snapshot or []:
            if not isinstance(section, dict):
                processed.append(section)
                continue

            section_copy = dict(section)
            icon_path = self._extract_icon_path(section_copy) or section_copy.get("icon_path")
            if isinstance(icon_path, str):
                resolved_icon_path = _resolve_cached_icon_path(icon_path)
            else:
                resolved_icon_path = icon_path
            section_copy["icon_path"] = resolved_icon_path

            categories = section_copy.get("categories")
            if isinstance(categories, list):
                processed_categories: list[dict] = []
                for category in categories:
                    if not isinstance(category, dict):
                        processed_categories.append(category)
                        continue
                    category_copy = dict(category)
                    cat_icon_path = self._extract_icon_path(category_copy) or category_copy.get("icon_path")
                    if isinstance(cat_icon_path, str):
                        resolved_cat_icon_path = _resolve_cached_icon_path(cat_icon_path)
                    else:
                        resolved_cat_icon_path = cat_icon_path
                    category_copy["icon_path"] = resolved_cat_icon_path
                    processed_categories.append(category_copy)
                section_copy["categories"] = processed_categories

            processed.append(section_copy)

        return processed

    def _apply_warmup_state(
        self, ready: bool, expected: int, warmed: int
    ) -> None:
        try:
            self._model._tree_snapshot_icons_ready = bool(ready)
            self._model._tree_snapshot_icons_expected = int(expected)
            self._model._tree_snapshot_icons_warmed = int(warmed)
        except Exception:
            logger.debug(
                "TreeSnapshotService: failed to apply icon warmup state",
                exc_info=True,
            )

    def _warmup_icons(self, snapshot: list[dict]) -> tuple[bool, int, int]:
        """Warm icon cache so tree icons appear without delayed loading."""
        if not snapshot:
            return True, 0, 0

        deps = self._load_icon_dependencies()
        if deps is None:
            return False, 0, 0

        if deps["app_cls"].instance() is None:
            logger.debug("TreeSnapshotService: icon warmup skipped (no QApplication)")
            return False, 0, 0

        themed_icons, path_icons = self._collect_icon_paths(snapshot)
        total_icons = len(themed_icons) + len(path_icons)
        if total_icons == 0:
            return True, 0, 0

        if self._should_skip_warmup(total_icons):
            return True, 0, 0

        warmed_total = self._warmup_icons_in_gui_thread(
            themed_icons,
            path_icons,
            deps,
        )

        ready = warmed_total >= total_icons

        if warmed_total:
            logger.debug(
                "TreeSnapshotService: warmed %s of %s tree icon(s) before applying snapshot",
                warmed_total,
                total_icons,
            )
        return ready, total_icons, warmed_total

    def _load_icon_dependencies(self) -> dict[str, object] | None:
        try:
            from PyQt6.QtWidgets import QApplication

            from app.utils.ui.icon.icon_operations.cache_proxy import icon_cache
            from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
            from app.utils.ui.qt.gui_exec import is_gui_thread, run_in_gui_thread_sync
        except Exception as exc:  # noqa: BLE001 - defensive import guard
            logger.debug(
                "TreeSnapshotService: icon warmup skipped (imports failed): %s",
                exc,
            )
            return None

        return {
            "app_cls": QApplication,
            "icon_cache": icon_cache,
            "create_icon_from_path": create_icon_from_path,
            "is_gui_thread": is_gui_thread,
            "run_in_gui_thread_sync": run_in_gui_thread_sync,
        }

    def _collect_icon_paths(
        self, snapshot: list[dict]
    ) -> tuple[set[str], set[str]]:
        themed_icons: set[str] = set()
        path_icons: set[str] = set()

        def _collect(value: object) -> None:
            if not isinstance(value, str):
                return
            trimmed = value.strip()
            if not trimmed:
                return
            if trimmed.startswith("abspath::"):
                trimmed = trimmed.split("::", 1)[-1]
            if (
                trimmed.startswith(":/")
                or trimmed.startswith("qrc:/")
                or "\\" in trimmed
                or "/" in trimmed
                or (len(trimmed) > 2 and trimmed[1] == ":" and trimmed[2] in ("\\", "/"))
            ):
                path_icons.add(trimmed)
            else:
                if _validate_icon_name(trimmed):
                    themed_icons.add(trimmed)
                    return

                resolved = resolve_icon_path(trimmed)
                if resolved:
                    path_icons.add(resolved)

        for section in snapshot:
            if not isinstance(section, dict):
                continue
            _collect(section.get("icon"))
            _collect(section.get("icon_path"))
            categories = section.get("categories") or []
            for category in categories:
                if not isinstance(category, dict):
                    continue
                _collect(category.get("icon"))
                _collect(category.get("icon_path"))

        return themed_icons, path_icons

    def _should_skip_warmup(self, total_icons: int) -> bool:
        if total_icons > self._ICON_WARMUP_LIMIT:
            logger.debug(
                "TreeSnapshotService: skipping icon warmup for %s icons",
                total_icons,
            )
            return True
        return False

    def _warmup_icons_in_gui_thread(
        self,
        themed_icons: set[str],
        path_icons: set[str],
        deps: dict[str, object],
    ) -> int:
        warmed_total = 0

        def _warmup() -> int:
            nonlocal warmed_total
            icon_cache = deps["icon_cache"]
            create_icon_from_path = deps["create_icon_from_path"]
            for icon_name in themed_icons:
                try:
                    icon_cache.get_icon(icon_name, source="tree_snapshot")
                    warmed_total += 1
                except Exception as exc:  # noqa: BLE001 - cache must not break UI
                    logger.debug(
                        "TreeSnapshotService: themed icon warmup failed for '%s': %s",
                        icon_name,
                        exc,
                    )
            for icon_path in path_icons:
                try:
                    create_icon_from_path(icon_path)
                    warmed_total += 1
                except Exception as exc:  # noqa: BLE001 - cache must not break UI
                    logger.debug(
                        "TreeSnapshotService: path icon warmup failed for '%s': %s",
                        icon_path,
                        exc,
                    )
            return warmed_total

        runner = deps["run_in_gui_thread_sync"]
        is_gui_thread = deps["is_gui_thread"]
        try:
            if is_gui_thread():
                warmed_total = _warmup()
            else:
                warmed_total = runner(_warmup)
        except Exception:  # noqa: BLE001 - defensive
            logger.debug("TreeSnapshotService: icon warmup execution failed", exc_info=True)
        return warmed_total
