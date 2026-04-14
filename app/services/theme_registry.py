from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from app.config_data.runtime_config import runtime_app_config as app_config
from app.core.paths.path_manager import PathManager

logger = logging.getLogger(__name__)

_THEME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


@dataclass(frozen=True)
class ThemeDefinition:
    theme_id: str
    name: str
    version: str
    is_dark: bool
    qss_path: Path
    icons_dir: Path
    preview_path: Path | None
    source: str  # "bundled" | "user"
    origin_path: Path


class ThemeRegistry:
    """Discover and cache bundled + user themes."""

    def __init__(self, config=app_config, *, cache_ttl: float = 2.0) -> None:
        self._config = config
        self._cache_ttl = max(0.0, float(cache_ttl))
        self._cache_ts: float = 0.0
        self._cache: dict[str, ThemeDefinition] = {}
        self._lock = RLock()
        self._required_icons_cache: set[str] | None = None

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
            self._cache_ts = 0.0
            self._required_icons_cache = None

    def list_themes(self) -> list[ThemeDefinition]:
        now = time.time()
        with self._lock:
            if self._cache and (now - self._cache_ts) < self._cache_ttl:
                return list(self._cache.values())

        bundled = self._load_themes_from_root(
            PathManager.themes_dir(),
            source="bundled",
            base_path=PathManager.app_root(),
        )
        user = self._load_themes_from_root(
            PathManager.user_themes_dir(),
            source="user",
            base_path=None,
        )

        merged: dict[str, ThemeDefinition] = {}
        for theme in bundled:
            merged[theme.theme_id] = theme
        for theme in user:
            if theme.theme_id in merged:
                logger.warning(
                    "User theme overrides bundled theme id: %s", theme.theme_id
                )
            merged[theme.theme_id] = theme

        with self._lock:
            self._cache = merged
            self._cache_ts = now
            return list(self._cache.values())

    def get_theme(self, theme_id: str) -> ThemeDefinition | None:
        if not theme_id:
            return None
        theme_id = str(theme_id).strip().lower()
        for theme in self.list_themes():
            if theme.theme_id == theme_id:
                return theme
        return None

    def get_theme_ids(self) -> list[str]:
        return [theme.theme_id for theme in self.list_themes()]

    def get_default_theme_id(self) -> str:
        if self.get_theme("light"):
            return "light"
        themes = self.list_themes()
        return themes[0].theme_id if themes else "light"

    def is_user_theme(self, theme_id: str) -> bool:
        theme = self.get_theme(theme_id)
        return bool(theme and theme.source == "user")

    def get_required_icon_names(self, *, base_theme_id: str = "light") -> set[str]:
        with self._lock:
            if self._required_icons_cache is not None:
                return set(self._required_icons_cache)

        theme = self.get_theme(base_theme_id)
        if theme is None:
            return set()

        allowed_ext = {
            ext.lower() for ext in self._config.get_supported_icon_formats()
        }
        required: set[str] = set()
        try:
            for entry in theme.icons_dir.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in allowed_ext:
                    continue
                required.add(entry.name.lower())
        except OSError as exc:
            logger.warning("Failed to read base theme icons: %s", exc)

        with self._lock:
            self._required_icons_cache = set(required)
        return required

    def _load_themes_from_root(
        self, root: Path, *, source: str, base_path: Path | None
    ) -> list[ThemeDefinition]:
        themes: list[ThemeDefinition] = []
        if not root or not root.exists():
            return themes
        try:
            for entry in sorted(root.iterdir(), key=lambda p: p.name.lower()):
                if not entry.is_dir():
                    continue
                manifest = entry / "theme.json"
                if not manifest.exists():
                    continue
                theme = self._load_theme_from_manifest(
                    manifest,
                    source=source,
                    base_path=base_path if source == "bundled" else entry,
                )
                if theme is not None:
                    themes.append(theme)
        except OSError as exc:
            logger.warning("Failed to scan themes at %s: %s", root, exc)
        return themes

    def _load_theme_from_manifest(
        self, manifest_path: Path, *, source: str, base_path: Path
    ) -> ThemeDefinition | None:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Invalid theme manifest %s: %s", manifest_path, exc)
            return None

        theme_id = str(data.get("id", "")).strip().lower()
        if not self._is_valid_theme_id(theme_id):
            logger.warning("Invalid theme id in %s: %r", manifest_path, theme_id)
            return None
        name = str(data.get("name", "")).strip()
        if not name:
            logger.warning("Theme name missing in %s", manifest_path)
            return None
        version = str(data.get("version", "")).strip() or "1.0.0"
        is_dark = bool(data.get("is_dark", False))

        qss_rel = data.get("qss")
        icons_rel = data.get("icons_dir")
        if not qss_rel or not icons_rel:
            logger.warning("Theme missing qss or icons_dir in %s", manifest_path)
            return None

        qss_path = self._resolve_safe_path(base_path, qss_rel)
        icons_dir = self._resolve_safe_path(base_path, icons_rel, require_dir=True)
        if qss_path is None or icons_dir is None:
            logger.warning("Theme paths invalid in %s", manifest_path)
            return None
        if not qss_path.is_file():
            logger.warning("Theme QSS file missing: %s", qss_path)
            return None
        if not icons_dir.is_dir():
            logger.warning("Theme icons dir missing: %s", icons_dir)
            return None

        preview_path = None
        preview_rel = data.get("preview")
        if preview_rel:
            preview_path = self._resolve_safe_path(base_path, preview_rel)
            if preview_path is not None and not preview_path.is_file():
                preview_path = None

        return ThemeDefinition(
            theme_id=theme_id,
            name=name,
            version=version,
            is_dark=is_dark,
            qss_path=qss_path,
            icons_dir=icons_dir,
            preview_path=preview_path,
            source=source,
            origin_path=manifest_path,
        )

    def _resolve_safe_path(
        self, base_path: Path, rel_path: str, *, require_dir: bool = False
    ) -> Path | None:
        try:
            rel = Path(str(rel_path))
        except Exception:
            return None
        if rel.is_absolute():
            return None
        if ".." in rel.parts:
            return None

        try:
            base_resolved = base_path.resolve()
            candidate = (base_resolved / rel).resolve()
        except OSError:
            return None

        try:
            candidate.relative_to(base_resolved)
        except ValueError:
            return None

        if require_dir and candidate.exists() and not candidate.is_dir():
            return None
        return candidate

    def _is_valid_theme_id(self, theme_id: str) -> bool:
        return bool(theme_id and _THEME_ID_RE.match(theme_id))

    def is_valid_theme_id(self, theme_id: str) -> bool:
        return self._is_valid_theme_id(theme_id)


theme_registry = ThemeRegistry()
