import pytest

from app.controllers.business.link_async_controller import LinkAsyncController


class DummyThreadPool:
    def __init__(self):
        self.wait_args = []

    def waitForDone(self, timeout_ms: int):
        self.wait_args.append(timeout_ms)
        return True


class DummyScheduler:
    def __init__(self, pool: DummyThreadPool):
        self._pool = pool

    def get_thread_pool(self):
        return self._pool


def immediate_run_db(fn, *, description=None, on_finished=None, on_error=None):
    try:
        result = fn()
        if on_finished:
            on_finished(result)
    except Exception as e:
        if on_error:
            on_error(e)
        else:
            raise


def test_load_links_async_calls_on_loaded_with_task_id():
    pool = DummyThreadPool()
    sched = DummyScheduler(pool)
    controller = LinkAsyncController(scheduler=sched, run_db_fn=immediate_run_db)

    calls = []

    def fetch():
        return [{"id": 1}]

    def on_loaded(links, category_id, task_id):
        calls.append((links, category_id, task_id))

    def on_error(msg: str):
        pytest.fail(f"Unexpected error: {msg}")

    task_id = controller.load_links_async(
        category_id=42,
        fetch_fn=fetch,
        on_loaded=on_loaded,
        on_error=on_error,
    )

    assert isinstance(task_id, int) and task_id > 0
    assert calls and calls[0][0] == [{"id": 1}] and calls[0][1] == 42
    # task_id, переданный в on_loaded, должен совпасть с возвращённым
    assert calls[0][2] == task_id


def test_search_links_async_calls_on_finished():
    controller = LinkAsyncController(scheduler=DummyScheduler(DummyThreadPool()), run_db_fn=immediate_run_db)

    def search():
        return [1, 2, 3]

    results = []

    controller.search_links_async(
        query="abc",
        search_fn=search,
        on_finished=lambda r: results.append(r),
        on_error=lambda e: pytest.fail(f"Unexpected error: {e}"),
    )

    assert results == [[1, 2, 3]]


def test_count_favorites_async_passes_all_links_and_ctx_and_casts_int():
    controller = LinkAsyncController(scheduler=DummyScheduler(DummyThreadPool()), run_db_fn=immediate_run_db)

    def count():
        return 5.0  # будет приведено к int

    links = [{"id": 7}]
    ctx = {"id": 7}

    calls = []

    controller.count_favorites_async(
        count_fn=count,
        links=links,
        link_ctx=ctx,
        on_finished=lambda fav_count, links, link_ctx: calls.append((fav_count, links, link_ctx)),
        on_error=lambda e: pytest.fail(f"Unexpected error: {e}"),
    )

    assert calls and calls[0][0] == 5
    assert calls[0][1] == [{"id": 7}]
    assert calls[0][2] == ctx


def test_shutdown_waits_thread_pool_with_timeout():
    pool = DummyThreadPool()
    sched = DummyScheduler(pool)
    controller = LinkAsyncController(scheduler=sched, run_db_fn=immediate_run_db)

    controller.shutdown(timeout_ms=1234)

    assert pool.wait_args == [1234]
