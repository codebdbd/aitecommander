from types import SimpleNamespace

import pytest

# Тест проверяет, что отсутствие set_top_panels_controller в StructureBusinessLogic
# приводит к SetupError при вызове setup_controllers


def test_setup_raises_if_structure_business_lacks_setter(monkeypatch):
    from app.controllers.system import window_controllers_setup as wcs

    class DummyStructureBusiness:
        # Отсутствует set_top_panels_controller
        def __init__(self, db):
            self.db = db

        # Нужные минимальные атрибуты/сигналы для дальнейшей проводки
        active_sphere_changed = SimpleNamespace(connect=lambda *_args, **_kw: None)
        structure_loaded = SimpleNamespace(connect=lambda *_args, **_kw: None)

    class DummyLinksBusiness:
        def __init__(self, db):
            self.db = db

        # Сигналы, к которым подключается код
        links_loaded = SimpleNamespace(connect=lambda *_args, **_kw: None)
        search_results_ready = SimpleNamespace(connect=lambda *_args, **_kw: None)

    class DummyLinkOps:
        def __init__(self, db, undo_stack, window):
            self.db = db
            self.undo_stack = undo_stack
            self.window = window
            self.recents_changed = SimpleNamespace(connect=lambda *_args, **_kw: None)
            self.favorites_changed = SimpleNamespace(connect=lambda *_args, **_kw: None)
            self.links_changed = SimpleNamespace(connect=lambda *_args, **_kw: None)
            self.link_saved = SimpleNamespace(connect=lambda *_args, **_kw: None)
            self.link_deleted = SimpleNamespace(connect=lambda *_args, **_kw: None)

    class DummyLinksTableController:
        def __init__(self, window, table, links_business, category_provider):
            pass

        def on_links_changed(self, *_):
            pass

        def on_link_saved(self, *_):
            pass

        def on_link_deleted(self, *_):
            pass

        def on_links_loaded(self, *_):
            pass

        def on_search_results(self, *_):
            pass

    class DummyLinksUIController:
        def __init__(
            self, table, links_business, window, link_operations, links_table_controller
        ):
            pass

        def on_quick_add_requested(self, *_):
            pass

    class DummyDatabaseController:
        def __init__(self, db, window):
            # Сигналы, которые позже подключаются
            self.database_restored = SimpleNamespace(connect=lambda *_a, **_k: None)
            self.database_connected = SimpleNamespace(connect=lambda *_a, **_k: None)
            self.favorites_cleared = SimpleNamespace(connect=lambda *_a, **_k: None)
            self.operation_success = SimpleNamespace(connect=lambda *_a, **_k: None)
            self.operation_error = SimpleNamespace(connect=lambda *_a, **_k: None)

    class DummySystemDialogController:
        def __init__(
            self,
            window,
            *,
            database_controller=None,
            links_table_controller=None,
            links_business=None,
        ):  # noqa: ARG002
            pass

    class DummyAppShutdownController:
        def __init__(self, window):
            pass

    class DummyCategoryTilesController:
        def __init__(self, ui_state, structure_business):
            pass

        def attach_tiles_widget(self, tiles):
            pass

    class DummyStructureUIController:
        def __init__(self, tree, structure_business, window):
            # Сигналы, к которым будет проводка
            self.item_changed = SimpleNamespace(connect=lambda *_a, **_k: None)
            self.item_added = SimpleNamespace(connect=lambda *_a, **_k: None)

    class DummySpheresBarController:
        def __init__(self, window):
            pass

        def update_active_sphere_button(self, *_):
            pass

    class DummyTopPanelsController:
        def __init__(self, window, fav_widget, recent_links_widget, links_business):
            pass

        def request_refresh(self):
            pass

        def request_favorites_refresh(self, *_):
            pass

        def request_recents_refresh(self, *_):
            pass

        def clear_favorites(self):
            pass

        def schedule_structure_refresh(self):
            pass

    class DummyQAction:
        def __init__(self, *args, **kwargs):
            pass

        def setToolTip(self, *_):
            pass

        @property
        def icon(self):
            return lambda: None

        def triggered(self):
            return SimpleNamespace(connect=lambda *_a, **_k: None)

    class DummyQPushButton:
        def __init__(self, *args, **kwargs):
            pass

        def setToolTip(self, *_):
            pass

        def setFont(self, *_):
            pass

        def clicked(self):
            return SimpleNamespace(connect=lambda *_a, **_k: None)

    class DummyQFont:
        def setPointSize(self, *_):
            pass

    class DummyQTimer:
        @staticmethod
        def singleShot(*_args, **_kwargs):
            pass

    # Monkeypatch dependencies inside the module under test
    monkeypatch.setattr(wcs, "StructureBusinessLogic", DummyStructureBusiness)
    monkeypatch.setattr(wcs, "LinksBusinessLogic", DummyLinksBusiness)
    monkeypatch.setattr(wcs, "LinkOperationsController", DummyLinkOps)
    monkeypatch.setattr(wcs, "LinksTableController", DummyLinksTableController)
    monkeypatch.setattr(wcs, "LinksUIController", DummyLinksUIController)
    monkeypatch.setattr(wcs, "DatabaseController", DummyDatabaseController)
    monkeypatch.setattr(wcs, "SystemDialogController", DummySystemDialogController)
    monkeypatch.setattr(wcs, "AppShutdownController", DummyAppShutdownController)
    monkeypatch.setattr(wcs, "CategoryTilesController", DummyCategoryTilesController)
    monkeypatch.setattr(wcs, "StructureUIController", DummyStructureUIController)
    monkeypatch.setattr(wcs, "SpheresBarController", DummySpheresBarController)
    monkeypatch.setattr(wcs, "TopPanelsController", DummyTopPanelsController)
    monkeypatch.setattr(wcs, "QAction", DummyQAction)
    monkeypatch.setattr(wcs, "QPushButton", DummyQPushButton)
    monkeypatch.setattr(wcs, "QFont", DummyQFont)
    monkeypatch.setattr(wcs, "QTimer", DummyQTimer)

    # Заглушки для темы/иконок
    monkeypatch.setattr(wcs, "themed_icon", lambda *a, **k: None)
    monkeypatch.setattr(wcs, "get_current_theme", lambda: "dark")

    class Tiles:
        view = object()
        contextMenuRequested = SimpleNamespace(connect=lambda *_a, **_k: None)
        editRequested = SimpleNamespace(connect=lambda *_a, **_k: None)
        deleteRequested = SimpleNamespace(connect=lambda *_a, **_k: None)
        addLinkRequested = SimpleNamespace(connect=lambda *_a, **_k: None)

        def inject_dependencies(self, **_deps):
            pass

    # Упрощённое окно с минимально необходимыми атрибутами
    window = SimpleNamespace(
        tiles=Tiles(),
        tree=SimpleNamespace(),
        table=SimpleNamespace(selectionModel=lambda: None),
        stack=SimpleNamespace(currentIndex=lambda: -1),
        undo_stack=None,
        fav_widget=object(),
        recent_links_widget=object(),
        update_statusbar=lambda: None,
        findChild=lambda *_a, **_k: None,
    )

    controllers: dict = {}

    with pytest.raises(wcs.SetupError):
        wcs.setup_controllers(window, controllers, db=object())
