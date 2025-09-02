import types
import pytest

from app.controllers.business.links_business import LinksBusinessLogic


class DummyRepo:
    def __init__(self):
        self.calls = []

    def fetch_links(self, category_id):
        self.calls.append(("fetch_links", category_id))
        return [{"id": 1, "category_id": category_id}]

    def search_links(self, query):
        self.calls.append(("search_links", query))
        return [{"id": 2, "q": query}]

    def count_favorites(self):
        self.calls.append(("count_favorites",))
        return 3


class DummyAsync:
    def __init__(self):
        self.calls = []
        self._last_callbacks = {}
        self.shutdown_called_with = None

    def load_links_async(self, *, category_id, fetch_fn, on_loaded, on_error):
        self.calls.append(("load_links_async", category_id))
        self._last_callbacks["links"] = (fetch_fn, on_loaded, on_error, category_id)

    def search_links_async(self, *, query, search_fn, on_finished, on_error):
        self.calls.append(("search_links_async", query))
        self._last_callbacks["search"] = (search_fn, on_finished, on_error, query)

    def count_favorites_async(self, *, count_fn, on_finished, on_error):
        self.calls.append(("count_favorites_async",))
        self._last_callbacks["fav"] = (count_fn, on_finished, on_error)

    def shutdown(self, timeout_ms):
        self.shutdown_called_with = timeout_ms


class SignalStub:
    def __init__(self):
        self._subs = []
        self.emitted = []

    def connect(self, cb):
        self._subs.append(cb)

    def emit(self, *args):
        self.emitted.append(args)
        for cb in list(self._subs):
            cb(*args)

    def __getitem__(self, _):
        return self


@pytest.fixture()
def business_with_stubs(monkeypatch):
    repo = DummyRepo()
    async_ctrl = DummyAsync()
    logic = LinksBusinessLogic(repository=repo, async_controller=async_ctrl)

    # Подменяем PyQt сигналы на простые стабы
    logic.links_loaded = SignalStub()
    logic.search_results_ready = SignalStub()
    logic.favorites_counted = SignalStub()
    logic.error_occurred = SignalStub()
    logic.link_updated = SignalStub()

    return logic, repo, async_ctrl


def test_load_links_delegates_and_emits(business_with_stubs):
    logic, repo, async_ctrl = business_with_stubs

    logic.load_links(category_id=42)

    assert ("load_links_async", 42) in async_ctrl.calls

    # эмулируем завершение задачи: выполняем fetch_fn и вызываем on_loaded
    fetch_fn, on_loaded, _on_error, cat_id = async_ctrl._last_callbacks["links"]
    links = fetch_fn()
    on_loaded(links, cat_id, task_id=1)

    # проверяем, что сигнал был эмитирован
    assert logic.links_loaded.emitted[-1] == (links, 42, 1)
    # и что репозиторий действительно дергался
    assert ("fetch_links", 42) in repo.calls


def test_search_links_delegates_and_emits(business_with_stubs):
    logic, repo, async_ctrl = business_with_stubs

    # пустой запрос игнорируется
    logic.search_links("   ")
    assert not async_ctrl.calls  # ничего не вызвано

    logic.search_links("abc")
    assert ("search_links_async", "abc") in async_ctrl.calls

    search_fn, on_finished, _on_error, q = async_ctrl._last_callbacks["search"]
    results = search_fn()
    on_finished(results)

    assert logic.search_results_ready.emitted[-1] == (results,)
    assert ("search_links", "abc") in repo.calls


def test_count_favorites_delegates_and_emits(business_with_stubs):
    logic, repo, async_ctrl = business_with_stubs

    logic.count_favorites()

    assert ("count_favorites_async",) in async_ctrl.calls

    count_fn, on_finished, _on_error = async_ctrl._last_callbacks["fav"]
    fav_count = count_fn()
    on_finished(fav_count)

    assert logic.favorites_counted.emitted[-1] == (3,)
    assert ("count_favorites",) in repo.calls


def test_shutdown_propagates_timeout(business_with_stubs):
    logic, _repo, async_ctrl = business_with_stubs
    logic.shutdown(timeout=1234)
    assert async_ctrl.shutdown_called_with == 1234
