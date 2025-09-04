from app.views.link.row_operations import RowOperationsMixin


class DummyView(RowOperationsMixin):
    def __init__(self, model_obj=None, rebuild_raises=False):
        self._model_obj = model_obj
        self._rebuild_raises = rebuild_raises
        # кэш, используемый в миксине
        self._current_links = {}

    def model(self):  # Qt-подобный интерфейс
        if isinstance(self._model_obj, Exception):
            # имитируем исключение при получении модели
            raise self._model_obj
        return self._model_obj

    def rebuild_cache_from_items(self):
        if self._rebuild_raises:
            raise RuntimeError("boom in rebuild")
        # Имитируем перестройку кэша: очищаем
        self._current_links.clear()


class DummyModel:
    def __init__(self, row_count=0, remove_returns=True, remove_raises: Exception | None = None):
        self._row_count = row_count
        self._remove_returns = remove_returns
        self._remove_raises = remove_raises

    def rowCount(self):
        return self._row_count

    def remove_row(self, row: int):
        if self._remove_raises:
            raise self._remove_raises
        return self._remove_returns


def test_remove_row_success_returns_true_and_rebuilds_cache():
    model = DummyModel(row_count=5, remove_returns=True)
    view = DummyView(model_obj=model)
    # предварительно наполним кэш, чтобы увидеть, что его очистили
    view._current_links = {0: {"id": 1}, 1: {"id": 2}}

    ok = view._remove_row(1)

    assert ok is True
    # После успешного удаления rebuild_cache_from_items вызывается, кэш очищен
    assert view._current_links == {}


def test_remove_row_invalid_index_returns_false():
    model = DummyModel(row_count=2, remove_returns=True)
    view = DummyView(model_obj=model)

    assert view._remove_row(-1) is False
    assert view._remove_row(2) is False  # out of bounds (0,1 valid)


def test_remove_row_missing_remove_method_returns_false(monkeypatch):
    class NoRemoveModel:
        def __init__(self, row_count=3):
            self._row_count = row_count
        def rowCount(self):
            return self._row_count
        # remove_row отсутствует

    model = NoRemoveModel(row_count=3)
    view = DummyView(model_obj=model)

    assert view._remove_row(1) is False


def test_remove_row_remove_raises_returns_false():
    model = DummyModel(row_count=3, remove_raises=RuntimeError("fail"))
    view = DummyView(model_obj=model)

    assert view._remove_row(1) is False


def test_remove_row_model_accessor_raises_returns_false():
    # Передаем Exception как сигнал, что model() должна бросать
    view = DummyView(model_obj=RuntimeError("model boom"))

    assert view._remove_row(0) is False


def test_remove_row_success_even_if_rebuild_raises():
    model = DummyModel(row_count=3, remove_returns=True)
    view = DummyView(model_obj=model, rebuild_raises=True)

    ok = view._remove_row(1)
    # Даже если rebuild_cache_from_items бросает, метод должен вернуть True
    assert ok is True
