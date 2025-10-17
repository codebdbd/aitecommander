"""Optional lightweight JS renderer using Playwright (sync API).

This module is safe to import even if Playwright is not installed.
Provide render_html(url, config) -> Optional[str] that returns fully rendered HTML
(or None on failure). Blocks heavy resources to be efficient.
"""

from __future__ import annotations

from typing import Any

from .constants import logger

# Optional import
try:  # pragma: no cover - optional dependency
    from playwright.sync_api import sync_playwright  # type: ignore
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore

# Lazy-initialized global browser/context
_browser: Any = None
_context: Any = None
_pl: Any = None


def _init_browser(config: Any) -> bool:
    global _browser, _context, _pl
    if sync_playwright is None:
        logger.warning("Playwright is not installed. Skipping JS rendering.")
        return False
    if _browser is not None and _context is not None and _pl is not None:
        return True
    try:
        _pl = sync_playwright().start()
        headless = bool(getattr(config, "PLAYWRIGHT_HEADLESS", True))
        # By default use built-in Chromium without specifying channel.
        # If PLAYWRIGHT_CHANNEL is explicitly set in config, use it.
        launch_kwargs: dict[str, bool | str | float] = {"headless": headless}
        cfg_channel = getattr(config, "PLAYWRIGHT_CHANNEL", None)
        if cfg_channel and isinstance(cfg_channel, str):
            launch_kwargs["channel"] = cfg_channel
        _browser = _pl.chromium.launch(**launch_kwargs)
        _context = _browser.new_context(
            user_agent=getattr(config, "USER_AGENT", None) or None,
            java_script_enabled=True,
            ignore_https_errors=bool(
                getattr(config, "PLAYWRIGHT_IGNORE_HTTPS_ERRORS", True)
            ),
            bypass_csp=True,
            viewport={"width": 1280, "height": 800},
        )

        # Block heavy resources
        def _route_intercept(route):
            req = route.request
            if req.resource_type in {"image", "media", "font", "stylesheet"}:
                return route.abort()
            return route.continue_()

        _context.route("**/*", _route_intercept)
        return True
    except (RuntimeError, ValueError) as e:
        logger.warning("Playwright init failed: %s", e)
    except Exception:
        logger.exception("Playwright init failed with unexpected error")
    finally:
        if _browser is None or _context is None or _pl is None:
            # partial init, ensure cleanup
            try:
                if _context:
                    _context.close()
            except Exception:
                logger.debug("Context close failed during init cleanup", exc_info=True)
            try:
                if _browser:
                    _browser.close()
            except Exception:
                logger.debug("Browser close failed during init cleanup", exc_info=True)
            try:
                if _pl:
                    _pl.stop()
            except Exception:
                logger.debug(
                    "Playwright stop failed during init cleanup", exc_info=True
                )
            _pl = None
            _browser = None
            _context = None

    return False


def render_html(url: str, config) -> str | None:
    """Render page with Playwright and return page.content() or None.

    Efficiency:
    - Blocks images/media/fonts/css
    - Headless by default
    - Navigation timeout and post-load wait are configurable
    """
    if not _init_browser(config):
        return None
    assert _context is not None  # mypy: ensured by _init_browser success
    nav_timeout_ms = int(getattr(config, "PLAYWRIGHT_NAV_TIMEOUT_MS", 9000))
    max_wait_ms = int(getattr(config, "JS_RENDER_MAX_WAIT_MS", 1200))
    page = None
    try:
        page = _context.new_page()
        page.set_default_navigation_timeout(nav_timeout_ms)
        page.set_default_timeout(nav_timeout_ms)
        page.goto(url, wait_until="domcontentloaded")
        # Small wait for SPA hydration
        if max_wait_ms > 0:
            page.wait_for_timeout(max_wait_ms)
        html = page.content()
        return html
    except (RuntimeError, ValueError) as e:
        logger.warning("[render] Playwright render failed url=%s: %s", url, e)
        return None
    except Exception:
        logger.exception(
            "[render] Playwright render failed with unexpected error url=%s", url
        )
        return None
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                logger.debug("page.close() failed in finally", exc_info=True)


def _shutdown():  # pragma: no cover
    global _browser, _context, _pl
    try:
        if _context:
            _context.close()
    except Exception:
        logger.debug("_shutdown: context.close failed", exc_info=True)
    try:
        if _browser:
            _browser.close()
    except Exception:
        logger.debug("_shutdown: browser.close failed", exc_info=True)
    try:
        if _pl:
            _pl.stop()
    except Exception:
        logger.debug("_shutdown: pl.stop failed", exc_info=True)
    _browser = None
    _context = None
    _pl = None


__all__ = ["render_html"]
