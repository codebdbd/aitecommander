import types

# Тесты для LinkDialog хелперов
from app.views.dialogs.link_dialog.link_dialog import LinkDialog
# Тесты для HierarchyMixin хелперов
from app.views.dialogs.link_dialog.handlers_mixins.hierarchy_mixin import HierarchyMixin


class ComboMock:
    def __init__(self, items=None, current_index=-1):
        # items: list of tuples (text, data)
        self.items = items or []
        self._current_index = current_index
        self.calls = []

    def findData(self, data):
        for idx, (_, d) in enumerate(self.items):
            if d == data:
                return idx
        return -1

    def setCurrentIndex(self, idx):
        self._current_index = idx
        self.calls.append(("setCurrentIndex", idx))

    def currentIndex(self):
        return self._current_index

    def count(self):
        return len(self.items)

    # Для тестов HierarchyMixin._add_with_optional_icon
    def addItem(self, *args):
        self.calls.append(("addItem", args))


class DummyLinkDialog(LinkDialog):
    """Создаём инстанс без вызова __init__, чтобы тестировать приватные хелперы."""

    @classmethod
    def make(cls):
        obj = LinkDialog.__new__(LinkDialog)
        return obj


class DummyHandlers(HierarchyMixin):
    def __init__(self):
        # Минимально достаточный объект для методов миксина (не используется в тестируемых методах)
        self.dialog = types.SimpleNamespace(ui=None, dialog_controller=None)


# ---------------- LinkDialog helpers -----------------

def test_set_index_by_data_found():
    dlg = DummyLinkDialog.make()
    combo = ComboMock(items=[("A", 1), ("B", 2), ("C", 3)], current_index=-1)

    changed = dlg._set_index_by_data(combo, 2)

    assert changed is True
    assert combo.currentIndex() == 1
    assert ("setCurrentIndex", 1) in combo.calls


def test_set_index_by_data_not_found_and_none():
    dlg = DummyLinkDialog.make()
    combo = ComboMock(items=[("A", 1)], current_index=-1)

    changed_none = dlg._set_index_by_data(combo, None)
    changed_missing = dlg._set_index_by_data(combo, 999)

    assert changed_none is False
    assert changed_missing is False
    # индекс не менялся
    assert combo.currentIndex() == -1


def test_select_first_if_unset_sets_first():
    dlg = DummyLinkDialog.make()
    combo = ComboMock(items=[("A", 1), ("B", 2)], current_index=-1)

    changed = dlg._select_first_if_unset(combo)

    assert changed is True
    assert combo.currentIndex() == 0


def test_select_first_if_unset_noop_when_already_selected():
    dlg = DummyLinkDialog.make()
    combo = ComboMock(items=[("A", 1)], current_index=0)

    changed = dlg._select_first_if_unset(combo)

    assert changed is False
    assert combo.currentIndex() == 0


def test_resolve_and_apply_icon_when_exists(monkeypatch):
    dlg = DummyLinkDialog.make()

    # Заглушка кнопки и ui.get_widget
    icon_btn = object()
    dlg.ui = types.SimpleNamespace(get_widget=lambda name: icon_btn)

    # Патчим импортированные в link_dialog символы
    import app.views.dialogs.link_dialog.link_dialog as ld

    calls = {"set_icon": []}

    def fake_resolve(link_dict):
        return "C:/icons/ok.png"

    def fake_exists(self):
        return True

    def fake_set_icon(button, path):
        calls["set_icon"].append((button, path))

    monkeypatch.setattr(ld, "resolve_icon_for_link", fake_resolve)
    from pathlib import Path as _Path
    monkeypatch.setattr(_Path, "exists", fake_exists, raising=True)
    monkeypatch.setattr(ld, "set_icon_to_button", fake_set_icon)

    resolved, exists = dlg._resolve_and_apply_icon("web", "ok.png")

    assert exists is True
    assert resolved.endswith("ok.png")
    assert calls["set_icon"] == [(icon_btn, resolved)]


def test_resolve_and_apply_icon_when_missing(monkeypatch):
    dlg = DummyLinkDialog.make()

    # Заглушка кнопки и ui.get_widget
    icon_btn = object()
    dlg.ui = types.SimpleNamespace(get_widget=lambda name: icon_btn)

    import app.views.dialogs.link_dialog.link_dialog as ld

    calls = {"set_icon": []}

    def fake_resolve(link_dict):
        return "C:/icons/missing.png"

    def fake_exists(self):
        return False

    def fake_set_icon(button, path):
        calls["set_icon"].append((button, path))

    monkeypatch.setattr(ld, "resolve_icon_for_link", fake_resolve)
    from pathlib import Path as _Path
    monkeypatch.setattr(_Path, "exists", fake_exists, raising=True)
    monkeypatch.setattr(ld, "set_icon_to_button", fake_set_icon)

    resolved, exists = dlg._resolve_and_apply_icon("web", "missing.png")

    assert exists is False
    assert resolved.endswith("missing.png")
    assert calls["set_icon"] == []


def test_set_initial_icon_warning_branch(monkeypatch):
    """Проверяем, что при exists=False показывается предупреждение ровно один раз.

    Мокаем _resolve_and_apply_icon и show_warning, убеждаемся в корректных аргументах.
    """
    dlg = DummyLinkDialog.make()
    # _set_initial_icon использует self.link_type и self.icon_name
    dlg.link_type = "web"
    dlg.icon_name = "missing.png"

    # Возвращаем фиксированные значения: путь и exists=False
    monkeypatch.setattr(dlg, "_resolve_and_apply_icon", lambda lt, iname: ("C:/icons/missing.png", False))

    calls = {"warn": []}

    def fake_show_warning(msg, title, *, informative_text=None, details=None):
        calls["warn"].append({
            "msg": msg,
            "title": title,
            "informative_text": informative_text,
            "details": details,
        })

    monkeypatch.setattr(dlg, "show_warning", fake_show_warning)

    # Вызов
    dlg._set_initial_icon()

    # Проверки
    assert len(calls["warn"]) == 1
    w = calls["warn"][0]
    assert "Иконка по умолчанию не найдена." in w["msg"]
    assert "Проблема с иконкой" in w["title"]
    assert "Кнопка будет отображаться без иконки" in (w["informative_text"] or "")
    assert (w["details"] or "").endswith("C:/icons/missing.png") or "missing.png" in (w["details"] or "")


# ---------------- HierarchyMixin helpers -----------------

def test_extract_icon_path_from_dict():
    h = DummyHandlers()
    assert h._extract_icon_path({"icon_path": "x/y.png"}) == "x/y.png"
    assert h._extract_icon_path({}) == ""


def test_extract_icon_path_from_mapping_like():
    class MappingLike:
        def __init__(self, value):
            self._value = value

        def keys(self):
            return ["icon_path"] if self._value is not None else []

        def __getitem__(self, key):
            if key == "icon_path":
                return self._value
            raise KeyError(key)

    h = DummyHandlers()
    item = MappingLike("a/b.svg")
    assert h._extract_icon_path(item) == "a/b.svg"

    item2 = MappingLike(None)
    assert h._extract_icon_path(item2) == ""


def test_add_with_optional_icon(monkeypatch):
    h = DummyHandlers()
    combo = ComboMock()

    # Когда make_icon возвращает объект (истинное значение) — должен вызываться вариант с иконкой
    from app.views.dialogs.link_dialog.handlers_mixins import hierarchy_mixin as hm

    monkeypatch.setattr(hm, "make_icon", lambda p: object() if p == "has" else None)

    h._add_with_optional_icon(combo, "Name1", 1, "has")
    h._add_with_optional_icon(combo, "Name2", 2, "")

    # Первая запись: 3 аргумента (icon, name, id); вторая — 2 аргумента (name, id)
    assert combo.calls[0][0] == "addItem"
    assert len(combo.calls[0][1]) == 3
    assert combo.calls[1][0] == "addItem"
    assert len(combo.calls[1][1]) == 2
