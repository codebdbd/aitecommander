"""High-level facade to fetch web link info (title + icon).

This implementation is self-contained and uses only modules within parser/.
Supports deferred icon loading for responsive UIs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from PyQt6.QtCore import QRunnable

from app.controllers.ui.state.task_scheduler import TaskType, get_task_scheduler
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.ui.icon.path_service import icon_path_service

from .cache import read_cache, write_cache
from .constants import BS_PARSER, CACHE_TTL, logger
from .domain import apply_jitter, base_domain
from .http_client import http_request
from .icon_downloader import pick_icon_parallel
from .title_parser import get_title


def _sanitize_url(u: str) -> str:
    """Sanitize URL by removing view-source prefix and trailing question marks."""
    if not u:
        return u
    s = u.strip()
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


def _check_cache(url: str, config, force_refresh: bool, existing_icon_path: str | None) -> dict[str, Any] | None:
    """Check cache for existing entry."""
    if force_refresh:
        return None
    
    cached = read_cache(url, config)
    if not cached:
        return None
    
    # If cache has default icon but folder contains saved one — reuse it
    try:
        default_icon_path = resolve_icon_for_link({"type": "web", "icon_path": ""}) or ""
    except Exception:
        default_icon_path = ""
    
    if (not cached.get("icon")) or (cached.get("icon") == default_icon_path):
        if existing_icon_path:
            cached = {**cached, "icon": existing_icon_path}
    
    return cached


def _fetch_and_parse_html(url: str, config, html_timeout) -> BeautifulSoup | None:
    """Fetch URL and parse HTML."""
    resp = http_request(url, config, timeout_override=html_timeout)
    if not resp:
        try:
            logger.debug("[fetch] http_request returned None for %s", url)
        except Exception:
            pass
        return None
    
    try:
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
            return BeautifulSoup(txt, BS_PARSER)
        except Exception:
            return BeautifulSoup(txt, "html.parser")
    except Exception as e:
        logger.debug("bs4 parse failed for %s: %s", url, e)
        return None


def _resolve_icon_sync(soup: BeautifulSoup | None, url: str, host: str, config, force_refresh: bool, existing_icon_path: str | None) -> str | None:
    """Resolve icon synchronously."""
    try:
        logger.debug("[fetch] picking icon sync for host=%s", host)
        soup_for_icon = soup or BeautifulSoup("", BS_PARSER)
        
        # If a domain icon already exists — reuse it and skip download
        if existing_icon_path:
            return existing_icon_path
        
        return pick_icon_parallel(soup_for_icon, url, host, config, force_refresh=force_refresh)
    except Exception as e:
        logger.debug("pick_icon failed for %s: %s", url, e)
        return None


def _refetch_html_for_icon(url: str, config) -> BeautifulSoup | None:
    """Re-fetch HTML specifically for icon resolution."""
    icon_html_timeout = getattr(
        config, "ICON_HTML_TIMEOUT", getattr(config, "HTML_FETCH_TIMEOUT", None)
    )
    resp = http_request(url, config, timeout_override=icon_html_timeout)
    if not resp:
        return None
    
    try:
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


def _notify_icon_ready(icon_path: str, url: str, on_icon_ready: Callable[[str], None]) -> None:
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


def _create_icon_resolve_task(soup: BeautifulSoup | None, url: str, title: str, config, on_icon_ready: Callable[[str], None] | None):
    """Create async icon resolve task."""
    def _resolve_icon_async(html_soup: BeautifulSoup | None) -> None:
        # Re-fetch HTML if soup is missing
        if html_soup is None:
            html_soup = _refetch_html_for_icon(url, config)
        
        if html_soup is None:
            return
        
        # Resolve icon
        resolved = None
        try:
            host = base_domain(urlparse(url).netloc)
            resolved = pick_icon_parallel(html_soup, url, host, config, force_refresh=False)
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
) -> dict[str, Any]:
    """Fetch web link information (title, icon) with caching."""
    # 1) Sanitize URL and get host
    url = _sanitize_url(url)
    try:
        host = base_domain(urlparse(url).netloc)
    except Exception:
        host = ""
    
    existing_icon_path = _get_existing_icon_path(host)
    
    # 2) Check cache
    cached = _check_cache(url, config, force_refresh, existing_icon_path)
    if cached:
        return cached
    
    # 3) Fetch and parse HTML
    html_timeout = getattr(config, "HTML_FETCH_TIMEOUT", None)
    try:
        logger.debug(
            "[fetch] start url=%s force=%s defer_icon=%s html_timeout=%s",
            url, force_refresh, defer_icon, html_timeout,
        )
    except Exception:
        pass
    
    soup = _fetch_and_parse_html(url, config, html_timeout)
    
    # 4) Extract title
    title = get_title(url, config, soup)
    try:
        logger.debug("[fetch] title='%s' for %s", title, url)
    except Exception:
        pass
    
    # 5) Resolve icon (sync or deferred)
    icon_path = None
    if not defer_icon:
        icon_path = _resolve_icon_sync(soup, url, host, config, force_refresh, existing_icon_path)
    
    # 6) Fallback to existing icon if resolution failed
    if icon_path is None and existing_icon_path:
        icon_path = existing_icon_path
    
    # 7) Build result with default icon fallback
    try:
        default_icon = resolve_icon_for_link({"type": "web", "icon_path": ""}) or ""
    except Exception:
        default_icon = ""
    
    result = {
        "url": url,
        "title": title,
        "icon": icon_path or default_icon,
        "timestamp": __import__("time").time(),
        "ttl": apply_jitter(CACHE_TTL, config),
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
    try:
        write_cache(url, result, config)
    except Exception as e:
        logger.debug("cache write failed for %s: %s", url, e)
    
    # 9) Schedule deferred icon resolution if needed
    if defer_icon and (icon_path is None):
        scheduler = get_task_scheduler()
        task = _create_icon_resolve_task(soup, url, title, config, on_icon_ready)
        scheduler.submit_task(task)
    
    return result


__all__ = ["fetch_web_link_info"]
