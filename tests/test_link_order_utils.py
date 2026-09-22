from app.views.widgets.link.order_utils import (
    move_link_position,
    move_rows_for_drop,
    normalized_source_rows,
    renumber_link_positions,
)


def _links(count: int) -> list[dict]:
    return [{"id": index + 1, "name": f"Link {index + 1}", "position": index} for index in range(count)]


def _ids(links: list[dict]) -> list[int]:
    return [int(link["id"]) for link in links]


def _positions(links: list[dict]) -> list[int]:
    return [int(link["position"]) for link in links]


def test_move_first_item_to_middle() -> None:
    result = move_link_position(_links(5), 1, 3)

    assert result is not None
    assert result.moved
    assert _ids(result.links) == [2, 3, 1, 4, 5]
    assert _positions(result.links) == [0, 1, 2, 3, 4]


def test_move_middle_item_to_first() -> None:
    result = move_link_position(_links(5), 3, 1)

    assert result is not None
    assert result.moved
    assert _ids(result.links) == [3, 1, 2, 4, 5]
    assert _positions(result.links) == [0, 1, 2, 3, 4]


def test_move_last_item_to_first() -> None:
    result = move_link_position(_links(5), 5, 1)

    assert result is not None
    assert result.moved
    assert _ids(result.links) == [5, 1, 2, 3, 4]
    assert _positions(result.links) == [0, 1, 2, 3, 4]


def test_target_position_is_clamped_to_end() -> None:
    result = move_link_position(_links(4), 2, 99)

    assert result is not None
    assert result.moved
    assert _ids(result.links) == [1, 3, 4, 2]
    assert _positions(result.links) == [0, 1, 2, 3]


def test_invalid_target_position_is_rejected() -> None:
    assert move_link_position(_links(4), 2, 0) is None
    assert move_link_position(_links(4), 2, "bad") is None


def test_missing_link_id_is_rejected() -> None:
    assert move_link_position(_links(4), 999, 1) is None


def test_duplicate_positions_are_normalized_on_noop() -> None:
    links = [
        {"id": 1, "position": 0},
        {"id": 2, "position": 0},
        {"id": 3, "position": 7},
    ]

    result = move_link_position(links, 2, 2)

    assert result is not None
    assert not result.moved
    assert _ids(result.links) == [1, 2, 3]
    assert _positions(result.links) == [0, 1, 2]


def test_missing_positions_are_normalized() -> None:
    result = move_link_position([{"id": 1}, {"id": 2}, {"id": 3}], 3, 1)

    assert result is not None
    assert result.moved
    assert _ids(result.links) == [3, 1, 2]
    assert _positions(result.links) == [0, 1, 2]


def test_hundred_items_move_to_first() -> None:
    result = move_link_position(_links(100), 100, 1)

    assert result is not None
    assert result.moved
    assert _ids(result.links)[:4] == [100, 1, 2, 3]
    assert _ids(result.links)[-1] == 99
    assert _positions(result.links) == list(range(100))


def test_renumber_link_positions_does_not_mutate_input() -> None:
    links = [{"id": 1, "position": 9}, {"id": 2, "position": 9}]

    result = renumber_link_positions(links)

    assert _positions(result) == [0, 1]
    assert _positions(links) == [9, 9]


def test_normalized_source_rows_filters_invalid_and_duplicates() -> None:
    assert normalized_source_rows([3, -1, 3, 0, 9], 5) == [0, 3]


def test_drop_move_single_row_matches_table_semantics() -> None:
    result = move_rows_for_drop(_links(5), [1], 3)

    assert result is not None
    assert result.moved
    assert result.contiguous
    assert result.first == 1
    assert result.last == 1
    assert result.destination_child == 3
    assert _ids(result.links) == [1, 3, 2, 4, 5]
    assert _positions(result.links) == [0, 1, 2, 3, 4]


def test_drop_move_contiguous_range_matches_table_semantics() -> None:
    result = move_rows_for_drop(_links(5), [0, 1], 4)

    assert result is not None
    assert result.moved
    assert result.contiguous
    assert result.first == 0
    assert result.last == 1
    assert result.destination_child == 4
    assert _ids(result.links) == [3, 4, 1, 2, 5]
    assert _positions(result.links) == [0, 1, 2, 3, 4]


def test_drop_move_inside_same_contiguous_range_is_noop() -> None:
    result = move_rows_for_drop(_links(5), [1, 2], 2)

    assert result is not None
    assert not result.moved
    assert result.contiguous
    assert _ids(result.links) == [1, 2, 3, 4, 5]


def test_drop_move_sparse_rows_matches_table_semantics() -> None:
    result = move_rows_for_drop(_links(5), [0, 2], 5)

    assert result is not None
    assert result.moved
    assert not result.contiguous
    assert result.destination_child is None
    assert _ids(result.links) == [2, 4, 5, 1, 3]
    assert _positions(result.links) == [0, 1, 2, 3, 4]


def test_drop_move_rejects_empty_or_invalid_sources() -> None:
    assert move_rows_for_drop(_links(3), [], 1) is None
    assert move_rows_for_drop(_links(3), [9], 1) is None


def test_drop_move_clamps_target_row() -> None:
    result = move_rows_for_drop(_links(4), [1], 99)

    assert result is not None
    assert result.moved
    assert result.destination_child == 4
    assert _ids(result.links) == [1, 3, 4, 2]
