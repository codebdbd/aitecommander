from PyQt6.QtGui import QIcon

import app.controllers.ui.structure.icon_handling as ih_mod
from app.controllers.ui.structure.icon_handling import prepare_icons_snapshot


def test_prepare_icons_snapshot_uses_add_icon_for_sections_and_categories(monkeypatch):
    calls = {"section": 0, "category": 0}

    def _fake_add_icon(item, item_type):
        calls[item_type] += 1
        # имитируем добавление поля icon
        d = dict(item)
        d["icon"] = QIcon()
        return d

    monkeypatch.setattr(ih_mod, "_add_icon", _fake_add_icon)

    data = [
        {"id": 1, "name": "Sec1", "icon_path": "p1", "categories": [
            {"id": 101, "name": "Cat1", "icon_path": "cp1"},
            {"id": 102, "name": "Cat2", "icon_path": "cp2"},
        ]},
        {"id": 2, "name": "Sec2", "icon_path": "p2", "categories": []},
    ]

    out = prepare_icons_snapshot(data)

    # Проверяем, что _add_icon вызывался для 2 секций и 2 категорий
    assert calls["section"] == 2
    assert calls["category"] == 2

    # И что на выходе у всех есть поле icon
    assert all(isinstance(s.get("icon"), QIcon) for s in out)
    assert all(all(isinstance(c.get("icon"), QIcon) for c in s.get("categories", [])) for s in out)


def test_prepare_icons_snapshot_logs_and_keeps_item_on_add_icon_failure(monkeypatch, caplog):
    # Если _add_icon бросает неожиданно, элемент должен пройти без изменений (категория тоже)
    def _boom(item, item_type):
        raise RuntimeError("boom")

    monkeypatch.setattr(ih_mod, "_add_icon", _boom)

    caplog.set_level("ERROR")

    data = [{"id": 1, "name": "Sec1", "categories": [{"id": 101, "name": "Cat1"}]}]
    out = prepare_icons_snapshot(data)

    # В случае исключения, prepare_icons_snapshot оборачивает в try/except на категорию
    # и оставляет исходный элемент/категорию как есть
    assert isinstance(out, list) and len(out) == 1
    assert out[0].get("categories")[0].get("name") == "Cat1"
