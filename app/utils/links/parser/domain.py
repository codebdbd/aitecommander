"""Domain normalization and TTL helpers."""

from __future__ import annotations

import random
from typing import Any

from .constants import DEFAULT_JITTER_PCT


def base_domain(host: str) -> str:
    """Return registrable base domain (eTLD+1) for a host.
    Uses tldextract if available; otherwise falls back to smart domain extraction.
    """
    h = (host or "").strip().lower()
    if h.startswith("www."):
        h = h[4:]
    try:
        import tldextract  # type: ignore

        ext = tldextract.extract(h)
        top_domain = getattr(ext, "top_domain_under_public_suffix", "")
        if top_domain:
            return top_domain
        registered_domain = getattr(ext, "registered_domain", "")
        if registered_domain:
            return registered_domain
    except Exception:
        pass
    
    # Smart fallback for common second-level TLDs
    parts = [p for p in h.split(".") if p]
    if len(parts) < 2:
        return h
    
    # Common second-level TLDs (e.g., .com.ua, .co.uk, .gov.au)
    second_level_tlds = {
        'com', 'co', 'org', 'net', 'edu', 'gov', 'ac', 'mil', 
        'sch', 'med', 'nom', 'gen', 'ltd', 'plc'
    }
    
    # If last part is 2 chars (country code) and second-to-last is in common TLDs
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in second_level_tlds:
        # e.g., google.com.ua -> take last 3 parts
        return ".".join(parts[-3:])
    
    # Default: take last 2 parts
    return ".".join(parts[-2:])


def cfg_ttl(config: Any, key: str, default_val: int) -> int:
    try:
        v = getattr(config, key, default_val)
        return int(v)
    except Exception:
        return default_val


def apply_jitter(ttl: int, config: Any) -> int:
    try:
        pct = float(getattr(config, "CACHE_JITTER_PCT", DEFAULT_JITTER_PCT))
    except Exception:
        pct = DEFAULT_JITTER_PCT
    if pct <= 0:
        return ttl
    delta = ttl * pct
    return max(1, int(ttl + random.uniform(-delta, delta)))


__all__ = ["base_domain", "cfg_ttl", "apply_jitter"]
