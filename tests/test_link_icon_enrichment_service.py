from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

from app.controllers.ui.links.icon_enrichment_service import (
    LinkIconEnrichmentService,
    _FetchIconTask,
    _can_replace_icon,
)


class _MainWindow:
    pass


def test_default_and_missing_icons_can_be_replaced() -> None:
    def _resolve(link: dict) -> str:
        value = str(link.get("icon_path") or "")
        if not value or value in {"web.png", "missing-custom.png"}:
            return "C:/icons/web.png"
        return value

    with patch(
        "app.controllers.ui.links.icon_enrichment_service.resolve_icon_for_link",
        side_effect=_resolve,
    ):
        assert _can_replace_icon({"type": "web", "icon_path": ""})
        assert _can_replace_icon({"type": "web", "icon_path": "web.png"})
        assert _can_replace_icon(
            {"type": "web", "icon_path": "missing-custom.png"}
        )
        assert not _can_replace_icon(
            {"type": "web", "icon_path": "C:/icons/user-choice.png"}
        )


def test_enqueue_deduplicates_by_link_generation() -> None:
    main = _MainWindow()
    service = LinkIconEnrichmentService(main)
    scheduler = Mock()

    with (
        patch(
            "app.controllers.ui.links.icon_enrichment_service.get_task_scheduler",
            return_value=scheduler,
        ),
        patch(
            "app.controllers.ui.links.icon_enrichment_service._can_replace_icon",
            return_value=True,
        ),
    ):
        assert service.enqueue(
            {"id": 7, "url": "https://one.example", "type": "web"}
        )
        assert service.enqueue(
            {"id": 7, "url": "https://two.example", "type": "web"}
        )

    first = scheduler.submit_task.call_args_list[0].args[0]
    second = scheduler.submit_task.call_args_list[1].args[0]
    assert isinstance(first, _FetchIconTask)
    assert isinstance(second, _FetchIconTask)
    assert first._generation == 1
    assert second._generation == 2
    assert first._link_type == "web"
    assert second._link_type == "web"


def test_enqueue_supports_program_links() -> None:
    main = _MainWindow()
    service = LinkIconEnrichmentService(main)
    scheduler = Mock()

    with (
        patch(
            "app.controllers.ui.links.icon_enrichment_service.get_task_scheduler",
            return_value=scheduler,
        ),
        patch(
            "app.controllers.ui.links.icon_enrichment_service._can_replace_icon",
            return_value=True,
        ),
    ):
        assert service.enqueue(
            {"id": 11, "url": r"C:\\Tools\\App.exe", "type": "program"}
        )

    task = scheduler.submit_task.call_args.args[0]
    assert isinstance(task, _FetchIconTask)
    assert task._link_type == "program"


def test_enqueue_allows_name_only_enrichment_for_web_links() -> None:
    main = _MainWindow()
    service = LinkIconEnrichmentService(main)
    scheduler = Mock()

    with (
        patch(
            "app.controllers.ui.links.icon_enrichment_service.get_task_scheduler",
            return_value=scheduler,
        ),
        patch(
            "app.controllers.ui.links.icon_enrichment_service._can_replace_icon",
            return_value=False,
        ),
    ):
        assert service.enqueue(
            {
                "id": 12,
                "url": "https://example.com/path",
                "type": "web",
                "name": "path",
                "icon_path": "C:/icons/user-choice.png",
            }
        )

    task = scheduler.submit_task.call_args.args[0]
    assert isinstance(task, _FetchIconTask)
    assert task._link_type == "web"


def test_completed_icon_is_persisted_and_published(tmp_path: Path) -> None:
    icon = tmp_path / "site.png"
    icon.write_bytes(b"icon")
    current = {
        "id": 8,
        "url": "https://example.com",
        "type": "web",
        "icon_path": "web.png",
        "category_id": 3,
        "name": "Example",
    }
    links = Mock()
    links.get_link_by_id.return_value = current
    link_updated = Mock()
    links_business = Mock(links=links, link_updated=link_updated)
    link_operations = Mock()
    main = _MainWindow()
    main.links_business = links_business
    main.link_operations = link_operations
    service = LinkIconEnrichmentService(main)
    service._generation_by_link[8] = 1

    def _run_now(task, **kwargs):
        kwargs["on_finished"](task())

    with (
        patch(
            "app.controllers.ui.links.icon_enrichment_service.run_db",
            side_effect=_run_now,
        ),
        patch(
            "app.controllers.ui.links.icon_enrichment_service._can_replace_icon",
            return_value=True,
        ),
    ):
        service._on_network_finished(
            {
                "link_id": 8,
                "url": "https://example.com",
                "link_type": "web",
                "generation": 1,
                "icon_path": str(icon),
            }
        )

    saved = links.create_or_update_link.call_args.args[0]
    assert saved["icon_path"] == "site.png"
    link_updated.emit.assert_called_once_with(current)
    link_operations.emit_link_saved.assert_called_once_with(current)


def test_completed_title_updates_dropped_web_name(tmp_path: Path) -> None:
    icon = tmp_path / "site.png"
    icon.write_bytes(b"icon")
    current = {
        "id": 10,
        "url": "https://example.com",
        "type": "web",
        "icon_path": "web.png",
        "category_id": 3,
        "name": "example.com",
    }
    links = Mock()
    links.get_link_by_id.return_value = current
    link_updated = Mock()
    links_business = Mock(links=links, link_updated=link_updated)
    link_operations = Mock()
    main = _MainWindow()
    main.links_business = links_business
    main.link_operations = link_operations
    service = LinkIconEnrichmentService(main)
    service._generation_by_link[10] = 1

    def _run_now(task, **kwargs):
        kwargs["on_finished"](task())

    with (
        patch(
            "app.controllers.ui.links.icon_enrichment_service.run_db",
            side_effect=_run_now,
        ),
        patch(
            "app.controllers.ui.links.icon_enrichment_service._can_replace_icon",
            return_value=False,
        ),
    ):
        service._on_network_finished(
            {
                "link_id": 10,
                "url": "https://example.com",
                "link_type": "web",
                "generation": 1,
                "title": "Example Title",
                "icon_path": str(icon),
            }
        )

    saved = links.create_or_update_link.call_args.args[0]
    assert saved["name"] == "Example Title"


def test_stale_url_does_not_overwrite_icon(tmp_path: Path) -> None:
    icon = tmp_path / "old-site.png"
    icon.write_bytes(b"icon")
    links = Mock()
    links.get_link_by_id.return_value = {
        "id": 9,
        "url": "https://new.example",
        "type": "web",
        "icon_path": "web.png",
    }
    main = _MainWindow()
    main.links_business = Mock(links=links)
    service = LinkIconEnrichmentService(main)
    service._generation_by_link[9] = 1

    def _run_now(task, **kwargs):
        kwargs["on_finished"](task())

    with patch(
        "app.controllers.ui.links.icon_enrichment_service.run_db",
        side_effect=_run_now,
    ):
        service._on_network_finished(
            {
                "link_id": 9,
                "url": "https://old.example",
                "link_type": "web",
                "generation": 1,
                "icon_path": str(icon),
            }
        )

    links.create_or_update_link.assert_not_called()
