"""Icon fallback strategies: www/non-www variants, Google Favicon API, failed domain cache."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .constants import MEDIUM_NEGATIVE_TTL, logger
from .domain import base_domain

if TYPE_CHECKING:
    pass

# Thread-safe cache for failed domains (403/404/SSL errors)
_FAILED_DOMAINS_CACHE: OrderedDict[str, tuple[int, float]] = OrderedDict()
_FAILED_CACHE_LOCK = threading.Lock()
_FAILED_CACHE_MAX_SIZE = 1000


def _normalize_domain(url: str) -> str:
    """Extract normalized domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        return base_domain(domain.lower().strip())
    except Exception:
        return base_domain(url.lower().strip())


def is_domain_failed(url: str) -> bool:
    """Check if domain is in failed cache and not expired.
    
    Args:
        url: URL to check
        
    Returns:
        True if domain recently failed with 403/404/SSL error
    """
    domain = _normalize_domain(url)
    if not domain:
        return False
    
    with _FAILED_CACHE_LOCK:
        if domain in _FAILED_DOMAINS_CACHE:
            status, timestamp = _FAILED_DOMAINS_CACHE[domain]
            # Check if cache entry is still valid
            if time.time() - timestamp < MEDIUM_NEGATIVE_TTL:
                logger.debug("[failed_cache] Domain %s is cached as failed (status=%s)", domain, status)
                return True
            else:
                # Expired, remove from cache
                del _FAILED_DOMAINS_CACHE[domain]
    
    return False


def mark_domain_failed(url: str, status_code: int) -> None:
    """Mark domain as failed in cache.
    
    Args:
        url: URL that failed
        status_code: HTTP status code (403, 404, etc.)
    """
    domain = _normalize_domain(url)
    if not domain:
        return
    
    with _FAILED_CACHE_LOCK:
        _FAILED_DOMAINS_CACHE[domain] = (status_code, time.time())
        # Limit cache size (LRU)
        while len(_FAILED_DOMAINS_CACHE) > _FAILED_CACHE_MAX_SIZE:
            _FAILED_DOMAINS_CACHE.popitem(last=False)
        
        logger.debug("[failed_cache] Marked domain %s as failed (status=%s)", domain, status_code)


def clear_domain_failed(url: str) -> None:
    """Remove domain from failed cache after a successful icon fetch/save."""
    domain = _normalize_domain(url)
    if not domain:
        return

    with _FAILED_CACHE_LOCK:
        _FAILED_DOMAINS_CACHE.pop(domain, None)


def get_www_variant(url: str) -> str | None:
    """Get www/non-www variant of URL.
    
    Args:
        url: Original URL
        
    Returns:
        Variant URL or None if not applicable
        
    Examples:
        https://example.com → https://www.example.com
        https://www.example.com → https://example.com
    """
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        
        domain = parsed.netloc.lower()
        
        # Skip if already has subdomain (other than www)
        parts = domain.split(".")
        if len(parts) > 2 and parts[0] != "www":
            return None
        
        # Toggle www
        if domain.startswith("www."):
            new_domain = domain[4:]  # Remove www.
        else:
            new_domain = f"www.{domain}"  # Add www.
        
        # Reconstruct URL
        variant = parsed._replace(netloc=new_domain).geturl()
        logger.debug("[www_variant] %s → %s", url, variant)
        return variant
        
    except Exception as e:
        logger.debug("[www_variant] Failed to create variant for %s: %s", url, e)
        return None


def try_google_favicon_api(domain: str, size: int = 128) -> str:
    """Get Google Favicon API URL for domain.
    
    Args:
        domain: Domain name (e.g., "example.com")
        size: Icon size (16, 32, 64, 128, 256)
        
    Returns:
        Google Favicon API URL
        
    Note:
        This is a fallback when direct icon download fails.
        Google's service is reliable but may return generic icons.
    """
    # Normalize domain
    domain = _normalize_domain(f"https://{domain}")
    if not domain:
        domain = "example.com"
    
    # Google Favicon API
    # sz parameter: 16, 32, 64, 128, 256
    url = f"https://www.google.com/s2/favicons?domain={domain}&sz={size}"
    logger.debug("[google_api] Fallback URL for %s: %s", domain, url)
    return url


__all__ = [
    "is_domain_failed",
    "mark_domain_failed",
    "clear_domain_failed",
    "get_www_variant",
    "try_google_favicon_api",
]
