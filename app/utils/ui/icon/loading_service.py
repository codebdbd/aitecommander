from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

from PyQt6.QtGui import QIcon

from .cache_manager import get_cached_category_icon, peek_cached_category_icon
from .icon_resolver import resolve_category_icon_path, resolve_icon_path
from .path_service import icon_path_service
from .validation import is_valid_icon_file


def _normalize_icon_ref(icon_path: str | None) -> str:
    return str(icon_path or "").strip()


class IconLoadingService:
    """Shared facade for path-based icon resolution and loading.

    This service intentionally focuses on path-backed icons. Theme-relative icons
    still use the existing theme icon cache/creator pipeline.
    """

    _CACHE_LIMIT = 1024

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._generic_resolved_cache: OrderedDict[str, str] = OrderedDict()
        self._category_resolved_cache: OrderedDict[str, str] = OrderedDict()
        self._existing_path_cache: OrderedDict[str, str] = OrderedDict()

    @staticmethod
    def _is_absolute_icon_path(candidate: str) -> bool:
        return (
            candidate.startswith((":/", "qrc:/", "qresource:"))
            or candidate.startswith(("/", "\\"))
            or (len(candidate) > 2 and candidate[1] == ":" and candidate[2] in ("\\", "/"))
        )

    def clear(self) -> None:
        with self._lock:
            self._generic_resolved_cache.clear()
            self._category_resolved_cache.clear()
            self._existing_path_cache.clear()

    def _remember(
        self,
        cache: OrderedDict[str, str],
        key: str,
        value: str,
    ) -> str:
        with self._lock:
            cache[key] = value
            cache.move_to_end(key)
            while len(cache) > self._CACHE_LIMIT:
                cache.popitem(last=False)
        return value

    def resolve_existing_path(self, icon_path: str | None) -> str:
        normalized = _normalize_icon_ref(icon_path)
        if not normalized:
            return ""

        with self._lock:
            cached = self._existing_path_cache.get(normalized)
            if cached is not None:
                self._existing_path_cache.move_to_end(normalized)
                return cached

        try:
            candidate = Path(normalized)
            if candidate.is_absolute() and candidate.exists() and is_valid_icon_file(candidate):
                return self._remember(
                    self._existing_path_cache,
                    normalized,
                    str(candidate),
                )
        except Exception:
            pass

        for base_dir_getter in (
            icon_path_service.get_user_icons_dir,
            icon_path_service.get_ui_icons_dir,
        ):
            try:
                candidate = base_dir_getter() / normalized
                if candidate.exists() and is_valid_icon_file(candidate):
                    return self._remember(
                        self._existing_path_cache,
                        normalized,
                        str(candidate),
                    )
            except Exception:
                pass
        return self._remember(self._existing_path_cache, normalized, "")

    def resolve_path(self, icon_path: str | None, *, category: bool = False) -> str:
        normalized = _normalize_icon_ref(icon_path)
        if not normalized:
            return ""

        cache = (
            self._category_resolved_cache if category else self._generic_resolved_cache
        )
        with self._lock:
            cached = cache.get(normalized)
            if cached is not None:
                cache.move_to_end(normalized)
                return cached

        resolver = resolve_category_icon_path if category else resolve_icon_path
        resolved = resolver(normalized) or ""

        return self._remember(cache, normalized, resolved)

    def peek_path_icon(self, icon_path: str | None, *, category: bool = False) -> QIcon | None:
        normalized = _normalize_icon_ref(icon_path)
        if not normalized:
            return None
        resolved = (
            normalized
            if self._is_absolute_icon_path(normalized)
            else self.resolve_path(normalized, category=category)
        )
        if not resolved:
            return None
        try:
            icon = peek_cached_category_icon(resolved)
        except Exception:
            return None
        return icon if icon is not None and not icon.isNull() else None

    def get_path_icon(self, icon_path: str | None, *, category: bool = False) -> QIcon:
        normalized = _normalize_icon_ref(icon_path)
        if not normalized:
            return QIcon()
        resolved = (
            normalized
            if self._is_absolute_icon_path(normalized)
            else self.resolve_path(normalized, category=category)
        )
        if not resolved:
            return QIcon()
        try:
            return get_cached_category_icon(resolved)
        except Exception:
            return QIcon()


icon_loading_service = IconLoadingService()
