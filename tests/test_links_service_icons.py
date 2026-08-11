from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.links_service import LinksService


def test_create_or_update_link_cleans_orphaned_previous_icon() -> None:
    repo = Mock()
    repo.get_link_by_id.return_value = {"id": 5, "icon_path": "custom-old.png"}
    repo.upsert_link.return_value = 5
    db = SimpleNamespace(links=repo, transaction=lambda: nullcontext())
    service = LinksService(db)
    service._cleanup_orphaned_icon = Mock()

    saved_id = service.create_or_update_link(
        {
            "id": 5,
            "category_id": 3,
            "name": "Example",
            "url": "https://example.com",
            "type": "web",
            "icon_path": "",
        }
    )

    assert saved_id == 5
    service._cleanup_orphaned_icon.assert_called_once_with("custom-old.png")


def test_resolve_link_id_prefers_repository_lookup_for_new_payload() -> None:
    repo = Mock()
    repo.get_link_by_name_url_args.return_value = None
    repo.get_link_by_unique_fields.return_value = {"id": 17}
    db = SimpleNamespace(links=repo, transaction=lambda: nullcontext())
    service = LinksService(db)

    resolved_id = service.resolve_link_id(
        {
            "category_id": 3,
            "name": "Example",
            "url": "https://example.com",
            "type": "web",
            "args": "",
        }
    )

    assert resolved_id == 17
