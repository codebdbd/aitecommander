"""Pure sorting helpers for the links table."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from app.views.widgets.link.columns import LinkTableColumn, is_column, sort_key_for_column

TypeLabelGetter = Callable[[dict[str, Any]], str]


def normalize_last_used(value: Any) -> float:
    """Return a numeric timestamp for a last-used value."""
    from math import inf

    if value is None:
        return -inf
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        pass
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        pass
    try:
        return float(abs(hash(str(value))))
    except Exception:
        return -inf


def link_sort_key(
    link: dict[str, Any],
    column: int,
    *,
    original_index: int = 0,
    type_label_getter: TypeLabelGetter | None = None,
) -> Any:
    """Return a stable sort key for one link table row."""
    if is_column(column, LinkTableColumn.LAUNCH):
        last_used = link.get("last_used")
        if last_used in (None, ""):
            return (0, str(link.get("name", "")).casefold())
        return (1, normalize_last_used(last_used))

    type_label = type_label_getter(link) if type_label_getter is not None else ""
    simple_key = sort_key_for_column(column, link, type_label=type_label)
    if simple_key is not None:
        return simple_key

    link_id = link.get("id")
    if isinstance(link_id, (int, str)):
        try:
            return int(link_id)
        except ValueError:
            pass
    return original_index


def sorted_links(
    links: Sequence[dict[str, Any]],
    column: int,
    *,
    descending: bool = False,
    type_label_getter: TypeLabelGetter | None = None,
) -> list[dict[str, Any]]:
    """Return links sorted by a table column without mutating the input list."""
    indexed_links = list(enumerate(links))
    indexed_links.sort(
        key=lambda item: link_sort_key(
            item[1],
            column,
            original_index=item[0],
            type_label_getter=type_label_getter,
        ),
        reverse=descending,
    )
    return [item[1] for item in indexed_links]
