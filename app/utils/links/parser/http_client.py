"""HTTP client with shared session and request helper for parser modules."""

from __future__ import annotations

import atexit
import threading
import warnings

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning

from .constants import HTTP_RETRIES, HTTP_RETRY_BACKOFF, TIMEOUT, USER_AGENT, logger

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


def _is_cancelled(cancel_event) -> bool:
    """Return True if cancel_event is set (safe for None)."""
    return bool(
        cancel_event is not None
        and getattr(cancel_event, "is_set", lambda: False)()
    )


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
            except (
                RuntimeError,
                ValueError,
            ) as e:  # pragma: no cover - creation failure
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
    except (
        OSError,
        RuntimeError,
        AttributeError,
    ) as e:  # pragma: no cover - best-effort cleanup
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
        _tls.session = s
        # Mark retries not configured yet; will be configured once by http_request on first use
        try:
            s._retry_installed = False  # type: ignore[attr-defined]
        except Exception:
            pass
        # Add a simple response hook for debug logging of responses
        try:

            def _log_response(resp, *args, **kwargs):
                try:
                    logger.debug(
                        "[http][resp] method=%s url=%s status=%s",
                        getattr(resp.request, "method", ""),
                        getattr(resp, "url", ""),
                        getattr(resp, "status_code", None),
                    )
                except Exception:
                    pass

            s.hooks.setdefault("response", []).append(_log_response)
        except Exception:
            pass
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


def _prepare_headers(config, extra_headers):
    """Prepare request headers."""
    headers = {"User-Agent": getattr(config, "USER_AGENT", USER_AGENT)}
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v})
    return headers


def _build_request_kwargs(headers, timeout, stream, allow_redirects, verify=None):
    """Build request kwargs dict."""
    kwargs = {"headers": headers, "timeout": timeout}
    if stream is not None:
        kwargs["stream"] = stream
    if allow_redirects is not None:
        kwargs["allow_redirects"] = allow_redirects
    if verify is not None:
        kwargs["verify"] = verify
    return kwargs


def _try_injected_http_get(http_get, url, headers, timeout, allow_non_2xx, method):
    """Try injected http_get function."""
    if http_get and method == "GET":
        logger.debug("[injected] %s %s", method, url)
        resp = http_get(url, headers=headers, timeout=timeout)
        if resp is None:
            raise RequestException("Injected http_get returned None")
        if allow_non_2xx:
            return resp
        resp.raise_for_status()
        return resp
    return None


def _try_cloudscraper(
    enable_cf, method, url, headers, timeout, stream, allow_redirects, allow_non_2xx, verify=None
):
    """Try cloudscraper request."""
    scraper = get_cloudscraper() if enable_cf else None
    if scraper is not None:
        logger.debug("[cloudscraper] %s %s", method, url)
        kwargs = _build_request_kwargs(headers, timeout, stream, allow_redirects, verify=verify)
        resp = scraper.request(method, url, **kwargs)
        if allow_non_2xx:
            return resp
        resp.raise_for_status()
        return resp
    return None


def _prefer_cloudscraper_primary(config) -> bool:
    try:
        return bool(getattr(config, "HTTP_CLOUDSCRAPER_PRIMARY", True))
    except Exception:
        return True


def _session_retry_mode_label(retries: int | None) -> str:
    if retries is None:
        return "shared"
    return f"temp:{max(0, int(retries))}"


def _try_session_request(
    config,
    method,
    url,
    headers,
    timeout,
    retries,
    stream,
    allow_redirects,
    allow_non_2xx,
    cancel_event=None,
    verify=None,
):
    """Try request using shared session."""
    retries_override = None if retries is None else int(retries)
    use_temp_session = retries_override is not None
    sess = requests.Session() if use_temp_session else get_session()
    logger.debug(
        "[http][session_mode] method=%s url=%s retry_mode=%s",
        method,
        url,
        _session_retry_mode_label(retries_override),
    )
    try:
        try:
            if use_temp_session:
                _configure_session_retries(
                    sess,
                    config=config,
                    retries_override=retries_override,
                )
            elif not bool(getattr(sess, "_retry_installed", False)):
                _configure_session_retries(sess, config=config)
                try:
                    sess._retry_installed = True  # type: ignore[attr-defined]
                except Exception:
                    pass
        except Exception:
            logger.debug("failed to configure session retries (one-time)", exc_info=True)
        logger.debug("[session] %s %s", method, url)
        if _is_cancelled(cancel_event):
            return None
        req_kwargs = _build_request_kwargs(
            headers,
            timeout,
            stream,
            allow_redirects,
            verify=verify,
        )
        if verify is False:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", InsecureRequestWarning)
                resp = sess.request(method, url, **req_kwargs)
        else:
            resp = sess.request(method, url, **req_kwargs)
        if allow_non_2xx:
            return resp
        resp.raise_for_status()
        return resp
    finally:
        if use_temp_session:
            try:
                sess.close()
            except Exception:
                pass


def _should_try_cloudscraper_fallback(enable_cf, e, method):
    """Check if cloudscraper fallback should be attempted."""
    if not enable_cf or method != "GET":
        return False
    err_s = str(e)
    status = getattr(getattr(e, "response", None), "status_code", None)
    return (status in (403, 429, 503)) or (
        status is None
        and any(tok in err_s.lower() for tok in ["forbidden", "blocked", "cloudflare"])
    )

def _attempt_cloud_primary(
    enable_cf,
    method,
    url,
    headers,
    timeout,
    stream,
    allow_redirects,
    allow_non_2xx,
    cancel_event,
) -> requests.Response | None:
    """Attempt a primary request via cloudscraper, honoring cancellation.

    Returns a response or None. Raises RequestException for fatal aborts
    (so the caller can short-circuit) after logging via _handle_cloudscraper_error.
    """
    if _is_cancelled(cancel_event):
        return None
    try:
        resp = _try_cloudscraper(
            enable_cf,
            method,
            url,
            headers,
            timeout,
            stream,
            allow_redirects,
            allow_non_2xx,
        )
        if resp is not None:
            return resp
    except RequestException as e:
        if _handle_cloudscraper_error(e, url):
            # re-raise for outer handler to treat as fatal
            raise
    return None

def _attempt_injected_request_safe(
    http_get,
    url,
    headers,
    timeout,
    allow_non_2xx,
    method,
):
    """Attempt injected GET safely; capture RequestException instead of raising."""
    try:
        resp = _try_injected_http_get(
            http_get, url, headers, timeout, allow_non_2xx, method
        )
        return resp, None
    except RequestException as e:  # pragma: no cover - injected path mostly in tests
        return None, e

def _handle_main_request_exception(
    e: Exception,
    enable_cf: bool,
    method: str,
    url: str,
    headers: dict[str, str],
    timeout,
    allow_non_2xx: bool,
    cancel_event,
):
    """Handle RequestException from main flow; may try cloudscraper fallback.

    Returns (response or None, last_exception or None).
    """
    status = getattr(getattr(e, "response", None), "status_code", None)
    logger.debug(
        "[http][error] method=%s url=%s status=%s err=%s", "GET" if method is None else method, url, status, e, exc_info=True
    )
    if _is_fatal_exception(e):
        logger.info("[http] Fatal error, aborting: %s", url)
        try:
            setattr(e, "_codex_fatal_http", True)
        except Exception:
            pass
        return None, e
    if _should_try_cloudscraper_fallback(enable_cf, e, method) and not _is_cancelled(cancel_event):
        try:
            cf_resp = _try_cloudscraper_fallback(
                enable_cf, method, url, headers, timeout, allow_non_2xx
            )
            return cf_resp, None
        except RequestException as ce:
            logger.warning("Cloudscraper fallback failed for %s: %s", url, ce)
            return None, ce
    return None, e


def _try_cloudscraper_fallback(enable_cf, method, url, headers, timeout, allow_non_2xx):
    """Try cloudscraper as fallback."""
    scraper = get_cloudscraper() if enable_cf else None
    if scraper is None:
        raise RequestException("cloudscraper unavailable")
    logger.debug("[fallback->cloudscraper] %s %s", method, url)
    resp = scraper.request(method, url, headers=headers, timeout=timeout)
    if allow_non_2xx:
        return resp
    resp.raise_for_status()
    return resp


def _allow_insecure_ssl_fallback(config) -> bool:
    try:
        return bool(getattr(config, "HTTP_ALLOW_INSECURE_SSL_FALLBACK", True))
    except Exception:
        return True


def _is_ssl_error(exc: Exception) -> bool:
    """Return True if exception looks like an SSL error."""
    return "SSLError" in type(exc).__name__ or "SSL" in str(exc)


def _is_name_resolution_error(exc: Exception) -> bool:
    """Return True if exception indicates DNS/name resolution failure."""
    text = f"{type(exc).__name__}: {exc}"
    lowered = text.lower()
    return (
        "nameresolutionerror" in lowered
        or "getaddrinfo failed" in lowered
        or "failed to resolve" in lowered
        or "temporary failure in name resolution" in lowered
    )


def _is_fatal_status_code(code: int | None) -> bool:
    """Return True for HTTP statuses that are treated as fatal (no retry/fallback)."""
    return code in (403, 404)


def _is_fatal_exception(exc: Exception) -> bool:
    """Return True if exception is considered fatal.

    SSL errors are intentionally not treated as fatal here, because some sites
    still succeed via the alternative request path/browser-like fetch strategy.
    """
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return (
        _is_name_resolution_error(exc)
        or _is_fatal_status_code(status)
    )


def _handle_cloudscraper_error(e: Exception, url: str) -> bool:
    """Log cloudscraper error and return True if we must abort immediately."""
    logger.warning("Cloudscraper failed for %s: %s", url, e)
    if _is_name_resolution_error(e):
        logger.info("[http] Name resolution error is fatal, aborting: %s", url)
        return True
    status = getattr(getattr(e, "response", None), "status_code", None)
    if _is_fatal_status_code(status):
        logger.info("[http] Status %s is fatal, aborting: %s", status, url)
        return True
    return False


def http_request(
    url: str,
    config,
    extra_headers: dict[str, str] | None = None,
    allow_non_2xx: bool = False,
    timeout_override: object | None = None,
    retries: int = 1,  # Reduced retries to avoid long waits on unreachable sites
    http_get=None,
    method: str = "GET",
    stream: bool | None = None,
    allow_redirects: bool | None = None,
    cancel_event=None,
    prefer_cloudscraper_primary: bool | None = None,
) -> requests.Response | None:
    if _is_cancelled(cancel_event):
        logger.debug("[http] cancel_event set before request %s", url)
        return None
    headers = _prepare_headers(config, extra_headers)
    base_timeout = getattr(config, "TIMEOUT", TIMEOUT)
    timeout = timeout_override if timeout_override is not None else base_timeout

    enable_cf = bool(getattr(config, "ENABLE_CLOUDSCRAPER_FALLBACK", True))
    if prefer_cloudscraper_primary is None:
        prefer_cloudscraper_primary = _prefer_cloudscraper_primary(config)
    logger.debug(
        "[http][start] method=%s url=%s enable_cf=%s retries=%s timeout=%s retry_mode=%s cf_primary=%s",
        method,
        url,
        enable_cf,
        retries,
        timeout,
        _session_retry_mode_label(retries),
        prefer_cloudscraper_primary,
    )

    resp, last_err = _http_request_impl(
        url=url,
        config=config,
        headers=headers,
        timeout=timeout,
        retries=retries,
        allow_non_2xx=allow_non_2xx,
        http_get=http_get,
        method=method,
        stream=stream,
        allow_redirects=allow_redirects,
        cancel_event=cancel_event,
        enable_cf=enable_cf,
        prefer_cloudscraper_primary=prefer_cloudscraper_primary,
    )
    if resp is not None:
        return resp
    logger.warning("Requests failed for %s: %s", url, last_err)
    return None


def _http_request_impl(
    *,
    url: str,
    config,
    headers: dict[str, str],
    timeout,
    retries: int,
    allow_non_2xx: bool,
    http_get,
    method: str,
    stream: bool | None,
    allow_redirects: bool | None,
    cancel_event,
    enable_cf: bool,
    prefer_cloudscraper_primary: bool,
):
    """Core HTTP flow extracted from http_request to reduce complexity.

    Returns a tuple of (response or None, last_exception or None).
    """
    last_err: Exception | None = None
    insecure_ssl_allowed = _allow_insecure_ssl_fallback(config)
    if _is_cancelled(cancel_event):
        return None, None

    # 1) injected (safe)
    resp, err = _attempt_injected_request_safe(
        http_get, url, headers, timeout, allow_non_2xx, method
    )
    if resp is not None:
        return resp, None
    if err is not None:
        r, last_err = _handle_main_request_exception(
            err, enable_cf, method, url, headers, timeout, allow_non_2xx, cancel_event
        )
        if r is not None:
            return r, None

    def _attempt_session():
        return _try_session_request(
            config,
            method,
            url,
            headers,
            timeout,
            retries,
            stream,
            allow_redirects,
            allow_non_2xx,
            cancel_event=cancel_event,
        )
    def _attempt_cloud():
        return _attempt_cloud_primary(
            enable_cf,
            method,
            url,
            headers,
            timeout,
            stream,
            allow_redirects,
            allow_non_2xx,
            cancel_event,
        )

    attempts = (
        (_attempt_cloud, "cloudscraper-primary"),
        (_attempt_session, "session"),
    ) if prefer_cloudscraper_primary else (
        (_attempt_session, "session"),
        (_attempt_cloud, "cloudscraper-primary"),
    )

    for attempt_func, attempt_name in attempts:
        try:
            resp = attempt_func()
            if resp is not None:
                return resp, None
        except RequestException as e:
            r, last_err = _handle_main_request_exception(
                e, enable_cf, method, url, headers, timeout, allow_non_2xx, cancel_event
            )
            if r is not None:
                return r, None
            if bool(getattr(last_err, "_codex_fatal_http", False)):
                return None, last_err
            if (
                attempt_name == "session"
                and insecure_ssl_allowed
                and _is_ssl_error(e)
                and not _is_cancelled(cancel_event)
            ):
                try:
                    logger.info("[http] SSL verify failed, retrying insecure session for %s", url)
                    insecure_resp = _try_session_request(
                        config,
                        method,
                        url,
                        headers,
                        timeout,
                        0,
                        stream,
                        allow_redirects,
                        allow_non_2xx,
                        cancel_event=cancel_event,
                        verify=False,
                    )
                    if insecure_resp is not None:
                        return insecure_resp, None
                except RequestException as insecure_err:
                    last_err = insecure_err
        except Exception as e:  # unexpected
            last_err = e
            logger.error(
                "[http][unexpected] phase=%s method=%s url=%s err=%s",
                attempt_name,
                method,
                url,
                e,
                exc_info=True,
            )
    return None, last_err


__all__ = ["http_request", "get_session"]


def _configure_session_retries(
    session: requests.Session,
    *,
    config=None,
    retries_override: int | None = None,
) -> None:
    """Configure retry policy on the shared session ONCE.

    Uses config.HTTP_RETRIES (int, default 3), config.HTTP_RETRY_BACKOFF (float, default 0.5),
    and config.HTTP_RETRY_ON_STATUS (bool, default True). Safe to call multiple times; idempotent by remounting once
    at session creation.
    """
    try:
        # Read config values with safe defaults
        retries = HTTP_RETRIES  # Default 3 retries
        backoff_factor = HTTP_RETRY_BACKOFF  # Default 0.5s exponential backoff
        enable_status = True  # Enable status-based retries by default
        try:
            if retries_override is not None:
                retries = max(0, int(retries_override))
            elif config is not None:
                retries = int(getattr(config, "HTTP_RETRIES", HTTP_RETRIES) or HTTP_RETRIES)
                backoff_factor = float(
                    getattr(config, "HTTP_RETRY_BACKOFF", HTTP_RETRY_BACKOFF) or HTTP_RETRY_BACKOFF
                )
                enable_status = bool(getattr(config, "HTTP_RETRY_ON_STATUS", True))
        except Exception:
            pass

        status_forcelist = (429, 500, 502, 503, 504) if enable_status else None
        allowed_methods = frozenset(["HEAD", "GET", "OPTIONS"])  # idempotent only

        r = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries if enable_status else 0,
            backoff_factor=backoff_factor,
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
        adapter = HTTPAdapter(
            max_retries=r, pool_connections=pool_conns, pool_maxsize=pool_size
        )
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
