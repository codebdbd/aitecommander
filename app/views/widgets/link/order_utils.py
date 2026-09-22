"""Pure ordering helpers for links table rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class LinkOrderResult:
    links: list[dict[str, Any]]
    moved: bool


@dataclass(frozen=True)
class RowDropMoveResult:
    links: list[dict[str, Any]]
    moved: bool
    source_rows: list[int]
    target_row: int
    contiguous: bool
    first: int | None = None
    last: int | None = None
    destination_child: int | None = None


def renumber_link_positions(links: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return shallow-copied links with contiguous zero-based positions."""
    renumbered: list[dict[str, Any]] = []
    for index, link in enumerate(links):
        item = dict(link)
        item["position"] = index
        renumbered.append(item)
    return renumbered


def has_contiguous_positions(links: Sequence[dict[str, Any]]) -> bool:
    """Return whether links already have contiguous zero-based positions."""
    for index, link in enumerate(links):
        try:
            if int(link.get("position", 0) or 0) != index:
                return False
        except Exception:
            return False
    return True


def are_contiguous_rows(rows: Sequence[int]) -> bool:
    """Return whether row indexes form one contiguous range."""
    return all(b - a == 1 for a, b in zip(rows, rows[1:]))


def normalized_source_rows(source_rows: Sequence[int], row_count: int) -> list[int]:
    """Return sorted unique source rows that are valid for ``row_count``."""
    return [row for row in sorted(set(source_rows)) if 0 <= row < row_count]


def move_link_position(
    links: Sequence[dict[str, Any]], link_id: Any, target_position: Any
) -> LinkOrderResult | None:
    """Move a link to a one-based position and renumber all links.

    Invalid link IDs or target positions return ``None``. Positions beyond the
    list bounds are clamped to the closest valid position.
    """
    try:
        requested = int(str(target_position).strip())
    except Exception:
        return None
    if requested <= 0:
        return None

    items = [dict(link) for link in links]
    if not items:
        return None

    source_index = -1
    for index, item in enumerate(items):
        if item.get("id") == link_id:
            source_index = index
            break
    if source_index < 0:
        return None

    target_index = max(0, min(requested - 1, len(items) - 1))
    moved = target_index != source_index
    if moved:
        item = items.pop(source_index)
        items.insert(target_index, item)
    elif has_contiguous_positions(items):
        return LinkOrderResult(items, moved=False)

    return LinkOrderResult(renumber_link_positions(items), moved=moved)


def move_rows_for_drop(
    links: Sequence[dict[str, Any]], source_rows: Sequence[int], target_row: int
) -> RowDropMoveResult | None:
    """Return row order after a table drag-and-drop move.

    The returned ``destination_child`` is the original-coordinate value expected
    by ``QAbstractItemModel.beginMoveRows`` for contiguous moves.
    """
    row_count = len(links)
    rows = normalized_source_rows(source_rows, row_count)
    if not rows:
        return None

    target = max(0, min(int(target_row), row_count))
    contiguous = len(rows) == 1 or are_contiguous_rows(rows)

    if contiguous:
        first = rows[0]
        last = rows[-1]
        destination_child = target
        if first < destination_child <= last + 1:
            return RowDropMoveResult(
                links=[dict(link) for link in links],
                moved=False,
                source_rows=rows,
                target_row=target,
                contiguous=True,
                first=first,
                last=last,
                destination_child=destination_child,
            )

        segment = [dict(link) for link in links[first : last + 1]]
        remaining = [dict(link) for index, link in enumerate(links) if not first <= index <= last]
        insert_at = destination_child
        if insert_at > first:
            insert_at -= last - first + 1
        insert_at = max(0, min(insert_at, len(remaining)))
        new_links = remaining[:insert_at] + segment + remaining[insert_at:]
        return RowDropMoveResult(
            links=renumber_link_positions(new_links),
            moved=True,
            source_rows=rows,
            target_row=target,
            contiguous=True,
            first=first,
            last=last,
            destination_child=destination_child,
        )

    row_set = set(rows)
    remaining = [dict(link) for index, link in enumerate(links) if index not in row_set]
    segment = [dict(links[index]) for index in rows]
    insert_at = max(0, min(target, len(remaining)))
    new_links = remaining[:insert_at] + segment + remaining[insert_at:]
    old_ids = [link.get("id") for link in links]
    new_ids = [link.get("id") for link in new_links]
    return RowDropMoveResult(
        links=renumber_link_positions(new_links),
        moved=old_ids != new_ids,
        source_rows=rows,
        target_row=target,
        contiguous=False,
    )
