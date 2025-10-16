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

import atexit
import json
import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.config_data import app_config

from .constants import FORMAT_RANK, TARGET_SIZE, logger
from .http_client import http_request

_MANIFEST_EXECUTOR = None
_MANIFEST_EXECUTOR_GUARD = threading.Lock()
_MANIFEST_ATEXIT_HANDLER = (
    None  # stores the registered atexit handler to support unregister
)


@dataclass(slots=True)
class IconCandidate:
    url: str
    size: int
    format: str
    format_rank: int
    base_priority: int
    media_priority: int
    kind: str


# Markers that make og:image likely unsuitable for favicon usage
OG_IMAGE_BANNED_MARKERS = [
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

# Precompiled regex for sizes like "16x16 32x32"
SIZE_RE = re.compile(r"(\d+)\s*x\s*(\d+)")
# Precompiled regex for first integer fallback
FIRST_INT_RE = re.compile(r"(\d+)")


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
                max_workers = int(
                    getattr(app_config, "ICON_MANIFEST_MAX_WORKERS", 4) or 4
                )
            except (TypeError, ValueError):
                logger.debug(
                    "Failed to read ICON_MANIFEST_MAX_WORKERS from app_config; using default 4",
                    exc_info=True,
                )
                max_workers = 4
            _MANIFEST_EXECUTOR = ThreadPoolExecutor(
                max_workers=max(1, max_workers), thread_name_prefix="manifest"
            )
            try:
                # Remove previously registered handler if any (in case of recreation)
                global _MANIFEST_ATEXIT_HANDLER
                if _MANIFEST_ATEXIT_HANDLER is not None:
                    try:
                        atexit.unregister(_MANIFEST_ATEXIT_HANDLER)
                    except Exception:
                        logger.debug(
                            "Failed to unregister previous atexit handler for manifest executor",
                            exc_info=True,
                        )
                    finally:
                        _MANIFEST_ATEXIT_HANDLER = None

                # Capture the current executor instance to avoid referencing None after manual shutdown
                def _manifest_shutdown_handler(
                    e: ThreadPoolExecutor | None = _MANIFEST_EXECUTOR,
                ) -> None:
                    if e is not None:
                        e.shutdown(wait=False, cancel_futures=True)

                _MANIFEST_ATEXIT_HANDLER = atexit.register(_manifest_shutdown_handler)
            except Exception:
                logger.debug(
                    "Failed to register atexit shutdown for manifest executor",
                    exc_info=True,
                )
    return _MANIFEST_EXECUTOR


def shutdown_manifest_executor(wait: bool = False, cancel_futures: bool = True) -> bool:
    """Explicitly shutdown the global manifest executor.

    Useful in tests or controlled environments to ensure clean teardown between
    runs. Returns True if an executor existed and was shut down, False if there
    was nothing to do. A future call to `_get_manifest_executor()` will lazily
    recreate the pool on demand.
    """
    global _MANIFEST_EXECUTOR, _MANIFEST_ATEXIT_HANDLER
    with _MANIFEST_EXECUTOR_GUARD:
        if _MANIFEST_EXECUTOR is None:
            return False
        try:
            _MANIFEST_EXECUTOR.shutdown(wait=wait, cancel_futures=cancel_futures)
        finally:
            _MANIFEST_EXECUTOR = None
            # Ensure atexit handler is removed to avoid accumulation on recreation
            if _MANIFEST_ATEXIT_HANDLER is not None:
                try:
                    atexit.unregister(_MANIFEST_ATEXIT_HANDLER)
                except Exception:
                    logger.debug(
                        "Failed to unregister atexit handler during shutdown",
                        exc_info=True,
                    )
                finally:
                    _MANIFEST_ATEXIT_HANDLER = None
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
    pairs = SIZE_RE.findall(s)
    if pairs:
        max_size = 0
        for w, h in pairs:
            try:
                int_w = int(w)
                int_h = int(h)
                if int_w > max_size:
                    max_size = int_w
                if int_h > max_size:
                    max_size = int_h
            except ValueError:
                logger.debug(
                    "Invalid WxH pair in sizes attribute: %sx%s", w, h, exc_info=True
                )
                continue
        if max_size:
            return max_size
    # Fallback: take first integer if present (non-standard values)
    m = FIRST_INT_RE.search(s)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            logger.debug("Failed to parse integer from sizes attribute", exc_info=True)
    logger.debug("Invalid sizes attribute: %s", sizes_attr)
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


def _collect_link_icons(
    soup: BeautifulSoup, base_url: str
) -> tuple[list[IconCandidate], list[str], bool]:
    """Collects candidates from <link> elements and manifest references.

    Arguments:
    - soup: BeautifulSoup parsed document.
    - base_url: base URL for resolving relative paths.

    Returns:
    - tuple: (candidates, manifest_urls, has_primary), where
      candidates — list of IconCandidate objects,
      manifest_urls — manifest links,
      has_primary — whether primary link-icons are present.
    """
    candidates: list[IconCandidate] = []
    manifest_urls: list[str] = []

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
            IconCandidate(
                url=urljoin(base_url, href),
                size=size_value,
                format=fmt,
                format_rank=FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
                base_priority=base_priority,
                media_priority=media_priority,
                kind=rel_label,
            )
        )

    try:
        manifest_links = []
        for link in soup.find_all("link"):
            rel_val = link.get("rel")
            if not rel_val:
                continue
            tokens = {
                t.lower()
                for t in (
                    rel_val if isinstance(rel_val, list) else str(rel_val).split()
                )
            }

            has_manifest = "manifest" in tokens
            has_apple = ("apple-touch-icon" in tokens) or (
                "apple-touch-icon-precomposed" in tokens
            )
            # Keep one pass for suffix check (covers e.g. mask-icon, any *icon tokens)
            has_icon = ("icon" in tokens) or any(t.endswith("icon") for t in tokens)
            has_mask = "mask-icon" in tokens

            if has_manifest:
                manifest_links.append(link)

            if has_apple:
                _add_link_candidate(link, "apple-touch-icon", 2)
                continue

            if has_icon:
                if has_mask:
                    _add_link_candidate(link, "mask-icon", 4)
                else:
                    _add_link_candidate(link, "link-icon", 0)

        for m_link in manifest_links:
            m_href = m_link.get("href")
            if m_href and not m_href.startswith("data:"):
                manifest_urls.append(urljoin(base_url, m_href))

        has_primary = any(
            c.kind in {"link-icon", "mask-icon", "apple-touch-icon"} for c in candidates
        )
        return candidates, manifest_urls, has_primary
    except (AttributeError, TypeError, ValueError):
        logger.warning("Error while collecting link and manifest icons", exc_info=True)
        return candidates, manifest_urls, False


def _handle_manifests(
    manifest_urls: list[str],
    base_url: str,
    config,
    on_manifest_icons: Callable[[list[str]], None] | None,
    candidates: list[IconCandidate],
):
    """Processes manifests: asynchronously invokes callback or synchronously enriches candidates.

    Arguments:
    - manifest_urls: list of manifest URLs.
    - base_url: base URL for resolving relative paths.
    - config: HTTP client configuration.
    - on_manifest_icons: Callable[[list[str]], None] | None — if provided, will be called with icon URLs;
      otherwise, icons from manifests are added to candidates synchronously.
    - candidates: collection that can be extended.
    """
    # Разрешаем обработку манифестов даже если config не передан: http_request
    # корректно работает с None, подставляя значения по умолчанию из constants.
    if not manifest_urls:
        return

    # Deduplicate while preserving order to avoid duplicate network requests
    try:
        manifest_urls = list(dict.fromkeys(manifest_urls))
    except Exception:
        # Fallback in case of unexpected types; better to proceed than fail
        manifest_urls = list(manifest_urls)

    if on_manifest_icons is not None:

        def _fetch_all_manifests_and_emit():
            all_urls: list[str] = []

            def _fetch_one(m_url: str) -> list[str]:
                urls: list[str] = []
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
                        except json.JSONDecodeError:
                            logger.warning(
                                "Failed to parse manifest JSON from %s",
                                m_url,
                                exc_info=True,
                            )
                except Exception:
                    logger.warning("Failed to fetch manifest %s", m_url, exc_info=True)
                return urls

            if not manifest_urls:
                return

            try:
                # Reuse the global manifest executor for per-URL fetches.
                executor = _get_manifest_executor()
                futures = [
                    executor.submit(_fetch_one, m_url) for m_url in manifest_urls
                ]
                # Collect results sequentially to support dummy futures used in tests
                for fut in futures:
                    try:
                        urls = fut.result() or []
                        if urls:
                            all_urls.extend(urls)
                    except Exception:
                        logger.warning(
                            "Manifest fetch task raised an exception", exc_info=True
                        )
            except Exception:
                logger.warning("Manifest executor failure", exc_info=True)

            if all_urls:
                # Deduplicate while preserving order before invoking callback
                try:
                    all_urls = list(dict.fromkeys(all_urls))
                except Exception:
                    # If something unexpected happens, fall back to a best-effort unique list
                    seen = set()
                    tmp = []
                    for u in all_urls:
                        if u not in seen:
                            seen.add(u)
                            tmp.append(u)
                    all_urls = tmp
                try:
                    on_manifest_icons(all_urls)
                except Exception:
                    logger.warning(
                        "on_manifest_icons callback raised an exception", exc_info=True
                    )

        # Run the coordinator in a separate thread, not via the executor,
        # so that only per-URL fetches are submitted to the global pool.
        # In tests, threading.Thread can be monkeypatched to run synchronously.
        threading.Thread(
            target=_fetch_all_manifests_and_emit,
            name="manifest-coordinator",
            daemon=True,
        ).start()
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
                                    IconCandidate(
                                        url=i_url,
                                        size=parse_icon_size(sz),
                                        format=fmt,
                                        format_rank=FORMAT_RANK.get(
                                            fmt, FORMAT_RANK["unknown"]
                                        ),
                                        base_priority=1,
                                        media_priority=0,
                                        kind="manifest",
                                    )
                                )
                        else:
                            candidates.append(
                                IconCandidate(
                                    url=i_url,
                                    size=0,
                                    format=fmt,
                                    format_rank=FORMAT_RANK.get(
                                        fmt, FORMAT_RANK["unknown"]
                                    ),
                                    base_priority=1,
                                    media_priority=0,
                                    kind="manifest",
                                )
                            )
                except json.JSONDecodeError:
                    logger.warning(
                        "Failed to parse manifest JSON from %s (sync)",
                        m_url,
                        exc_info=True,
                    )
        except Exception:
            logger.warning("Failed to fetch manifest %s (sync)", m_url, exc_info=True)


def _add_fallback_paths(base_url: str, candidates: list[IconCandidate]):
    """Adds standard fallback paths (favicon.ico, etc.) for main and www-hosts.

    Features: generates host variants with/without www. prefix and adds
    candidates with zero size and computed format.
    """
    p = urlparse(base_url)
    host = p.netloc
    hosts = {host}
    # Hosts for fallback:
    # - If starts with www., add base host without www.
    # - If it's a likely root domain (exactly one dot), add www.<host>.
    # - If explicit subdomain (>=2 dots and doesn't start with www.), DO NOT add www.<host> to avoid noisy 404s.
    if host.startswith("www."):
        hosts.add(host[4:])
    else:
        if host.count(".") == 1:
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
                IconCandidate(
                    url=url,
                    size=0,
                    format=fmt,
                    format_rank=FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
                    base_priority=1,
                    media_priority=0,
                    kind="fallback",
                )
            )


def _add_external_services(
    base_url: str, use_external: bool, candidates: list[IconCandidate]
):
    """Adds external fallback services (Google, DuckDuckGo) if allowed.

    Arguments:
    - base_url: page URL, used only for host extraction.
    - use_external: flag enabling external services.
    - candidates: list of candidates to extend.
    """
    if not use_external:
        return
    p = urlparse(base_url)
    host = p.netloc
    google_url = f"https://www.google.com/s2/favicons?domain={host}&sz={TARGET_SIZE}"
    candidates.append(
        IconCandidate(
            url=google_url,
            size=TARGET_SIZE,
            format="png",
            format_rank=FORMAT_RANK["png"],
            base_priority=10,
            media_priority=0,
            kind="google_fallback",
        )
    )
    ddg_url = f"https://icons.duckduckgo.com/ip3/{host}.ico"
    candidates.append(
        IconCandidate(
            url=ddg_url,
            size=0,
            format="ico",
            format_rank=FORMAT_RANK["ico"],
            base_priority=10,
            media_priority=0,
            kind="ddg_fallback",
        )
    )


def _append_og_image(
    soup: BeautifulSoup, base_url: str, candidates: list[IconCandidate]
) -> list[str]:
    """Returns URLs from og:image if no primary link-icons are present and URL looks like an icon.

    Filters by banned markers (OG_IMAGE_BANNED_MARKERS) and keywords
    (icon/favicon). Returns list of suitable URLs.
    """
    og_urls: list[str] = []
    # Append og:image only when there are no primary link-icons present.
    # Primary icons are those with base_priority == 0 (link-icon/mask/apple).
    if not any(getattr(c, "base_priority", 9) == 0 for c in candidates):
        # Control filtering strictness via config. Default to strict mode.
        try:
            strict = bool(getattr(app_config, "ICONS_OG_IMAGE_STRICT", True))
        except Exception:
            strict = True

        def _maybe_add_og(prop_name: str):
            meta = soup.find("meta", property=prop_name)
            if meta and meta.get("content"):
                og_content = meta.get("content") or ""
                og_url = urljoin(base_url, og_content)
                low = og_url.lower()
                if not any(m in low for m in OG_IMAGE_BANNED_MARKERS):
                    # In strict mode, require keywords; in soft mode, absence of banned markers is sufficient.
                    if (not strict) or any(k in low for k in ["icon", "favicon"]):
                        og_urls.append(og_url)

        _maybe_add_og("og:image")
        _maybe_add_og("og:image:secure_url")
    return og_urls


def _sort_candidates(candidates: list[IconCandidate]):
    """Sorts candidates by priorities: base_priority, format_rank, size, media_priority."""

    def sort_key(c: IconCandidate):
        size = getattr(c, "size", 0)
        return (
            getattr(c, "base_priority", 9),
            -getattr(c, "format_rank", FORMAT_RANK["unknown"]),
            -size,
            getattr(c, "media_priority", 0),
        )

    candidates.sort(key=sort_key)


def find_favicon_candidates(
    soup: BeautifulSoup,
    base_url: str,
    config=None,
    on_manifest_icons: Callable[[list[str]], None] | None = None,
    use_external: bool = False,
) -> list[str]:
   
    candidates, manifest_urls, has_primary = _collect_link_icons(soup, base_url)
    _handle_manifests(manifest_urls, base_url, config, on_manifest_icons, candidates)

    _add_fallback_paths(base_url, candidates)
    _add_external_services(base_url, use_external, candidates)

    _sort_candidates(candidates)

    logger.debug("Found %s icon candidates (before og:image):", len(candidates))
    for cand in candidates[:5]:
        logger.debug(
            "  %s %spx %s p%s/f%s: %s",
            cand.kind,
            cand.size,
            cand.format,
            cand.base_priority,
            cand.format_rank,
            cand.url,
        )
    if candidates:
        best = candidates[0]
        logger.info(
            "Best candidate: %s %spx %s from %s",
            best.kind,
            best.size,
            best.format,
            best.url,
        )

    og_urls = _append_og_image(soup, base_url, candidates)
    ordered_urls = [c.url for c in candidates] + og_urls
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
