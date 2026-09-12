import fnmatch
import os
from collections.abc import Mapping
from typing import Any

# Maximum file size for content search (10 MB)
_MAX_CONTENT_SEARCH_SIZE = 10 * 1024 * 1024
# Buffer size for reading files (1 MB chunks)
_READ_BUFFER_SIZE = 1024 * 1024

_BINARY_EXT = {
    "exe",
    "dll",
    "so",
    "dylib",
    "bin",
    "img",
    "iso",
    "class",
    "pyc",
    "jar",
    "pak",
    "dat",
}
_SAMPLE_BYTES = 4096
_NULL_THRESHOLD = 2


def is_probably_binary(filepath: str) -> bool:
    """Check if file is likely binary by extension or null-byte heuristic."""
    ext = filepath.rsplit(".", 1)[-1].lower() if "." in filepath else ""
    if ext in _BINARY_EXT:
        return True
    try:
        with open(filepath, "rb") as f:
            sample = f.read(_SAMPLE_BYTES)
    except OSError:
        return False

    if b"\x00" in sample and not (
        sample.startswith(b"\xff\xfe") or sample.startswith(b"\xfe\xff")
    ):
        null_count = sample.count(b"\x00")
        if null_count > _NULL_THRESHOLD:
            return True
    return False


def detect_and_read_text(filepath: str, encoding_override: str | None = None) -> str:
    """Read full file text using specified encoding or auto-detect with fallbacks."""
    if encoding_override:
        try:
            with open(filepath, encoding=encoding_override, errors="replace") as f:
                return f.read()
        except (OSError, LookupError):
            pass

    raw_bytes: bytes | None = None
    try:
        from charset_normalizer import from_bytes

        with open(filepath, "rb") as f:
            raw_bytes = f.read()
        res = from_bytes(raw_bytes).best()
        if res is not None:
            return str(res)
    except (ImportError, OSError):
        pass

    if raw_bytes is None:
        try:
            with open(filepath, "rb") as f:
                raw_bytes = f.read()
        except OSError:
            return ""

    for enc in ("utf-8", "cp1251", "cp866", "koi8-r", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def check_file_content(
    config: Mapping[str, Any],
    filepath: str,
) -> bool:
    """Check file contents against configuration rules.

    Returns ``True`` if the file matches the requested content conditions.
    Files larger than 10MB are skipped to prevent GUI freezing.
    Files are read in chunks or decoded safely.
    """
    try:
        file_stat = os.stat(filepath)
        if file_stat.st_size > _MAX_CONTENT_SEARCH_SIZE:
            return False

        search_text = config.get("content")
        if not isinstance(search_text, str) or not search_text.strip():
            return False

        search_text = search_text.lower()

        # If file is binary and not a known text format, skip
        if is_probably_binary(filepath):
            return False

        encoding_override = config.get("content_encoding_override")
        # If encoding override is specified or auto-detect needed for non-utf8
        # For standard UTF-8 stream search, chunked reading avoids huge RAM usage:
        if encoding_override and encoding_override.lower() not in ("auto", "utf-8"):
            text = detect_and_read_text(filepath, encoding_override=encoding_override)
            return search_text in text.lower()

        # Try chunked reading with UTF-8 first
        overlap_size = len(search_text) - 1 if len(search_text) > 1 else 0
        previous_chunk_tail = ""
        encoding_tried = "utf-8"

        with open(filepath, encoding=encoding_tried, errors="replace") as f:
            while True:
                chunk = f.read(_READ_BUFFER_SIZE)
                if not chunk:
                    break

                chunk_lower = chunk.lower()
                search_chunk = previous_chunk_tail + chunk_lower

                if search_text in search_chunk:
                    return True

                if len(chunk_lower) >= overlap_size and overlap_size > 0:
                    previous_chunk_tail = chunk_lower[-overlap_size:]
                else:
                    previous_chunk_tail = chunk_lower if overlap_size > 0 else ""

        # Fallback to auto-detection (e.g. CP1251 / CP866) if UTF-8 chunk search found nothing
        # and file is smaller than 2MB
        if file_stat.st_size <= 2 * 1024 * 1024:
            detected_text = detect_and_read_text(filepath, encoding_override=None)
            if detected_text and search_text in detected_text.lower():
                return True

        return False

    except (OSError, UnicodeDecodeError):
        return False


def matches_criteria(
    config: Mapping[str, Any],
    filepath: str,
    filename: str,
    name_regex,
) -> bool:
    """Validate file against all criteria defined in ``config``.

    Consolidates the logic shared by `FileSearchDialog` and `FileSearchWorker`.
    """
    try:
        os.stat(filepath)

        # 1. Filename pattern check
        pattern = config.get("pattern", "*.*")
        if pattern and not fnmatch.fnmatch(filename, pattern):
            return False

        # 2. Filename regex check
        if name_regex is not None and not name_regex.search(filename):
            return False

        # 3. Content match
        if config.get("content"):
            if not check_file_content(config, filepath):
                return False

        return True
    except OSError:
        return False
