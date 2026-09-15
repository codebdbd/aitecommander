from __future__ import annotations

from unittest.mock import Mock, patch

from app.controllers.ui.links.table_controller import LinksTableController


class _FakeTable:
    def populate(self, links: list[dict]) -> None:
        pass

    def update_link_by_id(self, link: dict) -> None:
        pass


class _FakeCategoryProvider:
    def __init__(self, category_id: int = 1):
        self.current_category_id = category_id


def test_on_links_loaded_triggers_background_enrichment() -> None:
    main = Mock()
    table = _FakeTable()
    table.populate = Mock()
    business = Mock()
    provider = _FakeCategoryProvider(category_id=42)

    controller = LinksTableController(
        main, table=table, links_business=business, category_provider=provider
    )

    sample_links = [
        {"id": 1, "url": "https://first.com", "type": "web"},
        {"id": 2, "url": "https://second.com", "type": "web"},
    ]

    with patch(
        "app.controllers.ui.links.icon_enrichment_service.enqueue_links_icon_enrichment"
    ) as mock_enqueue:
        controller.on_links_loaded(sample_links, category_id=42, task_id=1)

        table.populate.assert_called_once_with(sample_links)
        mock_enqueue.assert_called_once_with(main, sample_links)


def test_on_link_saved_with_icon_enrichment_skips_reload_on_category_mismatch() -> None:
    main = Mock()
    table = _FakeTable()
    table.update_link_by_id = Mock()
    business = Mock()
    # User is currently looking at category 99
    provider = _FakeCategoryProvider(category_id=99)

    controller = LinksTableController(
        main, table=table, links_business=business, category_provider=provider
    )
    controller.reload = Mock()

    # Link from category 42 was enriched in background
    payload = {
        "id": 10,
        "category_id": 42,
        "icon_path": "web_site.png",
        "_is_icon_enrichment": True,
    }

    controller.on_link_saved(payload)

    # Should NOT update row (because category is 42, not 99)
    table.update_link_by_id.assert_not_called()
    # Should NOT trigger reload (because it's background icon enrichment)
    controller.reload.assert_not_called()


def test_on_link_saved_with_icon_enrichment_updates_row_when_category_matches() -> None:
    main = Mock()
    table = _FakeTable()
    table.update_link_by_id = Mock()
    business = Mock()
    # User is currently looking at category 42
    provider = _FakeCategoryProvider(category_id=42)

    controller = LinksTableController(
        main, table=table, links_business=business, category_provider=provider
    )
    controller.reload = Mock()

    payload = {
        "id": 10,
        "category_id": 42,
        "icon_path": "web_site.png",
        "_is_icon_enrichment": True,
    }

    controller.on_link_saved(payload)

    # Directly updates row
    table.update_link_by_id.assert_called_once_with(payload)
    controller.reload.assert_not_called()
