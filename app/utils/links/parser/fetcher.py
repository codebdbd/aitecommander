"""High-level facade to fetch web link info (title + icon).

This implementation is self-contained and uses only modules within parser/.
Supports deferred icon loading for responsive UIs.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from PyQt6.QtCore import QRunnable

from .constants import BS_PARSER, CACHE_TTL, logger
from .http_client import http_request
from .title_parser import get_title
from .icon_downloader import pick_icon_parallel
from .cache import read_cache, write_cache
from .domain import base_domain, apply_jitter
from app.utils.system.task_scheduler import get_task_scheduler, TaskType
from app.utils.ui.icon.path_service import icon_path_service
import os


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
        prefix = 'view-source:'
        if low.startswith(prefix):
            s = s[len(prefix):].lstrip()
        # remove redundant trailing question marks like '???'
        while s.endswith('?'):
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
    # Подготовим host и путь до уже сохранённой иконки домена (если есть)
    try:
        parsed_for_host = urlparse(url)
        host = base_domain(parsed_for_host.netloc)
    except Exception:
        host = ""
    existing_icon_path = None
    if host:
        cand = os.path.join(str(icon_path_service.get_user_icons_dir()), f"web_{host.replace('.', '_')}.png")
        if os.path.exists(cand):
            existing_icon_path = cand
    # 1) Cache
    if not force_refresh:
        cached = read_cache(url, config)
        if cached:
            # Если в кэше дефолтная иконка, но в папке уже есть сохранённая — подставим её (без перезаписи кэша)
            try:
                default_icon = config.get_default_icons().get("web", "")
            except Exception:
                default_icon = ""
            if (not cached.get("icon")) or (cached.get("icon") == default_icon):
                if existing_icon_path:
                    cached = {**cached, "icon": existing_icon_path}
            return cached

    # 2) HTTP fetch page (best-effort)
    # Allow overriding HTML fetch timeout via config.HTML_FETCH_TIMEOUT
    html_timeout = getattr(config, 'HTML_FETCH_TIMEOUT', None)
    try:
        logger.debug(f"[fetch] start url={url} force={force_refresh} defer_icon={defer_icon} html_timeout={html_timeout}")
    except Exception:
        pass
    resp = http_request(url, config, timeout_override=html_timeout)
    soup: Optional[BeautifulSoup] = None
    if resp:
        try:
            # Robust decode (avoid ISO-8859-1 defaults)
            enc = getattr(resp, 'encoding', None)
            if not enc or str(enc).lower() == "iso-8859-1":
                try:
                    # Попытка детектировать кодировку через charset-normalizer
                    try:
                        from charset_normalizer import from_bytes  # type: ignore
                        best = from_bytes(resp.content).best()
                        if best is not None:
                            txt = str(best)
                        else:
                            txt = resp.content.decode(getattr(resp, 'apparent_encoding', None) or 'utf-8', errors='replace')
                    except Exception:
                        txt = resp.content.decode(getattr(resp, 'apparent_encoding', None) or 'utf-8', errors='replace')
                except Exception:
                    txt = resp.text
            else:
                txt = resp.text
            # Безопасное создание soup с запасным парсером
            try:
                soup = BeautifulSoup(txt, BS_PARSER)
            except Exception:
                soup = BeautifulSoup(txt, 'html.parser')
        except Exception as e:
            logger.debug(f"bs4 parse failed for {url}: {e}")
    else:
        try:
            logger.debug(f"[fetch] http_request returned None for {url}")
        except Exception:
            pass

    # 3) Title
    title = get_title(url, config, soup)
    try:
        logger.debug(f"[fetch] title='{title}' for {url}")
    except Exception:
        pass

    # 4) Icon (sync or deferred)
    # host рассчитан выше
    icon_path = None
    def _resolve_icon_async(html_soup: Optional[BeautifulSoup]) -> None:
        if html_soup is None:
            # Best-effort: re-fetch quickly for icon-only if soup missing
            # Allow overriding icon fetch HTML timeout via config.ICON_HTML_TIMEOUT, fallback to HTML_FETCH_TIMEOUT
            icon_html_timeout = getattr(config, 'ICON_HTML_TIMEOUT', getattr(config, 'HTML_FETCH_TIMEOUT', None))
            resp2 = http_request(url, config, timeout_override=icon_html_timeout)
            if resp2:
                try:
                    enc2 = getattr(resp2, 'encoding', None)
                    if not enc2 or str(enc2).lower() == "iso-8859-1":
                        try:
                            txt2 = resp2.content.decode(getattr(resp2, 'apparent_encoding', None) or 'utf-8', errors='replace')
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
            resolved = pick_icon_parallel(html_soup, url, host, config, force_refresh=force_refresh)
        except Exception as ex:
            logger.debug(f"pick_icon (async) failed for {url}: {ex}")
        if not resolved:
            return
        # Update cache with resolved icon
        try:
            current = {
                "url": url,
                "title": title,
                "name": title,
                "icon": resolved,
                "timestamp": __import__("time").time(),
                "ttl": apply_jitter(CACHE_TTL, config),
            }
            write_cache(url, current, config)
        except Exception as ex:
            logger.debug(f"cache write (async) failed for {url}: {ex}")
        # Callback to UI on main thread via TaskScheduler
        if on_icon_ready:
            try:
                sched = get_task_scheduler()
                sched.schedule_operation(
                    lambda: on_icon_ready(resolved),
                    task_type=TaskType.GENERAL,
                    delay=0,
                    operation_id=f"icon_ready:{url}"
                )
            except Exception as ex:
                logger.debug(f"on_icon_ready scheduling failed for {url}: {ex}")

    if not defer_icon:
        try:
            logger.debug(f"[fetch] picking icon sync for host={host}")
            soup_for_icon = soup or BeautifulSoup("", BS_PARSER)
            # Если иконка для домена уже есть — используем её и не скачиваем заново
            if existing_icon_path:
                icon_path = existing_icon_path
            else:
                icon_path = pick_icon_parallel(soup_for_icon, url, host, config, force_refresh=force_refresh)
        except Exception as e:
            logger.debug(f"pick_icon failed for {url}: {e}")

    # 5) Defaults and result
    # Если подбор не дал результата, но иконка уже сохранена ранее для домена — используем её
    if icon_path is None and existing_icon_path:
        icon_path = existing_icon_path
    default_icon = config.get_default_icons().get("web", "")
    result = {
        "url": url,
        "title": title,
        "name": title,  # backward-compat with legacy callers expecting 'name'
        "icon": icon_path or default_icon,
        "timestamp": __import__("time").time(),
        "ttl": apply_jitter(CACHE_TTL, config),
    }
    try:
        logger.debug(f"[fetch] icon={'custom' if icon_path else 'default'} for host={host}")
    except Exception:
        pass

    # 6) Cache store (initial)
    try:
        write_cache(url, result, config)
    except Exception as e:
        logger.debug(f"cache write failed for {url}: {e}")

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
