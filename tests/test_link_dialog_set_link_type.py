import pytest

from app.views.dialogs.link_dialog.link_dialog_handlers import LinkDialogHandlers


class FakeButton:
    def __init__(self, link_type):
        self._props = {"link_type": link_type}
        self.checked = False

    def property(self, name):
        return self._props.get(name)

    def setChecked(self, value):
        self.checked = bool(value)


class FakeButtonGroup:
    def __init__(self, buttons):
        self._buttons = buttons

    def buttons(self):
        return list(self._buttons)


class FakeUI:
    def __init__(self, buttons):
        self.widgets = {"type_group": FakeButtonGroup(buttons)}

    def get_widget(self, name):  # not used in these tests
        return self.widgets.get(name)


class FakeDialog:
    def __init__(self, link_types, buttons):
        self.link_types = link_types
        self.ui = FakeUI(buttons)
        self.link_type = None


@pytest.mark.parametrize(
    "available_types,requested,should_call",
    [
        ([("web", "Веб"), ("file", "Файл")], "web", True),
        (["web", "file"], "file", True),  # допускаем форму как последовательность кодов
        ([("web", "Веб")], "program", False),
    ],
)
def test_set_link_type_valid_and_invalid(monkeypatch, available_types, requested, should_call):
    buttons = [FakeButton("web"), FakeButton("file"), FakeButton("program")]
    dialog = FakeDialog(available_types, buttons)
    handlers = LinkDialogHandlers(dialog)

    called = {"flag": False, "arg": None}
    def fake_on_type_changed(arg):
        called["flag"] = True
        called["arg"] = arg
        dialog.link_type = arg

    # подменяем тяжёлую логику на заглушку
    monkeypatch.setattr(handlers, "on_type_changed", fake_on_type_changed)

    handlers.set_link_type(requested)

    assert called["flag"] is should_call
    if should_call:
        assert called["arg"] == requested
        # найдём кнопку с этим типом и проверим, что она отмечена
        target_btn = next(b for b in buttons if b.property("link_type") == requested)
        assert target_btn.checked is True
    else:
        # ни одна кнопка не должна быть отмечена
        assert all(not b.checked for b in buttons)


def test_set_link_type_missing_link_types(monkeypatch):
    buttons = [FakeButton("web"), FakeButton("file")]
    dialog = FakeDialog(link_types=None, buttons=buttons)
    handlers = LinkDialogHandlers(dialog)

    called = {"flag": False}
    monkeypatch.setattr(handlers, "on_type_changed", lambda *_: called.update(flag=True))

    # не должен упасть и не должен вызвать _on_type_changed
    handlers.set_link_type("web")

    assert called["flag"] is False
    assert all(not b.checked for b in buttons)
