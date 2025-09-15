from PyQt6.QtGui import QIcon

import app.controllers.ui.structure.icon_handling as ih_mod
from app.controllers.ui.structure.icon_handling import prepare_icons_snapshot


def test_prepare_icons_snapshot_empty_paths_set_empty_qicon(monkeypatch):
    # Resolver возвращает None для пустого пути
    monkeypatch.setattr(ih_mod, "resolve_icon_for_link", lambda d: None)
    # Создание иконки из None не вызывается, но на всякий случай вернём QIcon при не-пустом пути
    monkeypatch.setattr(ih_mod, "create_icon_from_path", lambda p: QIcon())

    data = [
        {"id": 1, "name": "Sec1", "icon_path": "", "categories": [
            {"id": 101, "name": "Cat1", "icon_path": ""}
        ]}
    ]

    out = prepare_icons_snapshot(data)
    assert isinstance(out, list) and len(out) == 1
    sec = out[0]
    assert isinstance(sec.get("icon"), QIcon) and sec.get("icon").isNull()
    cat = sec.get("categories")[0]
    assert isinstance(cat.get("icon"), QIcon) and cat.get("icon").isNull()
