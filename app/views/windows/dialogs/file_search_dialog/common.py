import fnmatch
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .text_extractors import extract_text_by_format

# Maximum file size for content search (20 MB)
_MAX_CONTENT_SEARCH_SIZE = 20 * 1024 * 1024
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

# Obvious non-document media/archive/executable formats to skip in content search
_SKIP_CONTENT_EXT = {
    "exe",
    "dll",
    "so",
    "dylib",
    "bin",
    "img",
    "iso",
    "class",
    "pyc",
    "mp3",
    "wav",
    "flac",
    "ogg",
    "aac",
    "mp4",
    "avi",
    "mkv",
    "mov",
    "webm",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "ico",
    "webp",
    "tiff",
    "bmp",
    "psd",
    "ai",
    "raw",
    "nef",
    "dng",
    "zip",
    "rar",
    "7z",
    "tar",
    "gz",
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

    try:
        with open(filepath, "rb") as f:
            raw_bytes = f.read(_MAX_CONTENT_SEARCH_SIZE)
    except OSError:
        return ""

    if not raw_bytes:
        return ""

    # Check BOM indicators
    if raw_bytes.startswith(b"\xff\xfe"):
        return raw_bytes.decode("utf-16-le", errors="replace")
    if raw_bytes.startswith(b"\xfe\xff"):
        return raw_bytes.decode("utf-16-be", errors="replace")
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes.decode("utf-8-sig", errors="replace")

    # Charset detection via charset-normalizer if available
    try:
        from charset_normalizer import from_bytes

        res = from_bytes(raw_bytes).best()
        if res is not None:
            return str(res)
    except (ImportError, Exception):
        pass

    # Standard fallback encodings
    for enc in ("utf-8", "cp1251", "cp866", "utf-16-le", "koi8-r", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def check_file_content(
    config: Mapping[str, Any],
    filepath: str,
) -> bool:
    """Check file contents against configuration rules with automatic format detection.

    Returns ``True`` if the file matches the requested content conditions.
    Supports Office (.docx, .xlsx, .pptx, .odt, .ods, .odp, .doc, .xls, .ppt),
    Ebooks (.fb2), PDF, RTF, and plain text files with automatic encoding detection.
    """
    try:
        file_stat = os.stat(filepath)
        if file_stat.st_size > _MAX_CONTENT_SEARCH_SIZE:
            return False

        search_text = config.get("content")
        if not isinstance(search_text, str) or not search_text.strip():
            return False

        search_text = search_text.lower()
        suffix = Path(filepath).suffix.lower().lstrip(".")

        # Skip known non-document media and archives (e.g. mp4, jpg, exe)
        if suffix in _SKIP_CONTENT_EXT:
            return False

        # 1. Automatic format detection (Word, Excel, PPT, PDF, ODT, FB2, RTF, OLE)
        extracted = extract_text_by_format(filepath)
        if extracted is not None:
            return search_text in extracted.lower()

        # If it's another binary format not recognized as a document, skip
        if is_probably_binary(filepath):
            return False

        # 2. Plain text chunked search (UTF-8 stream)
        encoding_override = config.get("content_encoding_override")
        if encoding_override and encoding_override.lower() not in ("auto", "utf-8"):
            text = detect_and_read_text(filepath, encoding_override=encoding_override)
            return search_text in text.lower()

        overlap_size = len(search_text) - 1 if len(search_text) > 1 else 0
        previous_chunk_tail = ""

        try:
            with open(filepath, encoding="utf-8", errors="strict") as f:
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
        except (UnicodeDecodeError, OSError):
            # Not valid strict UTF-8; fall through to encoding auto-detection
            pass

        # 3. Fallback to encoding auto-detection (e.g. CP1251, CP866, UTF-16)
        detected_text = detect_and_read_text(filepath, encoding_override=None)
        if detected_text and search_text in detected_text.lower():
            return True

        return False

    except (OSError, Exception):
        return False


def matches_criteria(
    config: Mapping[str, Any],
    filepath: str,
    filename: str,
    name_regex,
) -> bool:
    """Validate file against all criteria defined in ``config``."""
    try:
        os.stat(filepath)

        # 1. Filename pattern check
        pattern = config.get("pattern", "*.*")
        if pattern and pattern not in ("*.*", "*"):
            if not fnmatch.fnmatch(filename, pattern):
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
