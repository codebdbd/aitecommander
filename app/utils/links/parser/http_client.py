"""HTTP client with shared session and request helper for parser modules."""

from __future__ import annotations

import atexit
import threading
import time
from typing import Dict, Optional

import requests
from requests.exceptions import RequestException

from .constants import TIMEOUT, USER_AGENT, logger

try:
    import cloudscraper  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cloudscraper = None  # type: ignore
    logger.debug("cloudscraper not installed; fallback will be disabled")

# Lazy, shared cloudscraper instance
_CLOUDSCRAPER = None
_CLOUDSCRAPER_GUARD = threading.Lock()

# One-time registration guard for session atexit cleanup
_SESSION_CLEANUP_REGISTERED = False
_SESSION_CLEANUP_GUARD = threading.Lock()


def get_cloudscraper():
    global _CLOUDSCRAPER
    if cloudscraper is None:
        return None
    if _CLOUDSCRAPER is not None:
        return _CLOUDSCRAPER
    with _CLOUDSCRAPER_GUARD:
        if _CLOUDSCRAPER is None:
            try:
                _CLOUDSCRAPER = cloudscraper.create_scraper(
                    browser={
                        "browser": "chrome",
                        "platform": "windows",
                        "mobile": False,
                    }
                )
            except (RuntimeError, ValueError) as e:  # pragma: no cover - creation failure
                logger.warning("cloudscraper init failed: %s", e)
                return None
            try:
                atexit.register(lambda: shutdown_cloudscraper(wait=False))
            except RuntimeError as e:
                logger.debug("failed to register cloudscraper shutdown: %s", e)
    return _CLOUDSCRAPER


def shutdown_cloudscraper(wait: bool = False):
    global _CLOUDSCRAPER
    try:
        s = _CLOUDSCRAPER
        _CLOUDSCRAPER = None
        if s is not None:
            # cloudscraper returns a requests.Session-like object
            close = getattr(s, "close", None)
            if callable(close):
                close()
    except (OSError, RuntimeError, AttributeError) as e:
        logger.debug("cloudscraper shutdown failed: %s", e)


# Thread-local sessions with browser-like headers
_tls = threading.local()


def _cleanup_thread_local_session():
    """Best-effort close for thread-local session at interpreter shutdown.

    Registered once via atexit; safe to call multiple times.
    """
    try:
        s = getattr(_tls, "session", None)
        if s is not None:
            close = getattr(s, "close", None)
            if callable(close):
                close()
    except (OSError, RuntimeError, AttributeError) as e:  # pragma: no cover - best-effort cleanup
        logger.debug("session cleanup failed: %s", e)

def get_session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = requests.Session()
        # Initialize default headers once per thread
        try:
            s.headers.update(
                {
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
                }
            )
        except (TypeError, ValueError, RuntimeError) as e:
            logger.warning("failed to update default session headers: %s", e)
        setattr(_tls, "session", s)
        # One-time atexit registration
        global _SESSION_CLEANUP_REGISTERED
        if not _SESSION_CLEANUP_REGISTERED:
            with _SESSION_CLEANUP_GUARD:
                if not _SESSION_CLEANUP_REGISTERED:
                    try:
                        atexit.register(_cleanup_thread_local_session)
                        _SESSION_CLEANUP_REGISTERED = True
                    except RuntimeError as e:
                        logger.debug("failed to register session atexit cleanup: %s", e)
    return s


def http_request(
    url: str,
    config,
    extra_headers: Optional[Dict[str, str]] = None,
    allow_non_2xx: bool = False,
    timeout_override: Optional[object] = None,
    retries: int = 2,
    http_get=None,
    method: str = "GET",
) -> Optional[requests.Response]:
    headers = {"User-Agent": getattr(config, "USER_AGENT", USER_AGENT)}
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v})
    base_timeout = getattr(config, "TIMEOUT", TIMEOUT)
    timeout = timeout_override if timeout_override is not None else base_timeout

    attempt = 0
    last_err: Optional[Exception] = None
    cf_fallback_attempted = False
    # Configurable switch: allow cloudscraper attempts
    enable_cf = bool(getattr(config, "ENABLE_CLOUDSCRAPER_FALLBACK", True))
    logger.debug(
        "[http][start] method=%s url=%s enable_cf=%s retries=%s timeout=%s",
        method,
        url,
        bool(getattr(config, "ENABLE_CLOUDSCRAPER_FALLBACK", True)),
        retries,
        timeout,
    )
    while attempt <= max(0, int(retries)):
        if attempt > 0:
            time.sleep(0.5 * (2**attempt))
            logger.debug("[retry %s] %s %s", attempt, method, url)
        try:
            if http_get and method == "GET":
                logger.debug("[injected] %s %s", method, url)
                resp = http_get(url, headers=headers, timeout=timeout)
                if resp is None:
                    raise RequestException("Injected http_get returned None")
                if allow_non_2xx:
                    return resp
                resp.raise_for_status()
                return resp
            scraper = get_cloudscraper() if enable_cf else None
            if scraper is not None:
                try:
                    logger.debug("[cloudscraper] %s %s", method, url)
                    resp = scraper.request(
                        method, url, headers=headers, timeout=timeout
                    )
                    if allow_non_2xx:
                        return resp
                    resp.raise_for_status()
                    return resp
                except RequestException as e:
                    logger.warning("Cloudscraper failed for %s: %s", url, e)
                    last_err = e
            logger.debug("[session] %s %s", method, url)
            resp = get_session().request(
                method, url, headers=headers, timeout=timeout
            )
            if allow_non_2xx:
                return resp
            resp.raise_for_status()
            return resp
        except RequestException as e:
            last_err = e
            err_s = str(e)
            status = getattr(getattr(e, "response", None), "status_code", None)
            logger.debug(
                "[http][error] method=%s url=%s status=%s err=%s",
                method,
                url,
                status,
                e,
                exc_info=True,
            )
            should_try_cf = enable_cf and ((status in (403, 429, 503)) or (
                status is None
                and any(
                    tok in err_s.lower()
                    for tok in ["forbidden", "blocked", "cloudflare"]
                )
            ))
            if not cf_fallback_attempted and method == "GET" and should_try_cf:
                try:
                    scraper = get_cloudscraper() if enable_cf else None
                    if scraper is None:
                        raise RequestException("cloudscraper unavailable")
                    logger.debug("[fallback->cloudscraper] %s %s", method, url)
                    resp = scraper.request(
                        method, url, headers=headers, timeout=timeout
                    )
                    if allow_non_2xx:
                        return resp
                    resp.raise_for_status()
                    return resp
                except RequestException as ce:
                    logger.warning("Cloudscraper fallback failed for %s: %s", url, ce)
                finally:
                    cf_fallback_attempted = True
            if (
                "Read timed out" in err_s
                or "ConnectTimeout" in err_s
                or "timeout" in err_s.lower()
            ):
                attempt += 1
                continue
            break
        except Exception as e:
            last_err = e
            logger.error(
                "[http][unexpected] method=%s url=%s err=%s",
                method,
                url,
                e,
                exc_info=True,
            )
            break
    logger.warning("Requests failed for %s: %s", url, last_err)
    return None


__all__ = ["http_request", "get_session"]
