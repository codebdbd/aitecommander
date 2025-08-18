"""Optional lightweight JS renderer using Playwright (sync API).

This module is safe to import even if Playwright is not installed.
Provide render_html(url, config) -> Optional[str] that returns fully rendered HTML
(or None on failure). Blocks heavy resources to be efficient.
"""
from __future__ import annotations

from typing import Optional

from .constants import logger

# Optional import
try:  # pragma: no cover - optional dependency
    from playwright.sync_api import sync_playwright  # type: ignore
except Exception:  # pragma: no cover
    sync_playwright = None  # type: ignore

# Lazy-initialized global browser/context
_browser = None
_context = None
_pl = None


def _init_browser(config) -> bool:
    global _browser, _context, _pl
    if sync_playwright is None:
        try:
            logger.warning("Playwright is not installed. Skipping JS rendering.")
        except Exception:
            pass
        return False
    if _browser is not None and _context is not None and _pl is not None:
        return True
    try:
        _pl = sync_playwright().start()
        headless = bool(getattr(config, 'PLAYWRIGHT_HEADLESS', True))
        # По умолчанию используем встроенный Chromium, не указывая channel.
        # Если в конфиге явно задан PLAYWRIGHT_CHANNEL, применяем его.
        launch_kwargs = {"headless": headless}
        cfg_channel = getattr(config, 'PLAYWRIGHT_CHANNEL', None)
        if cfg_channel:
            launch_kwargs["channel"] = cfg_channel
        _browser = _pl.chromium.launch(**launch_kwargs)
        _context = _browser.new_context(
            user_agent=getattr(config, 'USER_AGENT', None) or None,
            java_script_enabled=True,
            ignore_https_errors=bool(getattr(config, 'PLAYWRIGHT_IGNORE_HTTPS_ERRORS', True)),
            bypass_csp=True,
            viewport={'width': 1280, 'height': 800},
        )
        # Block heavy resources
        def _route_intercept(route):
            req = route.request
            if req.resource_type in {"image", "media", "font", "stylesheet"}:
                return route.abort()
            return route.continue_()
        _context.route("**/*", _route_intercept)
        return True
    except Exception as e:
        try:
            logger.warning(f"Playwright init failed: {e}")
        except Exception:
            pass
        try:
            if _pl:
                _pl.stop()
        except Exception:
            pass
        _pl = None
        _browser = None
        _context = None
        return False


def render_html(url: str, config) -> Optional[str]:
    """Render page with Playwright and return page.content() or None.

    Efficiency:
    - Blocks images/media/fonts/css
    - Headless by default
    - Navigation timeout and post-load wait are configurable
    """
    if not _init_browser(config):
        return None
    nav_timeout_ms = int(getattr(config, 'PLAYWRIGHT_NAV_TIMEOUT_MS', 9000))
    max_wait_ms = int(getattr(config, 'JS_RENDER_MAX_WAIT_MS', 1200))
    try:
        page = _context.new_page()
        page.set_default_navigation_timeout(nav_timeout_ms)
        page.set_default_timeout(nav_timeout_ms)
        page.goto(url, wait_until="domcontentloaded")
        # Small wait for SPA hydration
        if max_wait_ms > 0:
            page.wait_for_timeout(max_wait_ms)
        html = page.content()
        page.close()
        return html
    except Exception as e:
        try:
            logger.warning(f"[render] Playwright render failed url={url}: {e}")
        except Exception:
            pass
        try:
            page.close()
        except Exception:
            pass
        return None


def _shutdown():  # pragma: no cover
    global _browser, _context, _pl
    try:
        if _context:
            _context.close()
    except Exception:
        pass
    try:
        if _browser:
            _browser.close()
    except Exception:
        pass
    try:
        if _pl:
            _pl.stop()
    except Exception:
        pass
    _browser = None
    _context = None
    _pl = None


__all__ = ["render_html"]
