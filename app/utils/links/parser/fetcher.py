"""High-level facade to fetch web link info (title + icon).

This implementation is self-contained and uses only modules within parser/.
Supports deferred icon loading for responsive UIs.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional
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


def fetch_web_link_info(
    url: str,
    config,
    force_refresh: bool = False,
    *,
    defer_icon: bool = False,
    on_icon_ready: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    # Preprocess URL: strip 'view-source:' and trailing question marks
    def _sanitize_url(u: str) -> str:
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

    url = _sanitize_url(url)
    # Prepare host and path to previously saved domain icon (if any)
    try:
        parsed_for_host = urlparse(url)
        host = base_domain(parsed_for_host.netloc)
    except Exception:
        host = ""
    existing_icon_path = None
    if host:
        cand = os.path.join(
            str(icon_path_service.get_user_icons_dir()),
            f"web_{host.replace('.', '_')}.png",
        )
        if os.path.exists(cand):
            existing_icon_path = cand
    # 1) Cache
    if not force_refresh:
        cached = read_cache(url, config)
        if cached:
            # If cache has default icon but the folder contains saved one — reuse it (without overwriting cache)
            try:
                default_icon_path = (
                    resolve_icon_for_link({"type": "web", "icon_path": ""}) or ""
                )
            except Exception:
                default_icon_path = ""
            if (not cached.get("icon")) or (cached.get("icon") == default_icon_path):
                if existing_icon_path:
                    cached = {**cached, "icon": existing_icon_path}
            return cached

    # 2) HTTP fetch page (best-effort)
    # Allow overriding HTML fetch timeout via config.HTML_FETCH_TIMEOUT
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
    resp = http_request(url, config, timeout_override=html_timeout)
    soup: Optional[BeautifulSoup] = None
    if resp:
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
                soup = BeautifulSoup(txt, BS_PARSER)
            except Exception:
                soup = BeautifulSoup(txt, "html.parser")
        except Exception as e:
            logger.debug("bs4 parse failed for %s: %s", url, e)
    else:
        try:
            logger.debug("[fetch] http_request returned None for %s", url)
        except Exception:
            pass

    # 3) Title
    title = get_title(url, config, soup)
    try:
        logger.debug("[fetch] title='%s' for %s", title, url)
    except Exception:
        pass

    # 4) Icon (sync or deferred)
    # host computed above
    icon_path = None

    def _resolve_icon_async(html_soup: Optional[BeautifulSoup]) -> None:
        if html_soup is None:
            # Best-effort: re-fetch quickly for icon-only if soup missing
            # Allow overriding icon fetch HTML timeout via config.ICON_HTML_TIMEOUT, fallback to HTML_FETCH_TIMEOUT
            icon_html_timeout = getattr(
                config, "ICON_HTML_TIMEOUT", getattr(config, "HTML_FETCH_TIMEOUT", None)
            )
            resp2 = http_request(url, config, timeout_override=icon_html_timeout)
            if resp2:
                try:
                    enc2 = getattr(resp2, "encoding", None)
                    if not enc2 or str(enc2).lower() == "iso-8859-1":
                        try:
                            txt2 = resp2.content.decode(
                                getattr(resp2, "apparent_encoding", None) or "utf-8",
                                errors="replace",
                            )
                        except Exception:
                            txt2 = resp2.text
                    else:
                        txt2 = resp2.text
                    html_soup = BeautifulSoup(txt2, BS_PARSER)
                except Exception:
                    html_soup = None
        if html_soup is None:
            return
        resolved = None
        try:
            resolved = pick_icon_parallel(
                html_soup, url, host, config, force_refresh=force_refresh
            )
        except Exception as ex:
            logger.debug("pick_icon (async) failed for %s: %s", url, ex)
        if not resolved:
            return
        # Update cache with resolved icon
        try:
            current = {
                "url": url,
                "title": title,
                "icon": resolved,
                "timestamp": __import__("time").time(),
                "ttl": apply_jitter(CACHE_TTL, config),
            }
            write_cache(url, current, config)
        except Exception as ex:
            logger.debug("cache write (async) failed for %s: %s", url, ex)
        # Callback to UI on main thread via TaskScheduler
        if on_icon_ready:
            try:
                sched = get_task_scheduler()
                # Обновление UI таблицы — используем TABLE_UPDATE и немедленную доставку
                sched.schedule_operation(
                    lambda: on_icon_ready(resolved),
                    task_type=TaskType.TABLE_UPDATE,
                    delay=0,
                    operation_id=f"icon_ready:{url}",
                )
            except Exception as ex:
                logger.debug("on_icon_ready scheduling failed for %s: %s", url, ex)

    if not defer_icon:
        try:
            logger.debug("[fetch] picking icon sync for host=%s", host)
            soup_for_icon = soup or BeautifulSoup("", BS_PARSER)
            # If a domain icon already exists — reuse it and skip download
            if existing_icon_path:
                icon_path = existing_icon_path
            else:
                icon_path = pick_icon_parallel(
                    soup_for_icon, url, host, config, force_refresh=force_refresh
                )
        except Exception as e:
            logger.debug("pick_icon failed for %s: %s", url, e)

    # 5) Defaults and result
    # If picking failed but domain icon exists — reuse it
    if icon_path is None and existing_icon_path:
        icon_path = existing_icon_path
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

    # 6) Cache store (initial)
    try:
        write_cache(url, result, config)
    except Exception as e:
        logger.debug("cache write failed for %s: %s", url, e)

    # 7) If deferred, resolve icon via TaskScheduler thread pool and notify UI safely
    if defer_icon and (icon_path is None):
        scheduler = get_task_scheduler()

        class IconResolveTask(QRunnable):
            def run(self_nonlocal):  # type: ignore[no-redef]
                _resolve_icon_async(soup)
                # _resolve_icon_async itself writes cache and triggers callback via scheduler
                # To ensure UI callback runs on main thread, schedule it inside _resolve_icon_async via scheduler
                return

        # Submit worker task to thread pool
        scheduler.submit_task(IconResolveTask())

    return result


__all__ = ["fetch_web_link_info"]
