from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)


def derive_dropped_web_link_name(url: str) -> str:
    """Derive a readable fallback name from a dropped URL."""
    clean_url = url.strip()
    try:
        parsed = urlparse(clean_url)
        host = parsed.netloc.replace("www.", "", 1)
        path_name = unquote((parsed.path or "").rstrip("/").split("/")[-1])
        return path_name or host or clean_url
    except Exception:
        logger.debug("Failed to derive dropped URL name for %s", url, exc_info=True)
    return clean_url


def build_dropped_web_link_payload(url: str, category_id: int) -> dict:
    """Build a standard link payload for an externally dropped URL."""
    return build_dropped_link_payload(url, category_id)


def build_dropped_link_payload(target: str, category_id: int) -> dict:
    """Build a standard link payload for a dropped web URL or local path."""
    clean_target = target.strip()
    link_type = classify_dropped_link_target(clean_target)
    name = (
        derive_dropped_web_link_name(clean_target)
        if link_type == "web"
        else derive_dropped_local_link_name(clean_target)
    )
    return {
        "name": name,
        "url": clean_target,
        "type": link_type,
        "icon_path": "",
        "notes": "",
        "last_used": None,
        "position": 0,
        "category_id": int(category_id),
        "args": "",
        "is_favorite": 0,
    }


def classify_dropped_link_target(target: str) -> str:
    """Classify dropped target into one of the supported link types."""
    parsed = urlparse(target)
    if parsed.scheme.lower() in {"http", "https"}:
        return "web"

    path = Path(target)
    try:
        if path.is_dir():
            return "folder"
    except OSError:
        pass

    suffix = path.suffix.lower()
    if suffix in {".exe", ".lnk"}:
        return "program"
    if suffix in {".ps1", ".py", ".bat", ".cmd"}:
        return "script"
    return "file"


def derive_dropped_local_link_name(target: str) -> str:
    """Derive a readable fallback name from a dropped local path."""
    path = Path(target)
    name = path.name if path.is_dir() else path.stem
    return name or target.strip()
