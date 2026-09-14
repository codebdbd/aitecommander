from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config_data.runtime_config import runtime_app_config as app_config
from app.services.structure_service import StructureService
from app.utils.ui.icon.path_service import icon_path_service

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

MAX_ARCHIVE_ENTRIES = 2000
MAX_MANIFEST_SIZE = 1 * 1024 * 1024  # 1 MB
MAX_DATA_JSON_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_ICON_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per icon
MAX_TOTAL_UNCOMPRESSED_SIZE = 50 * 1024 * 1024  # 50 MB total for archive

ALLOWED_ICON_EXTENSIONS = frozenset({".ico", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})
_ALLOWED_IMAGE_FORMATS = ("PNG", "ICO", "JPEG", "BMP", "GIF", "WEBP")


def _has_image_magic_bytes(blob: bytes) -> bool:
    if len(blob) < 4:
        return False
    # PNG: \x89PNG\r\n\x1a\n
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    # JPEG: \xff\xd8\xff
    if blob.startswith(b"\xff\xd8\xff"):
        return True
    # GIF: GIF87a or GIF89a
    if blob.startswith(b"GIF87a") or blob.startswith(b"GIF89a"):
        return True
    # BMP: BM
    if blob.startswith(b"BM"):
        return True
    # ICO: \x00\x00\x01\x00
    if blob.startswith(b"\x00\x00\x01\x00"):
        return True
    # WEBP: RIFF....WEBP
    if len(blob) >= 12 and blob.startswith(b"RIFF") and blob[8:12] == b"WEBP":
        return True
    return False


def _is_valid_image_blob(blob: bytes) -> bool:
    if not blob:
        return False
    if not _has_image_magic_bytes(blob):
        return False
    from io import BytesIO

    from app.utils.images import verify_image_safe

    return verify_image_safe(BytesIO(blob))


def _sanitize_icon_path(
    raw_icon_path: Any,
    valid_icons: set[str] | None = None,
    default: str = "",
) -> str:
    if not raw_icon_path or not isinstance(raw_icon_path, str):
        return default
    cleaned = raw_icon_path.strip()
    if not cleaned:
        return default

    # Extract bare filename and reject path traversals or drive indicators
    bare_name = Path(cleaned).name
    if not bare_name:
        return default

    suffix = Path(bare_name).suffix.lower()
    if suffix not in ALLOWED_ICON_EXTENSIONS:
        return default

    if valid_icons is not None:
        if bare_name in valid_icons:
            return bare_name
        try:
            icons_dir = icon_path_service.get_user_icons_dir()
            if (icons_dir / bare_name).is_file():
                return bare_name
        except Exception:
            pass
        return default

    return bare_name


class StructureShareService:
    """Export/import section/category trees to shareable archives."""

    def __init__(self, structure_service: StructureService) -> None:
        self._ss = structure_service

    def export_section_archive(self, section_id: int, dest_path: Path) -> None:
        tree = self._ss.export_section_tree(int(section_id))
        self._write_archive("section", tree, dest_path)

    def export_category_archive(self, category_id: int, dest_path: Path) -> None:
        tree = self._ss.export_category_tree(int(category_id))
        self._write_archive("category", tree, dest_path)

    def import_section_archive(self, path: Path, target_sphere_id: int) -> None:
        manifest, data, icons = self._read_archive(path)
        self._validate_manifest(manifest, expected_type="section")
        valid_icons = self._install_icons(icons)
        tree = self._prepare_section_tree_for_import(data, target_sphere_id, valid_icons=valid_icons)
        self._ss.import_section_tree(tree)

    def import_category_archive(self, path: Path, target_section_id: int) -> None:
        manifest, data, icons = self._read_archive(path)
        self._validate_manifest(manifest, expected_type="category")
        valid_icons = self._install_icons(icons)
        tree = self._prepare_category_tree_for_import(data, target_section_id, valid_icons=valid_icons)
        self._ss.import_category_tree(tree)


    def build_filename(self, package_type: str, name: str) -> str:
        safe_name = _normalize_ascii_name(name)
        type_suffix = {"section": "sec", "category": "cat"}.get(
            package_type, package_type
        )
        date_part = datetime.now().strftime("%Y%m%d%H%M")
        return f"{safe_name}_{type_suffix}_{date_part}.zip"

    def _write_archive(self, package_type: str, data: dict, dest_path: Path) -> None:
        payload = deepcopy(data) if isinstance(data, dict) else {}
        icon_files = self._collect_icon_files(payload)
        data_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        manifest = self._build_manifest(package_type, data_bytes, icon_files)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            zf.writestr("data.json", data_bytes)
            for rel, src in icon_files.items():
                try:
                    zf.write(str(src), rel)
                except OSError:
                    logger.warning("Failed to add icon to archive: %s", src)

    def _build_manifest(
        self, package_type: str, data_bytes: bytes, files: dict[str, Path]
    ) -> dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        checksums = {"data.json": _sha256_bytes(data_bytes), "files": {}}
        for rel, src in files.items():
            try:
                checksums["files"][rel] = _sha256_path(src)
            except OSError:
                checksums["files"][rel] = "unavailable"
        return {
            "schema_version": SCHEMA_VERSION,
            "package_type": package_type,
            "package_id": uuid4().hex,
            "created_at": created_at,
            "app_version": app_config.settings.get_app_version(),
            "checksums": checksums,
        }
    def _collect_icon_files(self, data: dict) -> dict[str, Path]:
        """Collect icon files to include into archive from provided tree data."""
        icons_dir = icon_path_service.get_user_icons_dir()
        candidates = self._gather_icon_candidates(data)
        return self._resolve_icon_candidates(candidates, icons_dir)

    def _gather_icon_candidates(self, data: dict) -> list[str]:
        """Gather raw icon path candidates from section/category/link entries."""
        candidates: list[str] = []
        section = data.get("section") or {}
        if isinstance(section, dict):
            candidates.append(section.get("icon_path") or "")
        category = data.get("category") or {}
        if isinstance(category, dict):
            candidates.append(category.get("icon_path") or "")
        for item in data.get("categories") or []:
            if not isinstance(item, dict):
                continue
            cat = item.get("category") or {}
            if isinstance(cat, dict):
                candidates.append(cat.get("icon_path") or "")
            for link in item.get("links") or []:
                if isinstance(link, dict):
                    candidates.append(link.get("icon_path") or "")
        for link in data.get("links") or []:
            if isinstance(link, dict):
                candidates.append(link.get("icon_path") or "")
        return candidates

    def _resolve_icon_candidates(self, candidates: list[str], icons_dir: Path) -> dict[str, Path]:
        """Resolve candidates strictly within user icons directory and build archive-relative map."""
        resolved_icons_dir = icons_dir.resolve()
        files: dict[str, Path] = {}
        for icon_name in candidates:
            if not icon_name or not isinstance(icon_name, str):
                continue
            name_stripped = icon_name.strip()
            if not name_stripped:
                continue

            # Reject path traversal and drive indicators
            if ".." in name_stripped or ":" in name_stripped:
                continue

            candidate_name = Path(name_stripped).name
            if not candidate_name:
                continue

            src = (resolved_icons_dir / candidate_name).resolve()
            try:
                if not src.is_relative_to(resolved_icons_dir):
                    continue
            except AttributeError:
                try:
                    src.relative_to(resolved_icons_dir)
                except ValueError:
                    continue

            if not src.is_file():
                continue

            # Verify safe extension
            if src.suffix.lower() not in ALLOWED_ICON_EXTENSIONS:
                continue

            rel = (Path("files") / "icons" / src.name).as_posix()
            files.setdefault(rel, src)
        return files

    def _safe_read_entry(
        self, zf: zipfile.ZipFile, name: str, max_size: int
    ) -> bytes:
        total_read = 0
        chunks: list[bytes] = []
        with zf.open(name, "r") as stream:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > max_size:
                    raise ValueError(
                        f"Entry '{name}' exceeds maximum allowed size ({max_size} bytes)"
                    )
                chunks.append(chunk)
        return b"".join(chunks)

    def _read_archive(
        self, path: Path
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
        with zipfile.ZipFile(path, "r") as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise ValueError(
                    f"Archive has too many entries ({len(infos)} > {MAX_ARCHIVE_ENTRIES})"
                )

            total_declared_uncompressed = 0
            for info in infos:
                total_declared_uncompressed += info.file_size
                if info.filename == "manifest.json" and info.file_size > MAX_MANIFEST_SIZE:
                    raise ValueError(
                        f"manifest.json declared size ({info.file_size}) exceeds limit ({MAX_MANIFEST_SIZE})"
                    )
                if info.filename == "data.json" and info.file_size > MAX_DATA_JSON_SIZE:
                    raise ValueError(
                        f"data.json declared size ({info.file_size}) exceeds limit ({MAX_DATA_JSON_SIZE})"
                    )
                if info.filename.startswith("files/icons/") and info.file_size > MAX_ICON_FILE_SIZE:
                    raise ValueError(
                        f"Icon {info.filename} declared size ({info.file_size}) exceeds limit ({MAX_ICON_FILE_SIZE})"
                    )

            if total_declared_uncompressed > MAX_TOTAL_UNCOMPRESSED_SIZE:
                raise ValueError(
                    f"Archive total declared uncompressed size ({total_declared_uncompressed}) exceeds limit ({MAX_TOTAL_UNCOMPRESSED_SIZE})"
                )

            manifest_raw = self._safe_read_entry(zf, "manifest.json", MAX_MANIFEST_SIZE)
            data_raw = self._safe_read_entry(zf, "data.json", MAX_DATA_JSON_SIZE)
            cumulative_size = len(manifest_raw) + len(data_raw)
            if cumulative_size > MAX_TOTAL_UNCOMPRESSED_SIZE:
                raise ValueError("Total uncompressed size exceeds archive limit")

            manifest = json.loads(manifest_raw.decode("utf-8"))
            data = json.loads(data_raw.decode("utf-8"))

            icon_entries: dict[str, bytes] = {}
            for info in infos:
                name = info.filename
                if not name.startswith("files/icons/"):
                    continue
                if ".." in Path(name).parts:
                    continue
                icon_blob = self._safe_read_entry(zf, name, MAX_ICON_FILE_SIZE)
                cumulative_size += len(icon_blob)
                if cumulative_size > MAX_TOTAL_UNCOMPRESSED_SIZE:
                    raise ValueError("Total uncompressed size exceeds archive limit")
                icon_entries[Path(name).name] = icon_blob

            self._validate_checksums(manifest, data_raw, zf, icon_entries)

        if not isinstance(manifest, dict) or not isinstance(data, dict):
            raise ValueError("Invalid package format")
        return manifest, data, icon_entries

    def _validate_manifest(self, manifest: dict[str, Any], expected_type: str) -> None:
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported schema version")
        if manifest.get("package_type") != expected_type:
            raise ValueError("Unexpected package type")

    def _validate_checksums(
        self,
        manifest: dict[str, Any],
        data_raw: bytes,
        zf: zipfile.ZipFile,
        icon_entries: dict[str, bytes] | None = None,
    ) -> None:
        checksums = manifest.get("checksums") or {}
        expected_data = (checksums.get("data.json") or "").strip()
        if expected_data and expected_data != _sha256_bytes(data_raw):
            raise ValueError("Checksum mismatch for data.json")
        files = checksums.get("files") or {}
        if not isinstance(files, dict):
            return
        for rel_path, expected_hash in files.items():
            if not expected_hash or expected_hash == "unavailable":
                continue
            if not isinstance(rel_path, str):
                continue
            icon_filename = Path(rel_path).name
            if icon_entries is not None and icon_filename in icon_entries:
                content = icon_entries[icon_filename]
            else:
                try:
                    content = self._safe_read_entry(zf, rel_path, MAX_ICON_FILE_SIZE)
                except (KeyError, ValueError):
                    logger.warning("Missing or oversized file in archive (ignored): %s", rel_path)
                    continue
            actual = _sha256_bytes(content)
            if actual != expected_hash:
                logger.warning("Checksum mismatch for %s (ignored)", rel_path)

    def _install_icons(self, icons: dict[str, bytes]) -> set[str]:
        installed_or_valid: set[str] = set()
        if not icons:
            return installed_or_valid
        icons_dir = icon_path_service.ensure_user_icons_dir().resolve()
        for name, blob in icons.items():
            if not name or not isinstance(name, str):
                continue
            safe_name = Path(name).name
            if not safe_name or ".." in name or ":" in name:
                continue
            suffix = Path(safe_name).suffix.lower()
            if suffix not in ALLOWED_ICON_EXTENSIONS:
                logger.warning("Skipping icon with disallowed extension: %s", safe_name)
                continue
            if not _is_valid_image_blob(blob):
                logger.warning("Skipping icon with invalid image format: %s", safe_name)
                continue

            dest = (icons_dir / safe_name).resolve()
            try:
                if not dest.is_relative_to(icons_dir):
                    continue
            except AttributeError:
                try:
                    dest.relative_to(icons_dir)
                except ValueError:
                    continue

            if not dest.exists():
                try:
                    dest.write_bytes(blob)
                except OSError as write_err:
                    logger.warning("Failed to write icon file %s: %s", dest, write_err)
                    continue

            installed_or_valid.add(safe_name)
        return installed_or_valid

    def _prepare_section_tree_for_import(
        self,
        data: dict[str, Any],
        sphere_id: int,
        valid_icons: set[str] | None = None,
    ) -> dict[str, Any]:
        tree = deepcopy(data)
        section = dict(tree.get("section") or {})
        section.pop("id", None)
        section["sphere_id"] = int(sphere_id)
        section["icon_path"] = _sanitize_icon_path(
            section.get("icon_path"), valid_icons=valid_icons, default=""
        )
        tree["section"] = section

        prepared_categories: list[dict[str, Any]] = []
        for item in tree.get("categories") or []:
            if not isinstance(item, dict):
                continue
            cat = dict(item.get("category") or {})
            cat.pop("id", None)
            cat.pop("section_id", None)
            cat["icon_path"] = _sanitize_icon_path(
                cat.get("icon_path"), valid_icons=valid_icons, default=""
            )
            links = self._sanitize_links(item.get("links") or [], valid_icons=valid_icons)
            prepared_categories.append({"category": cat, "links": links})
        tree["categories"] = prepared_categories
        return tree

    def _prepare_category_tree_for_import(
        self,
        data: dict[str, Any],
        section_id: int,
        valid_icons: set[str] | None = None,
    ) -> dict[str, Any]:
        tree = deepcopy(data)
        cat = dict(tree.get("category") or {})
        cat.pop("id", None)
        cat["section_id"] = int(section_id)
        cat["icon_path"] = _sanitize_icon_path(
            cat.get("icon_path"), valid_icons=valid_icons, default=""
        )
        tree["category"] = cat
        tree["links"] = self._sanitize_links(tree.get("links") or [], valid_icons=valid_icons)
        return tree

    def _sanitize_links(
        self,
        links: list[Any],
        valid_icons: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        sanitized: list[dict[str, Any]] = []
        for link in links:
            if not isinstance(link, dict):
                continue
            item = dict(link)
            item.pop("id", None)
            item.pop("category_id", None)
            item["icon_path"] = _sanitize_icon_path(
                item.get("icon_path"), valid_icons=valid_icons, default="default.ico"
            )
            sanitized.append(item)
        return sanitized


def _sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")
_CYRILLIC_MAP = {
    "\u0430": "a",
    "\u0431": "b",
    "\u0432": "v",
    "\u0433": "g",
    "\u0434": "d",
    "\u0435": "e",
    "\u0451": "e",
    "\u0436": "zh",
    "\u0437": "z",
    "\u0438": "i",
    "\u0439": "y",
    "\u043a": "k",
    "\u043b": "l",
    "\u043c": "m",
    "\u043d": "n",
    "\u043e": "o",
    "\u043f": "p",
    "\u0440": "r",
    "\u0441": "s",
    "\u0442": "t",
    "\u0443": "u",
    "\u0444": "f",
    "\u0445": "h",
    "\u0446": "ts",
    "\u0447": "ch",
    "\u0448": "sh",
    "\u0449": "shch",
    "\u044a": "",
    "\u044b": "y",
    "\u044c": "",
    "\u044d": "e",
    "\u044e": "yu",
    "\u044f": "ya",
    "\u0456": "i",
    "\u0457": "yi",
    "\u0454": "ye",
    "\u0491": "g",
}


def _normalize_ascii_name(name: str) -> str:
    raw = name.strip().replace(" ", "_")
    if raw:
        raw = _transliterate_cyrillic(raw)
    raw = _strip_diacritics(raw)
    cleaned = _NAME_RE.sub("_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower() or "item"


def _transliterate_cyrillic(text: str) -> str:
    out = []
    for ch in text:
        lower = ch.lower()
        if lower in _CYRILLIC_MAP:
            mapped = _CYRILLIC_MAP[lower]
            out.append(mapped)
        else:
            out.append(ch)
    return "".join(out)


def _strip_diacritics(text: str) -> str:
    replacements = {
        "\u00df": "ss",
        "\u00c4": "AE",
        "\u00e4": "ae",
        "\u00d6": "OE",
        "\u00f6": "oe",
        "\u00d8": "O",
        "\u00f8": "o",
        "\u0141": "L",
        "\u0142": "l",
        "\u0110": "D",
        "\u0111": "d",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))

