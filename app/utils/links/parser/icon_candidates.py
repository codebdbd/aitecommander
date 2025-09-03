"""
Discover favicon candidates from HTML and well-known paths/services.

Global manifest executor
------------------------
This module maintains a single global ThreadPoolExecutor used to fetch and parse
web app manifests concurrently when `on_manifest_icons` callback is provided.

Rationale:
- Reuse a single small pool across calls to avoid creating/destroying threads per
  page parse under load.
- Limit concurrency via app_config. The setting `ICON_MANIFEST_MAX_WORKERS` is
  read from `app.config_data.app_config` (defaults to 4). The value is clamped
  to a minimum of 1 by construction (`max(1, value)`).
- The pool is registered for shutdown at process exit via `atexit`.

Testing/Utilities:
- Use `shutdown_manifest_executor(wait=False, cancel_futures=True)` to explicitly
  stop and dispose the global pool between tests. A subsequent call that needs
  the pool will lazily recreate it.
"""

from __future__ import annotations

import json
from typing import List, Optional, Callable
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .constants import FORMAT_RANK, TARGET_SIZE, logger
from app.config_data import app_config
from .http_client import http_request


_MANIFEST_EXECUTOR = None
_MANIFEST_EXECUTOR_GUARD = threading.Lock()


def _get_manifest_executor() -> ThreadPoolExecutor:
    """Get or create the global manifest ThreadPoolExecutor.

    Threads count is taken from `app_config.ICON_MANIFEST_MAX_WORKERS` (default 4),
    and is clamped to minimum 1. The executor is registered for process-exit
    shutdown via `atexit`.
    """
    global _MANIFEST_EXECUTOR
    if _MANIFEST_EXECUTOR is not None:
        return _MANIFEST_EXECUTOR
    with _MANIFEST_EXECUTOR_GUARD:
        if _MANIFEST_EXECUTOR is None:
            try:
                max_workers = int(getattr(app_config, "ICON_MANIFEST_MAX_WORKERS", 4) or 4)
            except Exception:
                logger.debug("Failed to read ICON_MANIFEST_MAX_WORKERS from app_config; using default 4", exc_info=True)
                max_workers = 4
            _MANIFEST_EXECUTOR = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="manifest")
            try:
                atexit.register(lambda: _MANIFEST_EXECUTOR.shutdown(wait=False, cancel_futures=True))
            except Exception:
                logger.debug("Failed to register atexit shutdown for manifest executor", exc_info=True)
    return _MANIFEST_EXECUTOR


def shutdown_manifest_executor(wait: bool = False, cancel_futures: bool = True) -> bool:
    """Explicitly shutdown the global manifest executor.

    Useful in tests or controlled environments to ensure clean teardown between
    runs. Returns True if an executor existed and was shut down, False if there
    was nothing to do. A future call to `_get_manifest_executor()` will lazily
    recreate the pool on demand.
    """
    global _MANIFEST_EXECUTOR
    with _MANIFEST_EXECUTOR_GUARD:
        if _MANIFEST_EXECUTOR is None:
            return False
        try:
            _MANIFEST_EXECUTOR.shutdown(wait=wait, cancel_futures=cancel_futures)
        finally:
            _MANIFEST_EXECUTOR = None
    return True
def parse_icon_size(sizes_attr: str) -> int:
    """Parse sizes attribute and return the maximum declared size.

    - Supports multiple space-separated entries, e.g. "16x16 32x32 180x180" → 180
    - Treats "any" as 0 (unknown vector/scalable size)
    - Falls back to first integer if no WxH pattern is found
    """
    if not sizes_attr:
        return 0
    s = (sizes_attr or "").strip().lower()
    if s == "any":
        return 0
    import re

    pairs = re.findall(r"(\d+)\s*x\s*(\d+)", s)
    if pairs:
        sizes = []
        for w, h in pairs:
            try:
                sizes.append(max(int(w), int(h)))
            except Exception:
                logger.debug(f"Invalid WxH pair in sizes attribute: {w}x{h}", exc_info=True)
                continue
        if sizes:
            return max(sizes)
    # Fallback: take first integer if present (non-standard values)
    m = re.search(r"(\d+)", s)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            logger.debug("Failed to parse integer from sizes attribute", exc_info=True)
    logger.debug(f"Invalid sizes attribute: {sizes_attr}")
    return 0


# --- Helpers ---
def _detect_format(href: str, type_attr: str | None) -> str:
    ext = ""
    if href:
        lower = href.lower().split("?")[0].split("#")[0]
        if "." in lower:
            ext = lower.rsplit(".", 1)[-1]
    t = (type_attr or "").lower()
    if "avif" in t or ext == "avif":
        return "avif"
    if "apng" in t or ext == "apng":
        return "apng"
    if "svg" in t or ext == "svg":
        return "svg"
    if "x-icon" in t or ext == "ico":
        return "ico"
    if "png" in t or ext == "png":
        return "png"
    if "webp" in t or ext == "webp":
        return "webp"
    if "gif" in t or ext == "gif":
        return "gif"
    if "jpeg" in t or ext in ("jpg", "jpeg"):
        return "jpg"
    if ext:
        return ext
    return "unknown"


def _collect_link_icons(soup: BeautifulSoup, base_url: str) -> tuple[list[dict], list[str], bool]:
    candidates: List[dict] = []
    manifest_urls: List[str] = []

    def _add_link_candidate(link, rel_label: str, base_priority: int):
        href = link.get("href")
        if not href or href.startswith("data:"):
            return
        sizes = link.get("sizes", "")
        size_value = parse_icon_size(sizes)
        media = link.get("media", "")
        type_attr = link.get("type", "")
        fmt = _detect_format(href, type_attr)
        media_priority = 0 if not media or "light" in media else 1
        candidates.append(
            {
                "url": urljoin(base_url, href),
                "size": size_value,
                "format": fmt,
                "format_rank": FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
                "base_priority": base_priority,
                "media_priority": media_priority,
                "type": rel_label,
            }
        )

    try:
        manifest_links = []
        for link in soup.find_all("link"):
            rel_val = link.get("rel")
            if not rel_val:
                continue
            tokens = [
                t.lower()
                for t in (
                    rel_val if isinstance(rel_val, list) else str(rel_val).split()
                )
            ]

            if any(t == "manifest" for t in tokens):
                manifest_links.append(link)

            if any(t in ("apple-touch-icon", "apple-touch-icon-precomposed") for t in tokens):
                _add_link_candidate(link, "apple-touch-icon", 2)
                continue

            if any((t == "icon") or t.endswith("icon") for t in tokens):
                if any(t == "mask-icon" for t in tokens):
                    _add_link_candidate(link, "mask-icon", 4)
                else:
                    _add_link_candidate(link, "link-icon", 0)

        for m_link in manifest_links:
            m_href = m_link.get("href")
            if m_href and not m_href.startswith("data:"):
                manifest_urls.append(urljoin(base_url, m_href))

        has_primary = any(
            c.get("type") in {"link-icon", "mask-icon", "apple-touch-icon"} for c in candidates
        )
        return candidates, manifest_urls, has_primary
    except Exception:
        logger.warning("Error while collecting link and manifest icons", exc_info=True)
        return candidates, manifest_urls, False


def _handle_manifests(manifest_urls: list[str], base_url: str, config, on_manifest_icons: Optional[Callable[[List[str]], None]], candidates: list[dict]):
    if not manifest_urls or config is None:
        return

    if on_manifest_icons is not None:
        def _fetch_all_manifests_and_emit():
            all_urls: List[str] = []

            def _fetch_one(m_url: str) -> List[str]:
                urls: List[str] = []
                try:
                    m_resp_local = http_request(m_url, config, allow_non_2xx=True)
                    if m_resp_local and getattr(m_resp_local, "ok", False):
                        try:
                            m_json = json.loads(m_resp_local.text)
                            icons = m_json.get("icons") or []
                            for icon in icons:
                                src = icon.get("src")
                                if not src:
                                    continue
                                i_url = urljoin(m_url, src)
                                urls.append(i_url)
                        except Exception:
                            logger.warning("Failed to parse manifest JSON from %s", m_url, exc_info=True)
                except Exception:
                    logger.warning("Failed to fetch manifest %s", m_url, exc_info=True)
                return urls

            if not manifest_urls:
                return

            try:
                try:
                    max_workers = int(getattr(app_config, "ICON_MANIFEST_MAX_WORKERS", 4) or 4)
                except Exception:
                    logger.debug("Failed to read ICON_MANIFEST_MAX_WORKERS from app_config; using default 4", exc_info=True)
                    max_workers = 4
                with ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="manifest-fetch") as executor:
                    futures = [executor.submit(_fetch_one, m_url) for m_url in manifest_urls]
                    for fut in as_completed(futures):
                        try:
                            urls = fut.result() or []
                            if urls:
                                all_urls.extend(urls)
                        except Exception:
                            logger.warning("Manifest fetch task raised an exception", exc_info=True)
            except Exception:
                logger.warning("Manifest executor failure", exc_info=True)

            if all_urls:
                try:
                    on_manifest_icons(all_urls)
                except Exception:
                    logger.warning("on_manifest_icons callback raised an exception", exc_info=True)

        _get_manifest_executor().submit(_fetch_all_manifests_and_emit)
        return

    # sync path: enrich candidates
    for m_url in manifest_urls:
        try:
            m_resp = http_request(m_url, config, allow_non_2xx=True)
            if m_resp and getattr(m_resp, "ok", False):
                try:
                    m_json = json.loads(m_resp.text)
                    icons = m_json.get("icons") or []
                    for icon in icons:
                        src = icon.get("src")
                        if not src:
                            continue
                        i_url = urljoin(m_url, src)
                        sizes = str(icon.get("sizes") or "").split()
                        type_attr = icon.get("type") or ""
                        fmt = _detect_format(i_url, type_attr)
                        if sizes:
                            for sz in sizes:
                                candidates.append(
                                    {
                                        "url": i_url,
                                        "size": parse_icon_size(sz),
                                        "format": fmt,
                                        "format_rank": FORMAT_RANK.get(
                                            fmt, FORMAT_RANK["unknown"]
                                        ),
                                        "base_priority": 1,
                                        "media_priority": 0,
                                        "type": "manifest",
                                    }
                                )
                        else:
                            candidates.append(
                                {
                                    "url": i_url,
                                    "size": 0,
                                    "format": fmt,
                                    "format_rank": FORMAT_RANK.get(
                                        fmt, FORMAT_RANK["unknown"]
                                    ),
                                    "base_priority": 1,
                                    "media_priority": 0,
                                    "type": "manifest",
                                }
                            )
                except Exception:
                    logger.warning("Failed to parse manifest JSON from %s (sync)", m_url, exc_info=True)
        except Exception:
            logger.warning("Failed to fetch manifest %s (sync)", m_url, exc_info=True)


def _add_fallback_paths(base_url: str, candidates: list[dict]):
    p = urlparse(base_url)
    host = p.netloc
    hosts = {host}
    if host.startswith("www."):
        hosts.add(host[4:])
    else:
        hosts.add("www." + host)

    fallback_paths = [
        "/favicon.ico",
        "/favicon.png",
        "/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png",
    ]
    for h in hosts:
        base = f"{p.scheme}://{h}"
        for path in fallback_paths:
            url = urljoin(base + "/", path.lstrip("/"))
            fmt = _detect_format(url, None)
            candidates.append(
                {
                    "url": url,
                    "size": 0,
                    "format": fmt,
                    "format_rank": FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
                    "base_priority": 1,
                    "media_priority": 0,
                    "type": "fallback",
                }
            )


def _add_external_services(base_url: str, use_external: bool, candidates: list[dict]):
    if not use_external:
        return
    p = urlparse(base_url)
    host = p.netloc
    google_url = f"https://www.google.com/s2/favicons?domain={host}&sz={TARGET_SIZE}"
    candidates.append(
        {
            "url": google_url,
            "size": TARGET_SIZE,
            "format": "png",
            "format_rank": FORMAT_RANK["png"],
            "base_priority": 10,
            "media_priority": 0,
            "type": "google_fallback",
        }
    )
    ddg_url = f"https://icons.duckduckgo.com/ip3/{host}.ico"
    candidates.append(
        {
            "url": ddg_url,
            "size": 0,
            "format": "ico",
            "format_rank": FORMAT_RANK["ico"],
            "base_priority": 10,
            "media_priority": 0,
            "type": "ddg_fallback",
        }
    )


def _append_og_image(soup: BeautifulSoup, base_url: str, candidates: list[dict]) -> list[str]:
    og_urls: List[str] = []
    # Append og:image only when there are no primary link-icons present.
    # Primary icons are those with base_priority == 0 (link-icon/mask/apple).
    if not any(c.get("base_priority", 9) == 0 for c in candidates):
        def _maybe_add_og(prop_name: str):
            meta = soup.find("meta", property=prop_name)
            if meta and meta.get("content"):
                og_content = meta.get("content") or ""
                og_url = urljoin(base_url, og_content)
                low = og_url.lower()
                banned_markers = [
                    "1200",
                    "1080",
                    "1024",
                    "800",
                    "630",
                    "600",
                    "banner",
                    "social",
                    "share",
                    "opengraph",
                    "og:",
                    ".svg",
                ]
                if not any(m in low for m in banned_markers):
                    if any(k in low for k in ["icon", "favicon"]):
                        og_urls.append(og_url)

        _maybe_add_og("og:image")
        _maybe_add_og("og:image:secure_url")
    return og_urls


def _sort_candidates(candidates: list[dict]):
    def sort_key(c: dict):
        size = c.get("size", 0)
        return (
            c.get("base_priority", 9),
            -c.get("format_rank", FORMAT_RANK["unknown"]),
            -size,
            c.get("media_priority", 0),
        )

    candidates.sort(key=sort_key)


def find_favicon_candidates(
    soup: BeautifulSoup,
    base_url: str,
    config=None,
    on_manifest_icons: Optional[Callable[[List[str]], None]] = None,
    use_external: bool = False,
) -> List[str]:
    candidates, manifest_urls, has_primary = _collect_link_icons(soup, base_url)
    if not has_primary:
        _handle_manifests(manifest_urls, base_url, config, on_manifest_icons, candidates)

    _add_fallback_paths(base_url, candidates)
    _add_external_services(base_url, use_external, candidates)

    _sort_candidates(candidates)

    logger.debug(f"Found {len(candidates)} icon candidates (before og:image):")
    for cand in candidates[:5]:
        logger.debug(
            f"  {cand['type']} {cand['size']}px {cand['format']} p{cand['base_priority']}/f{cand['format_rank']}: {cand['url']}"
        )
    if candidates:
        best = candidates[0]
        logger.info(
            f"Best candidate: {best['type']} {best['size']}px {best['format']} from {best['url']}"
        )

    og_urls = _append_og_image(soup, base_url, candidates)
    ordered_urls = [c["url"] for c in candidates] + og_urls
    seen = set()
    ordered_urls = [url for url in ordered_urls if not (url in seen or seen.add(url))]
    return ordered_urls


__all__ = [
    "find_favicon_candidates",
    "parse_icon_size",
    "FORMAT_RANK",
    "TARGET_SIZE",
    "shutdown_manifest_executor",
]
