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
except Exception:  # pragma: no cover - optional dependency
    cloudscraper = None  # type: ignore
    logger.warning("cloudscraper not installed, some sites may fail to fetch")

# Lazy, shared cloudscraper instance
_CLOUDSCRAPER = None
_CLOUDSCRAPER_GUARD = threading.Lock()


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
            except Exception as e:  # pragma: no cover - creation failure
                logger.warning("cloudscraper init failed: %s", e)
                return None
            try:
                atexit.register(lambda: shutdown_cloudscraper(wait=False))
            except Exception:
                pass
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
    except Exception:
        pass

# Global session with browser-like headers
session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    }
)


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
    while attempt <= max(0, int(retries)):
        if attempt > 0:
            time.sleep(0.5 * (2**attempt))
            logger.debug("[retry %s] %s %s", attempt, method, url)
        try:
            if http_get and method == "GET":
                resp = http_get(url, headers=headers, timeout=timeout)
                if resp is None:
                    raise RequestException("Injected http_get returned None")
                if allow_non_2xx:
                    return resp
                resp.raise_for_status()
                return resp
            scraper = get_cloudscraper()
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
                except Exception as e:
                    logger.warning("Cloudscraper failed for %s: %s", url, e)
                    last_err = e
            logger.debug("[session] %s %s", method, url)
            resp = session.request(method, url, headers=headers, timeout=timeout)
            if allow_non_2xx:
                return resp
            resp.raise_for_status()
            return resp
        except RequestException as e:
            last_err = e
            err_s = str(e)
            try:
                status = getattr(getattr(e, "response", None), "status_code", None)
            except Exception:
                status = None
            should_try_cf = (status in (403, 429, 503)) or (
                status is None
                and any(
                    tok in err_s.lower()
                    for tok in ["forbidden", "blocked", "cloudflare"]
                )
            )
            if (
                not cf_fallback_attempted
                and method == "GET"
                and should_try_cf
            ):
                try:
                    scraper = get_cloudscraper()
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
                except Exception as ce:
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
            break
    logger.warning("Requests failed for %s: %s", url, last_err)
    return None


__all__ = ["http_request", "session"]
