import fnmatch
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .text_extractors import (
    check_document_content,
    check_document_content_with_snippet,
    extract_text_by_format,
    find_match_in_text,
    make_snippet,
)

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


def check_plain_text_fast_with_snippet(
    filepath: str,
    search_text: str,
    case_sensitive: bool = False,
    whole_words: bool = False,
) -> tuple[bool, str]:
    """Fast chunked stream search for plain text, markdown, and code returning snippet."""
    try:
        with open(filepath, "rb") as f:
            tail_utf8 = ""
            tail_cp1251 = ""
            overlap = len(search_text) + 20
            has_non_ascii = any(ord(c) > 127 for c in search_text)

            while chunk := f.read(256 * 1024):
                raw_chunk_utf8 = chunk.decode("utf-8", errors="ignore")
                t_utf8 = tail_utf8 + raw_chunk_utf8
                idx = find_match_in_text(t_utf8, search_text, case_sensitive, whole_words)
                if idx != -1:
                    return True, make_snippet(t_utf8, idx, len(search_text))
                tail_utf8 = t_utf8[-overlap:] if overlap > 0 else ""

                if has_non_ascii:
                    raw_chunk_cp = chunk.decode("cp1251", errors="ignore")
                    t_cp = tail_cp1251 + raw_chunk_cp
                    idx_cp = find_match_in_text(t_cp, search_text, case_sensitive, whole_words)
                    if idx_cp != -1:
                        return True, make_snippet(t_cp, idx_cp, len(search_text))
                    tail_cp1251 = t_cp[-overlap:] if overlap > 0 else ""
        return False, ""
    except Exception:
        return False, ""


def check_plain_text_fast(
    filepath: str,
    search_text: str,
    case_sensitive: bool = False,
    whole_words: bool = False,
) -> bool:
    """Fast chunked stream search for plain text, markdown, and code."""
    matched, _ = check_plain_text_fast_with_snippet(
        filepath, search_text, case_sensitive, whole_words
    )
    return matched


def check_file_content_with_snippet(
    config: Mapping[str, Any],
    filepath: str,
) -> tuple[bool, str]:
    """Check file content and return (is_match, snippet)."""
    try:
        file_stat = os.stat(filepath)
        if file_stat.st_size > _MAX_CONTENT_SEARCH_SIZE:
            return False, ""

        search_text = config.get("content")
        if not isinstance(search_text, str) or not search_text.strip():
            return False, ""

        case_sensitive = bool(config.get("case_sensitive", False))
        whole_words = bool(config.get("whole_words", False))
        suffix = Path(filepath).suffix.lower().lstrip(".")

        # Skip known non-document media and archives (e.g. mp4, jpg, exe)
        if suffix in _SKIP_CONTENT_EXT:
            return False, ""

        # 1. High-speed document check with early-exit
        doc_matched, snippet = check_document_content_with_snippet(
            filepath, search_text, case_sensitive=case_sensitive, whole_words=whole_words
        )
        if doc_matched is not None:
            return doc_matched, snippet

        # If it's another binary format not recognized as a document, skip
        if is_probably_binary(filepath):
            return False, ""

        # 2. Plain text search: explicit encoding override fallback
        encoding_override = config.get("content_encoding_override")
        if encoding_override and encoding_override.lower() not in ("auto", "utf-8"):
            text = detect_and_read_text(filepath, encoding_override=encoding_override)
            idx = find_match_in_text(text, search_text, case_sensitive, whole_words)
            if idx != -1:
                return True, make_snippet(text, idx, len(search_text))
            return False, ""

        # 3. High-speed stream search for text/code/markdown (UTF-8 & CP1251)
        fast_matched, fast_snippet = check_plain_text_fast_with_snippet(
            filepath, search_text, case_sensitive=case_sensitive, whole_words=whole_words
        )
        if fast_matched:
            return True, fast_snippet

        # 4. Fallback to full charset detection for rare legacy encodings (CP866, KOI8-R, UTF-16)
        detected_text = detect_and_read_text(filepath, encoding_override=None)
        if detected_text:
            idx = find_match_in_text(detected_text, search_text, case_sensitive, whole_words)
            if idx != -1:
                return True, make_snippet(detected_text, idx, len(search_text))

        return False, ""

    except (OSError, Exception):
        return False, ""


def check_file_content(
    config: Mapping[str, Any],
    filepath: str,
) -> bool:
    """Check file contents against configuration rules with automatic format detection.

    Returns ``True`` if the file matches the requested content conditions.
    Supports Office (.docx, .xlsx, .pptx, .odt, .ods, .odp, .doc, .xls, .ppt),
    Ebooks (.fb2), PDF, RTF, and plain text files with automatic encoding detection.
    """
    matched, _ = check_file_content_with_snippet(config, filepath)
    return matched


def matches_criteria_with_snippet(
    config: Mapping[str, Any],
    filepath: str,
    filename: str,
    name_regex,
) -> tuple[bool, str]:
    """Validate file against criteria and return (matches, snippet)."""
    try:
        # 1. Filename pattern check
        pattern = config.get("pattern", "*.*").strip()
        if pattern and pattern not in ("*.*", "*"):
            norm_pattern = pattern
            if not any(c in pattern for c in "*?"):
                norm_pattern = f"*{pattern}" if pattern.startswith(".") else f"*.{pattern}"
            if not fnmatch.fnmatch(filename.lower(), norm_pattern.lower()):
                return False, ""

        # 2. Filename / path regex check
        if name_regex is not None:
            norm_path = filepath.replace("\\", "/")
            if not (name_regex.search(filename) or name_regex.search(norm_path)):
                return False, ""

        # 3. Content match
        snippet = ""
        if config.get("content"):
            matched, snippet = check_file_content_with_snippet(config, filepath)
            if not matched:
                return False, ""

        return True, snippet
    except OSError:
        return False, ""


def matches_criteria(
    config: Mapping[str, Any],
    filepath: str,
    filename: str,
    name_regex,
) -> bool:
    """Validate file against all criteria defined in ``config``."""
    matched, _ = matches_criteria_with_snippet(config, filepath, filename, name_regex)
    return matched
