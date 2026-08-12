"""High-level facade to fetch web link info (title + icon).

This implementation is self-contained and uses only modules within parser/.
Supports deferred icon loading for responsive UIs.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from PyQt6.QtCore import QRunnable

from app.controllers.ui.state.task_scheduler import TaskType, get_task_scheduler
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.path_service import icon_path_service

from .cache import read_cache, write_cache
from .constants import BS_PARSER, CACHE_TTL, SHORT_NEGATIVE_TTL, logger
from .domain import apply_jitter, base_domain
from .http_client import http_request
from .icon_downloader import pick_icon_parallel, save_icon
from .title_parser import get_provider_title_fast, get_title, get_title_for_blocked_status


_HOST_FAILURE_LOCK = threading.RLock()
_HOST_FAILURES: dict[str, float] = {}


def _sanitize_url(u: str) -> str:
    """Sanitize URL by removing view-source prefix and trailing question marks."""
    if not u:
        return u
    s = u.strip()
    # Keep only the first token when users paste extra trailing text after URL,
    # e.g. "https://example.com/ (".
    if any(ch.isspace() for ch in s):
        s = s.split()[0].strip()

    # Strip surrounding wrappers accidentally copied with URL.
    s = s.strip(" \t\r\n<>\"'")

    # Strip common trailing wrapper punctuation accidentally copied with URL.
    while s and s[-1] in ')]}>,"\'':
        s = s[:-1].rstrip()
    low = s.lower()
    prefix = "view-source:"
    if low.startswith(prefix):
        s = s[len(prefix) :].lstrip()
    # remove redundant trailing question marks like '???'
    while s.endswith("?"):
        s = s[:-1]
    # prepend https:// if scheme is missing
    try:
        parsed = urlparse(s)
        if not parsed.scheme:
            s = "https://" + s
            parsed = urlparse(s)
        # If URL still has no host, keep original string but without wrappers.
        if parsed.scheme in {"http", "https"} and not parsed.netloc:
            return s
    except Exception:
        pass
    return s


def _get_existing_icon_path(host: str) -> str | None:
    """Get path to existing domain icon if it exists."""
    if not host:
        return None
    cand = str(
        icon_path_service.get_user_icons_dir() / f"web_{host.replace('.', '_')}.png"
    )
    return cand if Path(cand).exists() else None


def _is_host_temporarily_unreachable(host: str) -> bool:
    normalized = str(host or "").strip().lower()
    if not normalized:
        return False
    now = time.time()
    with _HOST_FAILURE_LOCK:
        expires_at = _HOST_FAILURES.get(normalized)
        if expires_at is None:
            return False
        if expires_at <= now:
            _HOST_FAILURES.pop(normalized, None)
            return False
        return True


def _mark_host_temporarily_unreachable(host: str, *, ttl: float = SHORT_NEGATIVE_TTL) -> None:
    normalized = str(host or "").strip().lower()
    if not normalized:
        return
    with _HOST_FAILURE_LOCK:
        _HOST_FAILURES[normalized] = time.time() + max(1.0, float(ttl))


def _clear_host_temporary_failure(host: str) -> None:
    normalized = str(host or "").strip().lower()
    if not normalized:
        return
    with _HOST_FAILURE_LOCK:
        _HOST_FAILURES.pop(normalized, None)


def _build_negative_result(url: str, title: str, default_icon: str, config) -> dict[str, Any]:
    return {
        "url": url,
        "title": title,
        "icon": default_icon,
        "timestamp": time.time(),
        "ttl": apply_jitter(SHORT_NEGATIVE_TTL, config),
    }


def _should_mark_host_negative(
    *,
    soup: BeautifulSoup | None,
    html_status: int | None,
    host: str,
) -> bool:
    """Return True only for failures that plausibly indicate a host-wide outage.

    We must not poison the whole host after a path-specific 404, an anti-bot
    silent drop, or an opaque transport failure where we don't know what
    actually happened. Those cases should be retried on the next attempt.
    """
    if soup is not None or not host:
        return False
    if html_status is None:
        return False
    return html_status >= 500


def _fallback_title_from_url(url: str, host: str) -> str:
    try:
        p = urlparse(url)
        netloc = (p.netloc or host or "").strip().lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if netloc:
            return netloc
    except Exception:
        pass
    return host or ""


def _direct_favicon_candidates(url: str, host: str) -> list[str]:
    try:
        p = urlparse(url)
        scheme = p.scheme or "https"
        netloc = (p.netloc or "").strip()
    except Exception:
        scheme = "https"
        netloc = ""

    candidates: list[str] = []
    if netloc:
        candidates.append(f"{scheme}://{netloc}/favicon.ico")
    if host:
        candidates.append(f"{scheme}://{host}/favicon.ico")
        if host.startswith("www."):
            candidates.append(f"{scheme}://{host[4:]}/favicon.ico")
        else:
            candidates.append(f"{scheme}://www.{host}/favicon.ico")

    # De-duplicate preserving order
    out: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _try_direct_favicon_on_block(
    url: str,
    host: str,
    config,
    force_refresh: bool,
    cancel_event=None,
) -> str | None:
    if not host:
        return None
    for icon_url in _direct_favicon_candidates(url, host):
        _raise_if_cancelled(cancel_event)
        try:
            saved = save_icon(
                icon_url,
                host,
                config,
                is_fallback=True,
                force_refresh=force_refresh,
                cancel_event=cancel_event,
            )
            if saved:
                return saved
        except Exception:
            logger.debug("direct favicon fallback failed url=%s", icon_url, exc_info=True)
    try:
        try:
            soup = BeautifulSoup("", BS_PARSER)
        except Exception:
            soup = BeautifulSoup("", "html.parser")
        logger.debug("[fetch] direct favicon fallback exhausted, trying full icon pipeline for host=%s", host)
        return pick_icon_parallel(
            soup,
            url,
            host,
            config,
            force_refresh=force_refresh,
            cancel_event=cancel_event,
        )
    except Exception:
        logger.debug("full icon pipeline fallback failed for %s", url, exc_info=True)
    return None


def _create_blocked_icon_resolve_task(
    url: str,
    host: str,
    title: str,
    config,
    force_refresh: bool,
    on_icon_ready: Callable[[str], None] | None = None,
):
    """Create async task to resolve favicon for blocked pages via /favicon.ico."""

    def _resolve_blocked_icon_async() -> None:
        resolved = _try_direct_favicon_on_block(
            url,
            host,
            config,
            force_refresh,
        )
        if not resolved:
            return
        _update_cache_with_icon(url, title, resolved, config)
        if on_icon_ready:
            _notify_icon_ready(resolved, url, on_icon_ready)

    class BlockedIconResolveTask(QRunnable):
        def run(_self_nonlocal):  # type: ignore[no-redef]
            _resolve_blocked_icon_async()
            return

    return BlockedIconResolveTask()


def _check_cache(
    url: str, config, force_refresh: bool, existing_icon_path: str | None
) -> dict[str, Any] | None:
    """Check cache for existing entry."""
    if force_refresh:
        return None

    cached = read_cache(url, config)
    if not cached:
        return None

    # If cache has default icon but folder contains saved one — reuse it
    try:
        default_icon_path = (
            resolve_icon_for_link({"type": "web", "icon_path": ""}) or ""
        )
    except Exception:
        default_icon_path = ""

    cached_title = str(cached.get("title") or "").strip()
    cached_icon = str(cached.get("icon") or "").strip()
    url_host = ""
    try:
        url_host = base_domain(urlparse(url).netloc)
    except Exception:
        url_host = ""

    # Any cached entry without title is considered incomplete and must be retried.
    # Otherwise we can get "stuck" forever on empty titles due to cache hits.
    if not cached_title:
        logger.info("[cache] BYPASS_EMPTY_TITLE %s", url)
        return None

    # Weak cached entries (fallback title == host + default icon) should be retried.
    # This prevents "stuck forever on default icon" behavior.
    if (
        not existing_icon_path
        and cached_icon
        and default_icon_path
        and cached_icon == default_icon_path
        and url_host
        and cached_title.lower() == url_host.lower()
    ):
        logger.info("[cache] BYPASS_WEAK_DEFAULT_ICON %s", url)
        return None

    if (not cached.get("icon")) or (cached.get("icon") == default_icon_path):
        if existing_icon_path:
            cached = {**cached, "icon": existing_icon_path}

    return cached


def _fetch_and_parse_html(
    url: str, config, html_timeout, cancel_event=None
) -> tuple[BeautifulSoup | None, int | None]:
    """Fetch URL and parse HTML.
    
    OPTIMIZATION: Removed redundant HEAD request - if site is unreachable,
    the main GET will fail quickly with same timeout.
    """
    _raise_if_cancelled(cancel_event)
    resp = http_request(
        url,
        config,
        allow_non_2xx=True,
        timeout_override=html_timeout,
        retries=0,
        cancel_event=cancel_event,
        prefer_cloudscraper_primary=False,
    )
    if not resp:
        try:
            logger.debug("[fetch] http_request returned None for %s", url)
        except Exception:
            pass
        return None, None

    try:
        status_code = int(getattr(resp, "status_code", 0) or 0)
        if status_code >= 400:
            logger.info("[fetch] html_skip status=%s url=%s", status_code, url)
            return None, status_code

        _raise_if_cancelled(cancel_event)
        # Robust decode (avoid ISO-8859-1 defaults)
        enc = getattr(resp, "encoding", None)
        if not enc or str(enc).lower() == "iso-8859-1":
            try:
                # Attempt to detect encoding via charset-normalizer
                try:
                    from charset_normalizer import from_bytes  # type: ignore

                    best = from_bytes(resp.content).best()
                    if best is not None:
                        txt = str(best)
                    else:
                        txt = resp.content.decode(
                            getattr(resp, "apparent_encoding", None) or "utf-8",
                            errors="replace",
                        )
                except Exception:
                    txt = resp.content.decode(
                        getattr(resp, "apparent_encoding", None) or "utf-8",
                        errors="replace",
                    )
            except Exception:
                txt = resp.text
        else:
            txt = resp.text

        # Create soup safely with fallback parser
        try:
            return BeautifulSoup(txt, BS_PARSER), status_code
        except Exception:
            return BeautifulSoup(txt, "html.parser"), status_code
    except Exception as e:
        logger.debug("bs4 parse failed for %s: %s", url, e)
        return None, None


def _raise_if_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError()


def _resolve_icon_sync(
    soup: BeautifulSoup | None,
    url: str,
    host: str,
    config,
    force_refresh: bool,
    existing_icon_path: str | None,
    cancel_event=None,
) -> str | None:
    """Resolve icon synchronously."""
    _raise_if_cancelled(cancel_event)
    try:
        logger.debug("[fetch] picking icon sync for host=%s", host)
        soup_for_icon = soup or BeautifulSoup("", BS_PARSER)

        # If a domain icon already exists — reuse it and skip download
        if existing_icon_path:
            return existing_icon_path

        return pick_icon_parallel(
            soup_for_icon,
            url,
            host,
            config,
            force_refresh=force_refresh,
            cancel_event=cancel_event,
        )
    except Exception as e:
        logger.debug("pick_icon failed for %s: %s", url, e)
        return None


def _refetch_html_for_icon(url: str, config, cancel_event=None) -> BeautifulSoup | None:
    """Re-fetch HTML specifically for icon resolution."""
    icon_html_timeout = getattr(
        config, "ICON_HTML_TIMEOUT", getattr(config, "HTML_FETCH_TIMEOUT", None)
    )
    try:
        host = base_domain(urlparse(url).netloc)
    except Exception:
        host = ""
    if host and _is_host_temporarily_unreachable(host):
        return None
    _raise_if_cancelled(cancel_event)
    resp = http_request(
        url,
        config,
        timeout_override=icon_html_timeout,
        retries=0,
        cancel_event=cancel_event,
        prefer_cloudscraper_primary=False,
    )
    if not resp:
        _mark_host_temporarily_unreachable(host)
        return None

    try:
        _clear_host_temporary_failure(host)
        _raise_if_cancelled(cancel_event)
        enc = getattr(resp, "encoding", None)
        if not enc or str(enc).lower() == "iso-8859-1":
            try:
                txt = resp.content.decode(
                    getattr(resp, "apparent_encoding", None) or "utf-8",
                    errors="replace",
                )
            except Exception:
                txt = resp.text
        else:
            txt = resp.text
        return BeautifulSoup(txt, BS_PARSER)
    except Exception:
        return None


def _update_cache_with_icon(url: str, title: str, icon_path: str, config) -> None:
    """Update cache with resolved icon."""
    try:
        current = {
            "url": url,
            "title": title,
            "icon": icon_path,
            "timestamp": __import__("time").time(),
            "ttl": apply_jitter(CACHE_TTL, config),
        }
        write_cache(url, current, config)
    except Exception as ex:
        logger.debug("cache write (async) failed for %s: %s", url, ex)


def _notify_icon_ready(
    icon_path: str, url: str, on_icon_ready: Callable[[str], None]
) -> None:
    """Notify UI that icon is ready via TaskScheduler."""
    try:
        sched = get_task_scheduler()
        sched.schedule_operation(
            lambda: on_icon_ready(icon_path),
            task_type=TaskType.TABLE_UPDATE,
            delay=0,
            operation_id=f"icon_ready:{url}",
        )
    except Exception as ex:
        logger.debug("on_icon_ready scheduling failed for %s: %s", url, ex)


def _create_icon_resolve_task(
    soup: BeautifulSoup | None,
    url: str,
    title: str,
    config,
    on_icon_ready: Callable[[str], None] | None,
):
    """Create async icon resolve task."""

    def _resolve_icon_async(html_soup: BeautifulSoup | None) -> None:
        try:
            host = base_domain(urlparse(url).netloc)
        except Exception:
            host = ""
        if host and _is_host_temporarily_unreachable(host):
            return
        # Re-fetch HTML if soup is missing
        if html_soup is None:
            html_soup = _refetch_html_for_icon(url, config)

        if html_soup is None:
            return

        # Resolve icon
        resolved = None
        try:
            resolved = pick_icon_parallel(
                html_soup, url, host, config, force_refresh=False
            )
        except Exception as ex:
            logger.debug("pick_icon (async) failed for %s: %s", url, ex)

        if not resolved:
            return

        # Update cache
        _update_cache_with_icon(url, title, resolved, config)

        # Notify UI
        if on_icon_ready:
            _notify_icon_ready(resolved, url, on_icon_ready)

    class IconResolveTask(QRunnable):
        def run(_self_nonlocal):  # type: ignore[no-redef]
            _resolve_icon_async(soup)
            return

    return IconResolveTask()


def fetch_web_link_info(
    url: str,
    config,
    force_refresh: bool = False,
    *,
    defer_icon: bool = False,
    on_icon_ready: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Fetch web link information (title, icon) with caching."""
    perf_t0 = time.perf_counter()
    cache_check_ms = 0.0
    fetch_html_ms = 0.0
    title_ms = 0.0
    icon_ms = 0.0
    cache_write_ms = 0.0
    result_source = "unknown"
    host_negative = False
    blocked_status: int | None = None
    deferred_icon_scheduled = False

    _raise_if_cancelled(cancel_event)
    # 1) Sanitize URL and get host
    url = _sanitize_url(url)
    try:
        host = base_domain(urlparse(url).netloc)
    except Exception:
        host = ""

    existing_icon_path = _get_existing_icon_path(host)

    # 2) Check cache
    t_cache0 = time.perf_counter()
    cached = _check_cache(url, config, force_refresh, existing_icon_path)
    cache_check_ms = (time.perf_counter() - t_cache0) * 1000.0
    if cached:
        result_source = "cache"
        logger.info(
            "[Perf] fetch_web_link_info url=%s source=%s total=%.2f ms cache_check=%.2f ms",
            url,
            result_source,
            (time.perf_counter() - perf_t0) * 1000.0,
            cache_check_ms,
        )
        return cached

    try:
        default_icon = resolve_icon_for_link({"type": "web", "icon_path": ""}) or ""
    except Exception:
        default_icon = ""

    # Fast provider path (YouTube/Vimeo oEmbed, etc.) to avoid heavy HTML fetch.
    fast_provider_title = ""
    try:
        t_fast_title0 = time.perf_counter()
        fast_provider_title = get_provider_title_fast(url, config) or ""
        if fast_provider_title:
            title_ms += (time.perf_counter() - t_fast_title0) * 1000.0
    except Exception:
        fast_provider_title = ""

    if (
        not force_refresh
        and host
        and not existing_icon_path
        and _is_host_temporarily_unreachable(host)
    ):
        host_negative = True
        logger.info("[fetch][host_negative] hit host=%s url=%s", host, url)
        result = _build_negative_result(url, "", default_icon, config)
        t_cache_write0 = time.perf_counter()
        try:
            write_cache(url, result, config)
        except Exception:
            logger.debug("cache write failed for host-negative %s", url, exc_info=True)
        cache_write_ms += (time.perf_counter() - t_cache_write0) * 1000.0
        result_source = "host_negative"
        logger.info(
            "[Perf] fetch_web_link_info url=%s source=%s total=%.2f ms cache_check=%.2f ms cache_write=%.2f ms host_negative=%s",
            url,
            result_source,
            (time.perf_counter() - perf_t0) * 1000.0,
            cache_check_ms,
            cache_write_ms,
            host_negative,
        )
        return result

    _raise_if_cancelled(cancel_event)

    # 2.5) If provider title is already known, return quickly and resolve icon cheaply.
    if fast_provider_title:
        icon_path = existing_icon_path
        if not icon_path and not defer_icon:
            t_icon0 = time.perf_counter()
            icon_path = _try_direct_favicon_on_block(
                url,
                host,
                config,
                force_refresh,
                cancel_event=cancel_event,
            )
            icon_ms = (time.perf_counter() - t_icon0) * 1000.0

        result = {
            "url": url,
            "title": fast_provider_title,
            "icon": icon_path or default_icon,
            "timestamp": __import__("time").time(),
            "ttl": apply_jitter(CACHE_TTL, config),
        }

        t_cache_write0 = time.perf_counter()
        try:
            write_cache(url, result, config)
        except Exception as e:
            logger.debug("cache write failed for %s: %s", url, e)
        cache_write_ms += (time.perf_counter() - t_cache_write0) * 1000.0

        if defer_icon and icon_path is None and not existing_icon_path:
            scheduler = get_task_scheduler()
            task = _create_blocked_icon_resolve_task(
                url,
                host,
                fast_provider_title,
                config,
                force_refresh,
                on_icon_ready,
            )
            scheduler.submit_task(task)
            deferred_icon_scheduled = True

        result_source = "provider_title_deferred_icon" if defer_icon else "provider_title_icon"
        logger.info(
            "[Perf] fetch_web_link_info url=%s source=%s total=%.2f ms cache_check=%.2f ms title=%.2f ms icon=%.2f ms cache_write=%.2f ms defer_icon=%s deferred_icon_scheduled=%s",
            url,
            result_source,
            (time.perf_counter() - perf_t0) * 1000.0,
            cache_check_ms,
            title_ms,
            icon_ms,
            cache_write_ms,
            defer_icon,
            deferred_icon_scheduled,
        )
        return result

    # 3) Fetch and parse HTML
    html_timeout = getattr(config, "HTML_FETCH_TIMEOUT", None)
    try:
        logger.debug(
            "[fetch] start url=%s force=%s defer_icon=%s html_timeout=%s",
            url,
            force_refresh,
            defer_icon,
            html_timeout,
        )
    except Exception:
        pass

    t_fetch0 = time.perf_counter()
    fetch_result = _fetch_and_parse_html(
        url, config, html_timeout, cancel_event=cancel_event
    )
    if (
        isinstance(fetch_result, tuple)
        and len(fetch_result) == 2
    ):
        soup, html_status = fetch_result
    else:
        # Backward compatibility for tests/mocks that return only soup/None.
        soup, html_status = fetch_result, None
    if html_status in (403, 429):
        blocked_status = html_status
    fetch_html_ms = (time.perf_counter() - t_fetch0) * 1000.0
    if soup is None:
        if blocked_status in (403, 429):
            logger.info(
                "[fetch][host_negative] skip_mark_blocked host=%s status=%s url=%s",
                host,
                blocked_status,
                url,
            )
            _clear_host_temporary_failure(host)
        elif _should_mark_host_negative(
            soup=soup,
            html_status=html_status,
            host=host,
        ):
            logger.info(
                "[fetch][host_negative] mark host=%s status=%s url=%s",
                host,
                html_status,
                url,
            )
            _mark_host_temporarily_unreachable(host)
        else:
            logger.info(
                "[fetch][host_negative] skip_mark_unknown host=%s status=%s url=%s",
                host,
                html_status,
                url,
            )
            _clear_host_temporary_failure(host)
    else:
        logger.debug("[fetch][host_negative] clear host=%s url=%s", host, url)
        _clear_host_temporary_failure(host)
    _raise_if_cancelled(cancel_event)

    # 4) Extract title (skip if site is unreachable)
    if soup is None:
        # For blocked pages (403/429), keep a stable fallback title from URL.
        if blocked_status in (403, 429):
            title = get_title_for_blocked_status(
                url,
                config,
                _fallback_title_from_url(url, host),
            )
        else:
            # Site is unreachable — keep stable fallback title from URL/host.
            title = _fallback_title_from_url(url, host)
    else:
        t_title0 = time.perf_counter()
        title = get_title(url, config, soup)
        title_ms = (time.perf_counter() - t_title0) * 1000.0
    try:
        logger.debug("[fetch] title='%s' for %s", title, url)
    except Exception:
        pass

    _raise_if_cancelled(cancel_event)

    # 5) Resolve icon (sync or deferred)
    icon_path = None
    if not defer_icon:
        t_icon0 = time.perf_counter()
        if soup is None:
            icon_path = _try_direct_favicon_on_block(
                url,
                host,
                config,
                force_refresh,
                cancel_event=cancel_event,
            )
        else:
            icon_path = _resolve_icon_sync(
                soup,
                url,
                host,
                config,
                force_refresh,
                existing_icon_path,
                cancel_event=cancel_event,
            )
        icon_ms = (time.perf_counter() - t_icon0) * 1000.0

    # 6) Fallback to existing icon if resolution failed
    if icon_path is None and existing_icon_path:
        icon_path = existing_icon_path

    # 7) Build result with default icon fallback
    result = {
        "url": url,
        "title": title,
        "icon": icon_path or default_icon,
        "timestamp": __import__("time").time(),
        "ttl": apply_jitter(
            SHORT_NEGATIVE_TTL if soup is None and icon_path is None else CACHE_TTL,
            config,
        ),
    }

    try:
        logger.debug(
            "[fetch] icon=%s for host=%s",
            "custom" if icon_path else "default",
            host,
        )
    except Exception:
        pass

    # 8) Write to cache
    t_cache_write0 = time.perf_counter()
    try:
        write_cache(url, result, config)
    except Exception as e:
        logger.debug("cache write failed for %s: %s", url, e)
    cache_write_ms += (time.perf_counter() - t_cache_write0) * 1000.0

    # 9) Schedule deferred icon resolution if needed
    if defer_icon and soup is not None and (icon_path is None):
        scheduler = get_task_scheduler()
        task = _create_icon_resolve_task(soup, url, title, config, on_icon_ready)
        scheduler.submit_task(task)
        deferred_icon_scheduled = True
    elif defer_icon and soup is None and icon_path is None and not existing_icon_path:
        scheduler = get_task_scheduler()
        task = _create_blocked_icon_resolve_task(
            url,
            host,
            title,
            config,
            force_refresh,
            on_icon_ready,
        )
        scheduler.submit_task(task)
        deferred_icon_scheduled = True

    if soup is None and blocked_status in (403, 429):
        result_source = f"html_blocked_{blocked_status}"
    elif soup is None:
        result_source = "html_unreachable"
    elif defer_icon:
        result_source = "html_title_deferred_icon"
    elif icon_path:
        result_source = "html_title_icon"
    else:
        result_source = "html_title_default_icon"

    logger.info(
        "[Perf] fetch_web_link_info url=%s source=%s total=%.2f ms cache_check=%.2f ms fetch_html=%.2f ms title=%.2f ms icon=%.2f ms cache_write=%.2f ms defer_icon=%s deferred_icon_scheduled=%s host_negative=%s",
        url,
        result_source,
        (time.perf_counter() - perf_t0) * 1000.0,
        cache_check_ms,
        fetch_html_ms,
        title_ms,
        icon_ms,
        cache_write_ms,
        defer_icon,
        deferred_icon_scheduled,
        host_negative,
    )

    return result


__all__ = ["fetch_web_link_info"]
