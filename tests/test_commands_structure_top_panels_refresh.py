from __future__ import annotations

from types import SimpleNamespace

from app.controllers.ui.undo.commands_structure import _request_top_panels_refresh
from app.controllers.ui.undo.commands_structure import _invalidate_links_business_cache


def test_request_top_panels_refresh_prefers_direct_favorites_refresh():
    calls: list[tuple[str, int]] = []
    controller = SimpleNamespace(
        refresh_favorites=lambda: calls.append(("favorites_now", 0)),
        request_refresh=lambda delay=0: calls.append(("refresh", delay)),
        request_favorites_refresh=lambda delay=0: calls.append(("favorites", delay)),
    )
    window = SimpleNamespace(top_panels_controller=controller)

    _request_top_panels_refresh(window)

    assert calls == [("favorites_now", 0)]


def test_request_top_panels_refresh_falls_back_to_favorites_only():
    calls: list[tuple[str, int]] = []
    controller = SimpleNamespace(
        request_favorites_refresh=lambda delay=0: calls.append(("favorites", delay))
    )
    window = SimpleNamespace(top_panels_controller=controller)

    _request_top_panels_refresh(window)

    assert calls == [("favorites", 0)]


def test_request_top_panels_refresh_falls_back_to_full_refresh():
    calls: list[tuple[str, int]] = []
    controller = SimpleNamespace(
        request_refresh=lambda delay=0: calls.append(("refresh", delay))
    )
    window = SimpleNamespace(top_panels_controller=controller)

    _request_top_panels_refresh(window)

    assert calls == [("refresh", 0)]


def test_invalidate_links_business_cache_prefers_public_method():
    calls: list[str] = []
    links_business = SimpleNamespace(invalidate_cache=lambda: calls.append("public"))
    window = SimpleNamespace(links_business=links_business)

    _invalidate_links_business_cache(window)

    assert calls == ["public"]


def test_invalidate_links_business_cache_falls_back_to_private_method():
    calls: list[str] = []
    links_business = SimpleNamespace(_invalidate_cache=lambda: calls.append("private"))
    window = SimpleNamespace(links_business=links_business)

    _invalidate_links_business_cache(window)

    assert calls == ["private"]
