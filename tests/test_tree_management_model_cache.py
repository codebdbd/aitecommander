import logging
from types import SimpleNamespace

from app.controllers.ui.structure.tree_management import TreeManagement


class ModelStub:
    def __init__(self):
        self.removed = []

    def insert_sections(self, *args, **kwargs):
        pass

    def insert_categories(self, *args, **kwargs):
        pass

    def update_item(self, *args, **kwargs):
        pass

    def remove_sections(self, ids):
        self.removed.append(("section", list(ids)))

    def remove_categories(self, ids):
        self.removed.append(("category", list(ids)))

    def index_for(self, item_type: str, item_id: int):
        class _Index:
            def isValid(self):
                return True

        return _Index()


class ControllerStub:
    def __init__(self, model):
        class _Tree:
            def __init__(self, model):
                self._model = model

            def model(self):
                return self._model

            def currentIndex(self):
                return None

        self.tree = _Tree(model)
        self.icon_handler = object()
        self.main = SimpleNamespace(_first_structure_load=False)

        class _Sel:
            def _restore_selection_after_load(self, *args, **kwargs):
                pass

            def _select_first_item_if_needed(self):
                pass

        self.selection_handler = _Sel()


def test_model_is_cached_and_not_rerequested_after_init(monkeypatch):
    model = ModelStub()
    main_ctrl = ControllerStub(model)
    tm = TreeManagement(
        main_ctrl, category_tiles_controller=SimpleNamespace(refresh=lambda *_: None)
    )

    # После инициализации подменим tree.model на функцию, бросающую исключение.
    def _boom():
        raise RuntimeError("should not be called")

    main_ctrl.tree.model = _boom  # type: ignore[assignment]

    # Методы должны использовать tm.model, а не вызывать tree.model()
    tm._on_item_deleted("section", 7)
    assert ("section", [7]) in model.removed

    idx = tm._find_item_by_id("category", 5)
    assert idx is not None and idx.isValid()


def test_on_item_deleted_logs_when_model_missing(caplog):
    # Смоделируем отсутствие модели: передадим контроллер с ломающимся model() и затем обнулим tm.model
    class BadController(ControllerStub):
        def __init__(self):
            super().__init__(ModelStub())

    ctrl = BadController()
    tm = TreeManagement(
        ctrl, category_tiles_controller=SimpleNamespace(refresh=lambda *_: None)
    )
    tm.model = None  # сломали ссылку

    caplog.set_level(logging.ERROR)
    tm._on_item_deleted("category", 1)

    assert any("model is not available" in rec.getMessage() for rec in caplog.records)
