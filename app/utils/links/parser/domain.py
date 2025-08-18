"""Domain normalization and TTL helpers."""
from __future__ import annotations

import random
from typing import Any

from .constants import DEFAULT_JITTER_PCT


def base_domain(host: str) -> str:
    """Return registrable base domain (eTLD+1) for a host.
    Uses tldextract if available; otherwise falls back to last two labels.
    """
    h = (host or "").strip().lower()
    if h.startswith("www."):
        h = h[4:]
    try:
        import tldextract  # type: ignore
        ext = tldextract.extract(h)
        if ext.registered_domain:
            return ext.registered_domain
    except Exception:
        pass
    parts = [p for p in h.split('.') if p]
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return h


def cfg_ttl(config: Any, key: str, default_val: int) -> int:
    try:
        v = getattr(config, key, default_val)
        return int(v)
    except Exception:
        return default_val


def apply_jitter(ttl: int, config: Any) -> int:
    try:
        pct = float(getattr(config, 'CACHE_JITTER_PCT', DEFAULT_JITTER_PCT))
    except Exception:
        pct = DEFAULT_JITTER_PCT
    if pct <= 0:
        return ttl
    delta = ttl * pct
    return max(1, int(ttl + random.uniform(-delta, delta)))


__all__ = ["base_domain", "cfg_ttl", "apply_jitter"]
