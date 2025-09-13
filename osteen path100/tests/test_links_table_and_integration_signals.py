import types

from app.controllers.ui.dialogs.link_operations_controller import (
    LinkOperationsController,
)
from app.controllers.ui.links.table_controller import LinksTableController
from app.controllers.ui.top_panels_controller import TopPanelsController


class LinksBusinessMock:
    def __init__(self):
        self.load_calls = []

    def load_links(self, category_id):
        self.load_calls.append(category_id)


class TableWidgetMock:
    def __init__(self):
        self.updated = []
        self.populated = []

    def update_link_by_id(self, link_dict):
        self.updated.append(link_dict)

    def populate(self, links, mode=None):
        self.populated.append((list(links), mode))


class FavWidgetMock:
    def __init__(self):
        self.favorites = None
        self.set_calls = 0

    def set_favorites(self, items):
        self.favorites = items
        self.set_calls += 1

    def clear_favorites(self):
        self.favorites = []

    def setVisible(self, _):
        pass


class RecentWidgetMock:
    def __init__(self, limit=None, max_items=None):
        self.recent = None
        self.set_calls = 0
        self.limit = limit
        self.max_items = max_items

    def set_recent_links(self, items):
        self.recent = items
        self.set_calls += 1

    def get_limit(self):
        # Совместимость: поддерживаем оба поля, выбирая приоритетно limit
        if isinstance(self.limit, int) and self.limit > 0:
            return self.limit
        if isinstance(self.max_items, int) and self.max_items > 0:
            return self.max_items
        return None


def make_link_ops():
    db = types.SimpleNamespace()
    undo = types.SimpleNamespace()
    main = types.SimpleNamespace()
    return LinkOperationsController(db, undo, main)


def test_links_table_controller_reacts_to_link_ops_signals():
    business = LinksBusinessMock()
    table = TableWidgetMock()
    main = types.SimpleNamespace(current_category_id=None)
    links_table = LinksTableController(
        main,
        table=table,
        links_business=business,
        category_provider=main,
    )

    link_ops = make_link_ops()

    link_ops.links_changed.connect(links_table.on_links_changed)
    link_ops.link_saved.connect(links_table.on_link_saved)
    link_ops.link_deleted.connect(links_table.on_link_deleted)

    link_ops.emit_links_changed(5)
    link_ops.emit_link_saved({"category_id": 7})
    link_ops.emit_link_deleted({"category_id": 9})

    assert business.load_calls == [5, 7, 9]


def test_integration_link_ops_to_top_panels_and_table(monkeypatch):
    # Поднимаем TopPanelsController и LinksTableController и соединяем с LinkOperationsController
    business = LinksBusinessMock()

    # Заглушим методы получения данных, чтобы TopPanelsController мог отработать
    def _fake_get_fav():
        return ["X"]

    def _fake_get_recent(limit):
        return [1] * int(limit)

    business.get_favorite_links = _fake_get_fav
    business.get_recent_links = _fake_get_recent

    fav = FavWidgetMock()
    recent = RecentWidgetMock(limit=3)
    top_ctrl = TopPanelsController(
        types.SimpleNamespace(),
        fav_widget=fav,
        recent_links_widget=recent,
        links_business=business,
    )

    table = TableWidgetMock()
    main2 = types.SimpleNamespace(current_category_id=None)
    links_table = LinksTableController(
        main2,
        table=table,
        links_business=business,
        category_provider=main2,
    )

    link_ops = make_link_ops()

    # Wiring как в setup: LinkOperations -> TopPanelsController, LinksTableController
    link_ops.favorites_changed.connect(top_ctrl.request_favorites_refresh)
    link_ops.recents_changed.connect(top_ctrl.request_recents_refresh)
    link_ops.links_changed.connect(links_table.on_links_changed)

    # Эмитим сигналы и вручную дожимаем таймауты дебаунса
    link_ops.emit_favorites_changed()
    link_ops.emit_recents_changed()
    link_ops.emit_links_changed(11)

    # Симулируем срабатывание timers TopPanelsController
    top_ctrl._on_fav_refresh_timeout()
    top_ctrl._on_recent_refresh_timeout()

    assert fav.set_calls == 1 and fav.favorites == ["X"]
    assert recent.set_calls == 1 and recent.recent == [1, 1, 1]
    assert business.load_calls == [11]
