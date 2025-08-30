import types

from app.utils.links.parser import favicon_cache as fc_module
from app.utils.links.parser.favicon_cache import favicon_cache
from app.utils.links.parser.constants import SHORT_NEGATIVE_TTL


def test_default_icon_resolver_called_once(monkeypatch):
    calls = {"n": 0}

    def _resolver(payload):
        calls["n"] += 1
        return "__DEFAULT_ICON__"

    # Reset cached value and monkeypatch resolver
    favicon_cache._default_icon_cached = None  # type: ignore[attr-defined]
    monkeypatch.setattr(fc_module, "resolve_icon_for_link", _resolver, raising=True)

    # First call should invoke resolver
    v1 = favicon_cache._get_default_icon()  # type: ignore[attr-defined]
    # Second call should use cached value, not invoking resolver again
    v2 = favicon_cache._get_default_icon()  # type: ignore[attr-defined]

    assert v1 == "__DEFAULT_ICON__" and v2 == "__DEFAULT_ICON__"
    assert calls["n"] == 1


def test_compute_effective_ttl_uses_short_for_default_icon(monkeypatch):
    # Ensure cached default icon is the known value
    favicon_cache._default_icon_cached = "__DEFAULT_ICON__"  # type: ignore[attr-defined]

    # Item without explicit ttl and with default icon -> SHORT_NEGATIVE_TTL
    ttl = favicon_cache._compute_effective_ttl({"icon": "__DEFAULT_ICON__"})  # type: ignore[attr-defined]
    assert float(ttl) == float(SHORT_NEGATIVE_TTL)

    # Item with explicit ttl should use it
    ttl2 = favicon_cache._compute_effective_ttl({"icon": "x.png", "ttl": 123})  # type: ignore[attr-defined]
    assert ttl2 == 123
