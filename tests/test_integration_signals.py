import logging
from types import SimpleNamespace

import pytest

from app.controllers.ui.category_tiles_controller import CategoryTilesController
from app.controllers.ui.dialogs.link_operations_controller import (
    LinkOperationsController,
)
from app.controllers.ui.links.table_controller import LinksTableController
from app.controllers.ui.top_panels_controller import TopPanelsController


class FavWidgetMock:
    def __init__(self):
        self.calls: list[tuple[str, list[dict]] | str] = []

    def set_favorites(self, items):
        self.calls.append(("set_favorites", list(items)))

    def clear_favorites(self):
        self.calls.append("clear_favorites")


class RecentLinksWidgetMock:
    def __init__(self):
        self.calls: list[tuple[str, list[dict]]] = []
        self.limit = 10

    def set_recent_links(self, items):
        self.calls.append(("set_recent_links", list(items)))


class LinksBusinessMock:
    def __init__(self):
        self.load_calls: list[int] = []
        self.favorites = [
            {"id": 1, "name": "A"},
        ]
        self.recents = [
            {"id": 2, "name": "B"},
        ]

    def load_links(self, category_id: int):
        self.load_calls.append(int(category_id))

    def get_favorite_links(self):
        return list(self.favorites)

    def get_recent_links(self, limit: int | None = None):
        return list(self.recents[: (limit or 20)])


class TableWidgetMock:
    def __init__(self):
        self.populated_with = None
        self.updated_rows: list[dict] = []

    def populate(self, links, mode: str | None = None):
        self.populated_with = (list(links), mode)

    def update_link_by_id(self, link_dict: dict):
        self.updated_rows.append(link_dict)


class StructureBusinessMock:
    def __init__(self, categories_by_section: dict[int, list[dict]] | None = None):
        self.categories_by_section = categories_by_section or {
            1: [{"id": 10}, {"id": 11}]
        }
        self.get_calls: list[int] = []

    def get_categories(self, section_id: int):
        self.get_calls.append(int(section_id))
        return list(self.categories_by_section.get(int(section_id), []))


class UIStateMock:
    def __init__(self):
        self.switched_to: list[list[dict]] = []

    def switch_to_category_tiles(self, categories: list[dict]):
        self.switched_to.append(list(categories))


@pytest.fixture()
def main_window_stub():
    # Минимальный main_window для контроллеров
    return SimpleNamespace(current_category_id=None, undo_stack=SimpleNamespace())


def test_top_panels_receive_signals_from_link_ops(
    monkeypatch, caplog, main_window_stub
):
    caplog.set_level(logging.DEBUG)

    fav = FavWidgetMock()
    recent = RecentLinksWidgetMock()
    links_business = LinksBusinessMock()

    top_ctrl = TopPanelsController(
        main_window_stub,
        fav_widget=fav,
        recent_links_widget=recent,
        links_business=links_business,
    )

    # LinkOperationsController требует db и undo_stack, но для сигналов они не используются в этом тесте
    dummy_db = SimpleNamespace()
    link_ops = LinkOperationsController(
        dummy_db, undo_stack=SimpleNamespace(), main_window=main_window_stub
    )

    # Подключаем сигналы к запросам обновления топ-панелей
    link_ops.favorites_changed.connect(top_ctrl.request_favorites_refresh)
    link_ops.recents_changed.connect(top_ctrl.request_recents_refresh)

    # Эмитим сигналы
    link_ops.emit_favorites_changed()
    link_ops.emit_recents_changed()

    # Симулируем срабатывание таймеров
    top_ctrl._on_fav_refresh_timeout()
    top_ctrl._on_recent_refresh_timeout()

    assert fav.calls and fav.calls[0][0] == "set_favorites"
    assert recent.calls and recent.calls[0][0] == "set_recent_links"


def test_links_table_reloads_on_link_ops_signals(caplog, main_window_stub):
    caplog.set_level(logging.DEBUG)

    table = TableWidgetMock()
    links_business = LinksBusinessMock()
    main_window_stub.current_category_id = 5

    links_table_ctrl = LinksTableController(
        main_window_stub,
        table=table,
        links_business=links_business,
        category_provider=main_window_stub,
    )

    dummy_db = SimpleNamespace()
    link_ops = LinkOperationsController(
        dummy_db, undo_stack=SimpleNamespace(), main_window=main_window_stub
    )

    # Подключаем сигналы к таблице
    link_ops.links_changed.connect(links_table_ctrl.on_links_changed)
    link_ops.link_saved.connect(links_table_ctrl.on_link_saved)
    link_ops.link_deleted.connect(links_table_ctrl.on_link_deleted)

    # Эмитим события и проверяем загрузки
    link_ops.emit_links_changed(7)
    link_ops.emit_link_saved({"id": 22, "category_id": 8})
    link_ops.emit_link_deleted({"id": 23, "category_id": 9})

    assert links_business.load_calls == [7, 8, 9]


def test_category_tiles_refresh_reacts_to_structure_changes(caplog):
    caplog.set_level(logging.DEBUG)

    ui_state = UIStateMock()
    structure_business = StructureBusinessMock(
        categories_by_section={2: [{"id": 100}], 3: []}
    )

    tiles_ctrl = CategoryTilesController(
        ui_state=ui_state, structure_business=structure_business
    )

    tiles_ctrl.refresh(2)
    tiles_ctrl.refresh(3)
    tiles_ctrl.clear()

    # Проверяем, что бизнес-логика запрашивалась, а UIState получил правильные данные
    assert structure_business.get_calls == [2, 3]
    # Первое обновление — категории [100], второе — пусто, clear() — пусто
    assert ui_state.switched_to[0] == [{"id": 100}]
    assert ui_state.switched_to[1] == []
    assert ui_state.switched_to[2] == []


def test_links_ui_controller_uses_table_controller_reload(monkeypatch, caplog):
    # Этот тест проверяет интеграцию _reload_current_category -> LinksTableController.reload
    from app.controllers.ui.links.controller import LinksUIController

    caplog.set_level(logging.DEBUG)

    class LinksTableControllerMock:
        def __init__(self):
            self.reload_calls: list[int] = []

        def reload(self, category_id):
            self.reload_calls.append(category_id)

    class _Signal:
        def __init__(self):
            self._subs = []

        def connect(self, cb):
            if not callable(cb):
                raise TypeError("slot must be callable")
            self._subs.append(cb)

    class _SelModel:
        def __init__(self):
            self.selectionChanged = _Signal()

    class TableViewMock:
        def __init__(self):
            self.doubleClicked = _Signal()
            self.clicked = _Signal()
            self.links_reordered = _Signal()
            # Новые обязательные элементы интерфейса таблицы
            self.customContextMenuRequested = _Signal()

        def setContextMenuPolicy(self, *_args, **_kwargs):
            pass

        def selectionModel(self):
            return _SelModel()

    class _BizSignal:
        def connect(self, *_a, **_k):
            return None

    class LinksBusinessDummy:
        # Требуемые сигналы для LinksUIHandlers._connect_signals
        def __init__(self):
            self.favorites_counted = _BizSignal()
            self.link_updated = _BizSignal()
            self.error_occurred = _BizSignal()

    table_view = TableViewMock()
    business = LinksBusinessDummy()
    main = SimpleNamespace(get_current_category_id=lambda: 42)
    table_ctrl_mock = LinksTableControllerMock()
    # Обязательная зависимость link_operations — передаём простую заглушку
    link_ops_stub = SimpleNamespace()

    _ = LinksUIController(
        table_view,
        business,
        main,
        link_operations=link_ops_stub,
        links_table_controller=table_ctrl_mock,
    )

    # В конструкторе вызывается _reload_current_category()
    assert table_ctrl_mock.reload_calls == [42]
