"""HTTP client with shared session and request helper for parser modules."""

from __future__ import annotations

import atexit
import threading
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

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
        except (TypeError, ValueError) as e:
            logger.warning("failed to update default session headers: %s", e)
        except Exception as e:
            # Unexpected errors should be logged with full traceback and we continue without these headers
            logger.error("unexpected error updating default session headers: %s", e, exc_info=True)
        setattr(_tls, "session", s)
        # Mark retries not configured yet; will be configured once by http_request on first use
        try:
            setattr(s, "_retry_installed", False)  # type: ignore[attr-defined]
        except Exception:
            pass
        # Add a simple response hook for debug logging of responses
        def _log_response(resp, *args, **kwargs):
            try:
                logger.debug(
                    "[http][resp] method=%s url=%s status=%s",
                    getattr(resp.request, "method", ""),
                    getattr(resp, "url", ""),
                    getattr(resp, "status_code", None),
                )
            except AttributeError:
                # Handle only attribute access issues gracefully; others should propagate
                logger.debug("response logging skipped due to missing attributes")

        # Register response hook; only handle expected configuration errors here
        try:
            s.hooks.setdefault("response", []).append(_log_response)
        except (TypeError, ValueError) as e:
            logger.warning("failed to register response hook: %s", e)
        except Exception as e:
            # Log unexpected errors with traceback and proceed without hook
            logger.error("unexpected error registering response hook: %s", e, exc_info=True)
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
    stream: Optional[bool] = None,
    allow_redirects: Optional[bool] = None,
) -> Optional[requests.Response]:
    headers = {"User-Agent": getattr(config, "USER_AGENT", USER_AGENT)}
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v})
    base_timeout = getattr(config, "TIMEOUT", TIMEOUT)
    timeout = timeout_override if timeout_override is not None else base_timeout

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
                kwargs = {"headers": headers, "timeout": timeout}
                if stream is not None:
                    kwargs["stream"] = stream
                if allow_redirects is not None:
                    kwargs["allow_redirects"] = allow_redirects
                resp = scraper.request(method, url, **kwargs)
                if allow_non_2xx:
                    return resp
                resp.raise_for_status()
                return resp
            except RequestException as e:
                logger.warning("Cloudscraper failed for %s: %s", url, e)
                last_err = e
        # Get shared session and configure retries once per session (no per-call remount)
        sess = get_session()
        try:
            if not bool(getattr(sess, "_retry_installed", False)):
                _configure_session_retries(sess, config=config)
                try:
                    setattr(sess, "_retry_installed", True)  # type: ignore[attr-defined]
                except Exception:
                    pass
        except Exception:
            logger.debug("failed to configure session retries (one-time)", exc_info=True)
        logger.debug("[session] %s %s", method, url)
        req_kwargs = {"headers": headers, "timeout": timeout}
        if stream is not None:
            req_kwargs["stream"] = stream
        if allow_redirects is not None:
            req_kwargs["allow_redirects"] = allow_redirects
        resp = sess.request(method, url, **req_kwargs)
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
            status is None and any(tok in err_s.lower() for tok in ["forbidden", "blocked", "cloudflare"])
        ))
        if not cf_fallback_attempted and method == "GET" and should_try_cf:
            try:
                scraper = get_cloudscraper() if enable_cf else None
                if scraper is None:
                    raise RequestException("cloudscraper unavailable")
                logger.debug("[fallback->cloudscraper] %s %s", method, url)
                resp = scraper.request(method, url, headers=headers, timeout=timeout)
                if allow_non_2xx:
                    return resp
                resp.raise_for_status()
                return resp
            except RequestException as ce:
                logger.warning("Cloudscraper fallback failed for %s: %s", url, ce)
            finally:
                cf_fallback_attempted = True
    except Exception as e:
        last_err = e
        logger.error(
            "[http][unexpected] method=%s url=%s err=%s",
            method,
            url,
            e,
            exc_info=True,
        )
    logger.warning("Requests failed for %s: %s", url, last_err)
    return None


__all__ = ["http_request", "get_session"]


def _configure_session_retries(session: requests.Session, *, config=None) -> None:
    """Configure retry policy on the shared session ONCE.

    Uses config.HTTP_RETRIES (int, default 2), config.HTTP_RETRY_BACKOFF (float, default 0.5),
    and config.HTTP_RETRY_ON_STATUS (bool, default False). Safe to call multiple times; idempotent by remounting once
    at session creation.
    """
    try:
        # Read config values with safe defaults
        retries = 0
        backoff_factor = 0.5
        enable_status = False
        try:
            if config is not None:
                retries = int(getattr(config, "HTTP_RETRIES", 2) or 0)
                backoff_factor = float(getattr(config, "HTTP_RETRY_BACKOFF", 0.5) or 0.5)
                enable_status = bool(getattr(config, "HTTP_RETRY_ON_STATUS", False))
        except Exception:
            pass

        status_forcelist = (429, 500, 502, 503, 504) if enable_status else None
        allowed_methods = frozenset(["HEAD", "GET", "OPTIONS"])  # idempotent only

        r = Retry(
            total=max(0, int(retries)),
            connect=max(0, int(retries)),
            read=max(0, int(retries)),
            status=max(0, int(retries)) if enable_status else 0,
            backoff_factor=float(backoff_factor),
            status_forcelist=status_forcelist,
            allowed_methods=allowed_methods,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        # Pool sizing
        pool_conns = 10
        pool_size = 20
        try:
            if config is not None:
                pool_conns = int(getattr(config, "HTTP_POOL_CONNECTIONS", 10) or 10)
                pool_size = int(getattr(config, "HTTP_POOL_MAXSIZE", 20) or 20)
        except Exception:
            pass
        adapter = HTTPAdapter(max_retries=r, pool_connections=pool_conns, pool_maxsize=pool_size)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        logger.debug(
            "[http][retry] configured(session) retries=%s backoff_factor=%s on_status=%s pool=(%s,%s)",
            retries,
            backoff_factor,
            enable_status,
            pool_conns,
            pool_size,
        )
    except Exception as e:
        logger.debug("failed to configure session retries: %s", e, exc_info=True)
