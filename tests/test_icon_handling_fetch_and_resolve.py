import types

import app.controllers.ui.structure.icon_handling as ih_mod
from app.controllers.ui.structure.icon_handling import IconHandling


class _DummyController:
    def __init__(self):
        # tree not used in this unit
        self.tree = types.SimpleNamespace(model=lambda: None)
        self.business = types.SimpleNamespace(
            get_sections_bulk=lambda ids: [{"id": i, "icon_path": f"s-{i}"} for i in ids],
            get_categories_bulk=lambda ids: [{"id": i, "icon_path": f"c-{i}"} for i in ids],
        )


def test_fetch_and_resolve_returns_paths_and_respects_token(monkeypatch):
    ctrl = _DummyController()
    ih = IconHandling(ctrl)

    # Patch resolver to prefix with 'resolved:'
    monkeypatch.setattr(
        ih_mod,
        "resolve_icon_for_link",
        lambda d: f"resolved:{d['type']}:{d['icon_path']}",
    )

    # Valid token case
    token = ih._icon_task_token + 1
    res = ih._fetch_and_resolve(token, {1, 2}, {101})
    assert res is not None
    tok, sec_map, cat_map = res
    assert tok == token
    assert sec_map[1].startswith("resolved:"), "section path must be resolved"
    assert cat_map[101].startswith("resolved:"), "category path must be resolved"

    # Stale token case: simulate concurrent newer task
    # Increase global token to simulate obsolescence
    ih._icon_task_token = token + 1
    res2 = ih._fetch_and_resolve(token, {3}, {201})
    assert res2 is None, "stale token results must be ignored"
