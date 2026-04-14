from __future__ import annotations

from app.controllers.ui.top_panels_controller import TopPanelsController


def _build_controller_stub() -> TopPanelsController:
    controller = TopPanelsController.__new__(TopPanelsController)
    controller.refresh_calls = 0

    def _request_favorites_refresh(*_args, **_kwargs):
        controller.refresh_calls += 1

    controller.request_favorites_refresh = _request_favorites_refresh
    return controller


def test_link_updated_with_favorite_flag_requests_refresh():
    controller = _build_controller_stub()

    controller._on_link_updated_for_favorites({"id": 1, "is_favorite": True})

    assert controller.refresh_calls == 1


def test_link_updated_without_favorite_flag_skips_refresh():
    controller = _build_controller_stub()

    controller._on_link_updated_for_favorites({"id": 1, "name": "x"})

    assert controller.refresh_calls == 0


def test_link_deleted_requests_refresh():
    controller = _build_controller_stub()

    controller._on_link_deleted_for_favorites(123)

    assert controller.refresh_calls == 1


def test_link_batch_delete_requests_refresh_only_for_links():
    controller = _build_controller_stub()

    controller._on_items_batch_deleted_for_favorites("category", [1, 2])
    controller._on_items_batch_deleted_for_favorites("link", [3, 4])

    assert controller.refresh_calls == 1


def test_batch_updated_requests_refresh():
    controller = _build_controller_stub()

    controller._on_batch_updated_for_favorites(True)

    assert controller.refresh_calls == 1
