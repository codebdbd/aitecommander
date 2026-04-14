from __future__ import annotations

import json
import logging
import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.config_data.runtime_config import runtime_app_config as app_config
from app.core.paths.path_manager import PathManager
from app.services.theme_registry import ThemeDefinition, theme_registry
from app.utils.ui.icon.validation import is_valid_icon_file

logger = logging.getLogger(__name__)


class ThemeImportError(Exception):
    """Base class for theme import failures."""


class ThemeValidationError(ThemeImportError):
    """Raised when a theme package fails validation."""


class ThemeConflictError(ThemeImportError):
    """Raised when a theme id conflicts with an installed theme."""

    def __init__(self, theme_id: str, source: str):
        super().__init__(f"Theme '{theme_id}' already exists ({source}).")
        self.theme_id = theme_id
        self.source = source


@dataclass
class ThemeManifest:
    theme_id: str
    name: str
    version: str
    is_dark: bool
    qss_path: Path
    icons_dir: Path
    preview_path: Path | None
    root: Path


class ThemeImportService:
    """Import user themes from zip files or directories."""

    def __init__(self, *, config=app_config, registry=theme_registry) -> None:
        self._config = config
        self._registry = registry

    def import_theme(
        self,
        source_path: Path,
        *,
        conflict_policy: str = "prompt",
    ) -> ThemeDefinition:
        """Import a theme from a zip file or directory.

        conflict_policy: "prompt" | "overwrite" | "rename"
        """
        src = Path(source_path)
        if not src.exists():
            raise ThemeImportError(f"Theme source not found: {src}")

        user_root = PathManager.user_themes_dir()
        user_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="theme_import_") as temp_dir:
            temp_root = Path(temp_dir)
            extracted_root = (
                self._extract_zip(src, temp_root)
                if src.is_file() and zipfile.is_zipfile(src)
                else self._copy_from_dir(src, temp_root)
            )

            manifest = self._validate_theme_root(extracted_root)
            theme_id = manifest.theme_id

            existing = self._registry.get_theme(theme_id)
            if existing is not None:
                if existing.source == "bundled":
                    if conflict_policy == "rename":
                        theme_id = self._generate_unique_id(theme_id)
                        self._rewrite_theme_id(manifest.root, theme_id)
                        manifest.theme_id = theme_id
                    else:
                        raise ThemeConflictError(theme_id, existing.source)
                else:
                    if conflict_policy == "overwrite":
                        self._remove_user_theme(theme_id)
                    elif conflict_policy == "rename":
                        theme_id = self._generate_unique_id(theme_id)
                        self._rewrite_theme_id(manifest.root, theme_id)
                        manifest.theme_id = theme_id
                    else:
                        raise ThemeConflictError(theme_id, existing.source)

            dest_dir = user_root / theme_id
            if dest_dir.exists():
                raise ThemeImportError(f"Destination already exists: {dest_dir}")

            shutil.move(str(manifest.root), str(dest_dir))

        self._registry.invalidate()
        theme = self._registry.get_theme(theme_id)
        if theme is None:
            raise ThemeImportError(f"Imported theme not found in registry: {theme_id}")
        return theme

    def remove_theme(self, theme_id: str) -> None:
        """Remove a user-installed theme."""
        theme = self._registry.get_theme(theme_id)
        if theme is None:
            raise ThemeImportError(f"Theme not found: {theme_id}")
        if theme.source != "user":
            raise ThemeImportError(f"Cannot remove bundled theme: {theme_id}")
        self._remove_user_theme(theme_id)
        self._registry.invalidate()

    def _remove_user_theme(self, theme_id: str) -> None:
        theme = self._registry.get_theme(theme_id)
        if theme is None:
            return
        try:
            shutil.rmtree(theme.origin_path.parent)
        except OSError as exc:
            raise ThemeImportError(f"Failed to remove theme '{theme_id}': {exc}") from exc

    def _extract_zip(self, src: Path, temp_root: Path) -> Path:
        max_zip = int(self._config.get_theme_max_package_size())
        max_files = int(self._config.get_theme_max_files())
        max_uncompressed = int(self._config.get_theme_max_uncompressed_size())

        if src.stat().st_size > max_zip:
            raise ThemeValidationError("Theme package is too large.")

        with zipfile.ZipFile(src, "r") as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            if len(infos) > max_files:
                raise ThemeValidationError("Theme package contains too many files.")

            total_size = sum(info.file_size for info in infos)
            if total_size > max_uncompressed:
                raise ThemeValidationError("Theme package uncompressed size is too large.")

            self._validate_zip_members(infos)
            root_name = self._detect_zip_root(infos)
            zf.extractall(temp_root)

        return temp_root / root_name if root_name else temp_root

    def _copy_from_dir(self, src: Path, temp_root: Path) -> Path:
        if not src.is_dir():
            raise ThemeImportError(f"Theme source is not a folder or zip: {src}")
        max_files = int(self._config.get_theme_max_files())
        max_uncompressed = int(self._config.get_theme_max_uncompressed_size())
        file_entries = [p for p in src.rglob("*") if p.is_file()]
        if len(file_entries) > max_files:
            raise ThemeValidationError("Theme folder contains too many files.")
        total_size = sum(p.stat().st_size for p in file_entries)
        if total_size > max_uncompressed:
            raise ThemeValidationError("Theme folder size is too large.")
        dest = temp_root / src.name
        shutil.copytree(src, dest)
        return dest

    def _validate_zip_members(self, infos: Iterable[zipfile.ZipInfo]) -> None:
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or name.startswith("../"):
                raise ThemeValidationError("Theme package contains an invalid path.")
            parts = Path(name).parts
            if ".." in parts:
                raise ThemeValidationError("Theme package contains an invalid path.")

    def _detect_zip_root(self, infos: Iterable[zipfile.ZipInfo]) -> str:
        roots: set[str] = set()
        for info in infos:
            name = info.filename.replace("\\", "/").lstrip("/")
            if not name or name.startswith("__MACOSX/"):
                continue
            parts = name.split("/")
            if parts:
                roots.add(parts[0])
        return roots.pop() if len(roots) == 1 else ""

    def _validate_theme_root(self, root: Path) -> ThemeManifest:
        manifest_path = root / "theme.json"
        if not manifest_path.exists():
            raise ThemeValidationError("theme.json is missing in the package root.")
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ThemeValidationError(f"theme.json is invalid: {exc}") from exc

        theme_id = str(data.get("id", "")).strip().lower()
        if not theme_id:
            raise ThemeValidationError("theme.json: missing id.")
        if not theme_registry.is_valid_theme_id(theme_id):
            raise ThemeValidationError("theme.json: invalid id format.")

        name = str(data.get("name", "")).strip()
        if not name:
            raise ThemeValidationError("theme.json: missing name.")
        version = str(data.get("version", "")).strip() or "1.0.0"
        is_dark = bool(data.get("is_dark", False))

        qss_rel = data.get("qss")
        icons_rel = data.get("icons_dir")
        if not qss_rel or not icons_rel:
            raise ThemeValidationError("theme.json: qss and icons_dir are required.")

        qss_path = self._resolve_theme_path(root, qss_rel, require_file=True)
        icons_dir = self._resolve_theme_path(root, icons_rel, require_dir=True)
        if qss_path is None or icons_dir is None:
            raise ThemeValidationError("theme.json: invalid qss or icons_dir path.")
        if qss_path.suffix.lower() != ".qss":
            raise ThemeValidationError("theme.json: qss must point to a .qss file.")

        preview_path = None
        preview_rel = data.get("preview")
        if preview_rel:
            preview_path = self._resolve_theme_path(root, preview_rel, require_file=True)

        self._validate_allowed_files(root)
        self._validate_icons(icons_dir)

        return ThemeManifest(
            theme_id=theme_id,
            name=name,
            version=version,
            is_dark=is_dark,
            qss_path=qss_path,
            icons_dir=icons_dir,
            preview_path=preview_path,
            root=root,
        )

    def _resolve_theme_path(
        self, root: Path, rel_path: str, *, require_file: bool = False, require_dir: bool = False
    ) -> Path | None:
        try:
            rel = Path(str(rel_path))
        except Exception:
            return None
        if rel.is_absolute() or ".." in rel.parts:
            return None
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return None
        if require_file and not candidate.is_file():
            return None
        if require_dir and not candidate.is_dir():
            return None
        return candidate

    def _validate_allowed_files(self, root: Path) -> None:
        allowed_ext = {
            ".json",
            ".qss",
            ".md",
            ".txt",
            *{ext.lower() for ext in self._config.get_supported_icon_formats()},
        }
        for entry in root.rglob("*"):
            if not entry.is_file():
                continue
            if entry.name in {".DS_Store"}:
                continue
            if entry.name.startswith("._"):
                continue
            if "__MACOSX" in entry.parts:
                continue
            if entry.suffix.lower() not in allowed_ext:
                raise ThemeValidationError(
                    f"Unsupported file type in theme package: {entry.name}"
                )

    def _validate_icons(self, icons_dir: Path) -> None:
        required = self._registry.get_required_icon_names()
        if not required:
            raise ThemeValidationError("Base theme icon manifest is empty.")
        allowed_ext = {
            ext.lower() for ext in self._config.get_supported_icon_formats()
        }

        existing: set[str] = set()
        for entry in icons_dir.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in allowed_ext:
                continue
            existing.add(entry.name.lower())
            if not is_valid_icon_file(entry):
                raise ThemeValidationError(f"Invalid icon file: {entry.name}")

        missing = sorted(required - existing)
        if missing:
            preview = ", ".join(missing[:6])
            raise ThemeValidationError(
                f"Missing required icons. Examples: {preview}"
            )

    def _generate_unique_id(self, base_id: str) -> str:
        existing_ids = set(self._registry.get_theme_ids())
        if base_id not in existing_ids:
            return base_id
        suffix = 2
        while True:
            candidate = f"{base_id}-{suffix}"
            if candidate not in existing_ids:
                return candidate
            suffix += 1

    def _rewrite_theme_id(self, root: Path, new_id: str) -> None:
        manifest_path = root / "theme.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["id"] = new_id
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8"
        )
