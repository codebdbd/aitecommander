from __future__ import annotations

from types import SimpleNamespace

from app.utils.ui.menu_builders.category_menu_builder import CategoryMenuBuilder
from app.utils.ui.menu_builders.links_menu_builder import LinksMenuBuilder


class _FakeAction:
    def __init__(self) -> None:
        self.enabled = None

    def setEnabled(self, value: bool) -> None:
        self.enabled = value


class _FakeActionBuilder:
    def create(self, *_args, **_kwargs) -> _FakeAction:
        return _FakeAction()


def _main_window_stub() -> SimpleNamespace:
    def _action(enabled: bool = True) -> SimpleNamespace:
        return SimpleNamespace(isEnabled=lambda: enabled)

    action_controller = SimpleNamespace(
        update_action_states=lambda: None,
        cut_current=lambda: None,
        copy_current=lambda: None,
        paste_current=lambda: None,
        delete_current=lambda: None,
        select_all_current=lambda: None,
        undo_current=lambda: None,
        redo_current=lambda: None,
    )
    return SimpleNamespace(
        settings=SimpleNamespace(get_theme=lambda: "dark"),
        action_controller=action_controller,
        cut_action=_action(True),
        copy_action=_action(True),
        paste_action=_action(False),
        delete_action=_action(True),
        select_all_action=_action(True),
        undo_action=_action(True),
        redo_action=_action(False),
        share_category=lambda _item_id: None,
        links_actions=SimpleNamespace(show_link_dialog=lambda **_kwargs: None),
        get_current_category_id=lambda: 1,
    )


def test_category_menu_builder_creates_fresh_context_actions(monkeypatch) -> None:
    main_window = _main_window_stub()
    builder = CategoryMenuBuilder(SimpleNamespace(), main_window)
    builder.actions = _FakeActionBuilder()
    monkeypatch.setattr(builder, "_get_icon", lambda _name: None)

    action = builder._create_context_action(
        "Delete", "delete_current", "global.delete", "delete", "delete_action"
    )

    assert action is not None
    assert action is not main_window.delete_action
    assert action.enabled is True


def test_links_menu_builder_creates_fresh_context_actions(monkeypatch) -> None:
    main_window = _main_window_stub()
    builder = LinksMenuBuilder(SimpleNamespace(), main_window)
    builder.actions = _FakeActionBuilder()
    monkeypatch.setattr(
        "app.utils.ui.menu_builders.links_menu_builder.get_menu_icon",
        lambda *_args, **_kwargs: None,
    )

    action = builder._create_context_action(
        "Paste", "paste_current", "edit.paste", "paste", "paste_action"
    )

    assert action is not None
    assert action is not main_window.paste_action
    assert action.enabled is False
