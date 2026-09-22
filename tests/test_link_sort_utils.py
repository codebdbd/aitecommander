from app.views.widgets.link.columns import LinkTableColumn
from app.views.widgets.link.sort_utils import (
    link_sort_key,
    normalize_last_used,
    sorted_links,
)


def _ids(links: list[dict]) -> list[int]:
    return [int(link["id"]) for link in links]


def test_sort_by_name_casefolds() -> None:
    links = [
        {"id": 1, "name": "zulu"},
        {"id": 2, "name": "Alpha"},
        {"id": 3, "name": "bravo"},
    ]

    result = sorted_links(links, int(LinkTableColumn.NAME))

    assert _ids(result) == [2, 3, 1]


def test_sort_by_order_uses_position() -> None:
    links = [
        {"id": 1, "position": 2},
        {"id": 2, "position": 0},
        {"id": 3, "position": 1},
    ]

    result = sorted_links(links, int(LinkTableColumn.ORDER))

    assert _ids(result) == [2, 3, 1]


def test_sort_by_launch_keeps_never_bucket_alphabetical() -> None:
    links = [
        {"id": 1, "name": "Zulu", "last_used": ""},
        {"id": 2, "name": "Alpha", "last_used": None},
        {"id": 3, "name": "Used", "last_used": "2026-01-01T10:00:00"},
    ]

    result = sorted_links(links, int(LinkTableColumn.LAUNCH))

    assert _ids(result) == [2, 1, 3]


def test_sort_by_launch_descending_matches_model_semantics() -> None:
    links = [
        {"id": 1, "name": "Never", "last_used": ""},
        {"id": 2, "name": "Older", "last_used": "2026-01-01T10:00:00"},
        {"id": 3, "name": "Newer", "last_used": "2026-02-01T10:00:00"},
    ]

    result = sorted_links(links, int(LinkTableColumn.LAUNCH), descending=True)

    assert _ids(result) == [3, 2, 1]


def test_sort_by_type_uses_supplied_display_label() -> None:
    links = [
        {"id": 1, "type": "web"},
        {"id": 2, "type": "program"},
        {"id": 3, "type": "file"},
    ]
    labels = {"web": "Web link", "program": "Application", "file": "File"}

    result = sorted_links(
        links,
        int(LinkTableColumn.TYPE),
        type_label_getter=lambda link: labels[str(link["type"])],
    )

    assert _ids(result) == [2, 3, 1]


def test_sort_unknown_column_falls_back_to_stable_id() -> None:
    links = [{"id": 3}, {"id": 1}, {"id": 2}]

    result = sorted_links(links, 999)

    assert _ids(result) == [1, 2, 3]


def test_sorted_links_does_not_mutate_input_list() -> None:
    links = [{"id": 2, "name": "b"}, {"id": 1, "name": "a"}]

    result = sorted_links(links, int(LinkTableColumn.NAME))

    assert _ids(result) == [1, 2]
    assert _ids(links) == [2, 1]


def test_normalize_last_used_handles_invalid_values() -> None:
    assert normalize_last_used(None) == float("-inf")
    assert isinstance(normalize_last_used("not-a-date"), float)


def test_link_sort_key_falls_back_to_original_index_without_id() -> None:
    assert link_sort_key({"name": "x"}, 999, original_index=7) == 7
