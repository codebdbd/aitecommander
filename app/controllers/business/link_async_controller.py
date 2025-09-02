import logging
from typing import Callable, List, Dict, Optional

from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.utils.db.api import run_db
from app.utils.db.synchronization import tasks_lock


class LinkAsyncController:
    """Инкапсулирует управление асинхронными задачами для LinksBusinessLogic.

    Управляет scheduler'ом, счетчиком задач, pending_tasks и запуском run_db.
    Предоставляет методы запуска фоновых операций и корректного завершения работы.
    """

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        scheduler=None,
        run_db_fn=run_db,
        tasks_lock_obj=tasks_lock,
    ) -> None:
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._scheduler = scheduler or get_task_scheduler()
        self._run_db = run_db_fn
        self._tasks_lock = tasks_lock_obj
        self._pending_tasks: set[int] = set()
        self._task_counter = 0

    # Методы запуска
    def load_links_async(
        self,
        *,
        category_id: int,
        fetch_fn: Callable[[], List[Dict]],
        on_loaded: Callable[[List[Dict], int, int], None],
        on_error: Callable[[str], None],
    ) -> int:
        """Запустить загрузку ссылок для категории. Возвращает task_id."""
        self._task_counter += 1
        task_id = self._task_counter
        with self._tasks_lock:
            self._pending_tasks.add(task_id)
        self.logger.debug(
            "Loading links for category %s, task_id=%s", category_id, task_id
        )

        def _finished(links: List[Dict]):
            # Снимаем из pending и дальше отдаём в BLL
            with self._tasks_lock:
                if task_id in self._pending_tasks:
                    self._pending_tasks.remove(task_id)
            on_loaded(links, category_id, task_id)

        self._run_db(
            fetch_fn,
            description=f"load_links(category_id={category_id})",
            on_finished=_finished,
            on_error=lambda e: on_error(str(e)),
        )
        return task_id

    def search_links_async(
        self,
        *,
        query: str,
        search_fn: Callable[[], List[Dict]],
        on_finished: Callable[[List[Dict]], None],
        on_error: Callable[[str], None],
    ) -> None:
        self.logger.debug("Searching links for query: %s", query)
        self._run_db(
            search_fn,
            description=f"search_links(query={query!r})",
            on_finished=on_finished,
            on_error=lambda e: on_error(str(e)),
        )

    def count_favorites_async(
        self,
        *,
        count_fn: Callable[[], int],
        links: List[Dict],
        link_ctx: Optional[Dict],
        on_finished: Callable[[int, List[Dict], Optional[Dict]], None],
        on_error: Callable[[str], None],
    ) -> None:
        self._run_db(
            count_fn,
            description="count_favorites()",
            on_finished=lambda fav_count: on_finished(int(fav_count), links, link_ctx),
            on_error=lambda e: on_error(str(e)),
        )

    # Завершение работы
    def shutdown(self, timeout_ms: int = 2000) -> None:
        try:
            self._scheduler.get_thread_pool().waitForDone(timeout_ms)
            self.logger.debug("LinkAsyncController shutdown completed")
        except Exception as e:
            self.logger.error("Error during LinkAsyncController shutdown: %s", e)
