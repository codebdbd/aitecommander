from __future__ import annotations

from pathlib import Path


def is_valid_bookmarks_html(path: str, max_size_mb: int = 50) -> bool:
    """Quick check of HTML bookmarks file by path.
    - file exists and is a file
    - extension .html/.htm
    - reasonable size (default < 50 MB)
    - minimal content check: file beginning contains HTML doctype/tag
    """
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return False
        if p.suffix.lower() not in {".html", ".htm"}:
            return False
        if p.stat().st_size > max_size_mb * 1024 * 1024:
            return False
        # minimal content check
        with p.open("r", encoding="utf-8", errors="ignore") as f:
            head = f.read(2048).lower()
            if ("<!doctype html" not in head) and ("<html" not in head):
                return False
        return True
    except OSError:
        return False


def can_parse_bookmarks_html(content: str) -> bool:
    """Light heuristic for early assessment of content suitability for parsing.
    Does not replace a full parser.
    Check for basic HTML structures and typical bookmarks nodes.
    """
    if not content or not isinstance(content, str):
        return False
    low = content[:4096].lower()
    # basic HTML
    if ("<html" not in low) and ("<!doctype" not in low):
        return False
    # typical bookmark export elements (browser-dependent, heuristic)
    keywords = ("<dl", "<dt", "<h3", "bookmark")
    return any(k in low for k in keywords)
