# app/controllers/links_business.py

import logging
from collections import defaultdict
from functools import wraps
from typing import Any, Callable, Optional

import cachetools
from PyQt6.QtCore import QMutex, QMutexLocker, QObject, pyqtSignal, pyqtSlot

from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.models.db import Database
from app.services.links_service import LinksService
from app.utils.db.api import run_db
from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.synchronization import tasks_lock
from app.utils.metrics import measure_time
from app.utils.validators.link_validators import validate_link_form_data


def validate_link_form(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that validates link data before processing."""

    @wraps(func)
    def wrapper(
        self: "LinksBusinessLogic", link_data: dict[str, Any], *args: Any, **kwargs: Any
    ) -> Any:
        if not isinstance(link_data, dict):
            raise ValueError(self.tr("Invalid link data provided: not a dict"))

        name = link_data.get("name")
        url = link_data.get("url")
        link_type = link_data.get("type")
        category_id = link_data.get("category_id")
        if not (
            validate_link_form_data(name, url, link_type)
            and isinstance(category_id, int)
            and category_id > 0
        ):
            raise ValueError(self.tr("Invalid link data provided"))  # ✅ i18n уже есть

        return func(self, link_data, *args, **kwargs)

    return wrapper


def handle_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator providing centralized error handling."""

    @wraps(func)
    def wrapper(self: "LinksBusinessLogic", *args: Any, **kwargs: Any) -> Any:
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            self.logger.error("Error in %s: %s", func.__name__, e, exc_info=True)
            if not handle_db_error(e, self):
                raise

    return wrapper


class LinksBusinessLogic(QObject):
    """Business logic responsible for working with links."""

    # Constants
    DEFAULT_SHUTDOWN_TIMEOUT = 2000
    DEFAULT_RECENT_LIMIT = 10
    CACHE_TTL_SECONDS = 300  # 5 minutes TTL for cache

    # Signals used to notify the UI layer (PyQt6 typed style)
    links_loaded = pyqtSignal(
        list, int, int, name="linksLoaded"
    )  # List[Dict[str, Any]], int, int - links, category ID, task ID
    search_results_ready = pyqtSignal(
        list, name="searchResultsReady"
    )  # List[Dict[str, Any]] - search results
    favorites_counted = pyqtSignal(
        int, list, object, name="favoritesCounted"
    )  # int, List[Dict[str, Any]], Optional[Dict[str, Any]] - count, links, current link
    link_updated = pyqtSignal(dict, name="linkUpdated")  # Dict[str, Any] - updated link
    error_occurred = pyqtSignal(str, name="errorOccurred")  # str - error message
    link_deleted = pyqtSignal(int, name="linkDeleted")  # int - deleted link ID
    recent_links_loaded = pyqtSignal(
        list, name="recentLinksLoaded"
    )  # List[Dict[str, Any]] - recent links
    favorite_links_loaded = pyqtSignal(
        list, name="favoriteLinksLoaded"
    )  # List[Dict[str, Any]] - favorite links
    favorites_cleared = pyqtSignal(bool, name="favoritesCleared")  # bool - success flag
    link_by_id_loaded = pyqtSignal(
        dict, int, name="linkByIdLoaded"
    )  # Dict[str, Any], int - link, ID
    next_position_loaded = pyqtSignal(
        int, int, name="nextPositionLoaded"
    )  # int, int - position, category_id
    batch_updated = pyqtSignal(bool, name="batchUpdated")  # bool - batch result

    # Internal dispatch signals to marshal worker callbacks into the QObject's thread
    _finished_dispatch = pyqtSignal(
        object, object, name="_finishedDispatch"
    )  # handler, result
    _error_dispatch = pyqtSignal(str, object, name="_errorDispatch")  # message, task_id

    def __init__(
        self,
        db: Database,
        parent: QObject = None,
        logger: Optional[logging.Logger] = None,
        tasks_lock_instance=None,
        scheduler=None,
        links_service: Optional[LinksService] = None,
    ):
        super().__init__(parent)
        self.db = db
        # Service layer atop the repository to reduce duplication and manage transactions
        self.links = links_service or LinksService(db)
        # Dependency injection
        self.scheduler = scheduler or get_task_scheduler()
        self._tasks_lock = tasks_lock_instance or tasks_lock
        self.pending_tasks: dict[
            int, int
        ] = {}  # Store task_id -> category_id or other payloads
        self.task_counter = 0
        self.logger = logger or logging.getLogger(self.__class__.__name__)

        # TTLCache with automatic expiration for better memory management
        self._cache: cachetools.TTLCache[str, Any] = cachetools.TTLCache(
            maxsize=128, ttl=self.CACHE_TTL_SECONDS
        )

        self._mutex = QMutex()  # Qt-compatible mutex for thread safety
        # Connect internal dispatchers
        try:
            self._finished_dispatch.connect(self._dispatch_finished)
            self._error_dispatch.connect(self._dispatch_error)
        except Exception as e:
            # In rare cases during shutdown the QObject may not be fully initialised
            self.logger.debug(
                "Failed to connect internal dispatch signals: %s", e, exc_info=True
            )

    def shutdown(self, timeout: int = DEFAULT_SHUTDOWN_TIMEOUT) -> None:
        """Perform a graceful shutdown."""
        try:
            # Disconnect all signals to prevent memory leaks
            try:
                self._finished_dispatch.disconnect()
            except TypeError:
                pass  # Signal not connected
            try:
                self._error_dispatch.disconnect()
            except TypeError:
                pass  # Signal not connected

            thread_pool = self.scheduler.get_thread_pool()
            active_threads = thread_pool.activeThreadCount()
            if active_threads > 0:
                self.logger.debug("Waiting for %d active threads...", active_threads)
            thread_pool.waitForDone(timeout)
            self._clear_pending_tasks()
            self._cache.clear()
            self.logger.debug("LinksBusinessLogic shutdown completed")
        except Exception as e:
            self.logger.error(
                "Error during LinksBusinessLogic shutdown: %s", e, exc_info=True
            )

    def _clear_pending_tasks(self) -> None:
        with self._tasks_lock:
            self.pending_tasks.clear()

    @measure_time("load_links", log_threshold_ms=200)
    def load_links(self, category_id: int) -> None:
        """Load links for a category.

        ✅ Метрика производительности: измеряется время выполнения.
        """
        self.task_counter += 1
        task_id = self.task_counter

        with self._tasks_lock:
            self.pending_tasks[task_id] = category_id

        self.logger.debug(
            "Loading links for category %s, task_id=%s", category_id, task_id
        )

        self._run_db_task(
            lambda: self.links.get_links(category_id) or [],
            description=f"load_links(category_id={category_id})",
            on_finished=lambda links: self._on_links_loaded(
                links, category_id, task_id
            ),
            task_id=task_id,
        )

    @handle_errors
    def get_links(self, category_id: int) -> list[dict[str, Any]]:
        """Return links for a category synchronously (used by import/export flows)."""
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning("Invalid category_id: %s", category_id)
            return []

        cache_key = f"sync_links:{category_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        links = self.links.get_links(category_id) or []
        self._cache[cache_key] = links
        return links

    @measure_time("search_links", log_threshold_ms=300)
    def search_links(self, query: str) -> None:
        """Search links by query.

        ✅ Метрика производительности: измеряется время выполнения.
        """
        q = (query or "").strip()
        if not q:
            self.logger.debug(
                "Searching links: empty query -> return ALL links (global)"
            )
            self._run_db_task(
                lambda: self.links.get_all_links() or [],
                description="search_links(all)",
                on_finished=self._on_search_finished,
            )
            return

        self.logger.debug("Searching links for query: %s", q)

        self._run_db_task(
            lambda: self.links.search(q) or [],
            description=f"search_links(query={q!r})",
            on_finished=self._on_search_finished,
        )

    def update_link_order(self, link_ids: list[int]) -> None:
        """Update the order of links."""
        if not link_ids:
            return

        self.logger.debug("Updating order for %s links", len(link_ids))

        self._run_db_task(
            lambda: self.links.reorder(link_ids),
            description="update_link_order",
            on_finished=self._on_reorder_finished,
        )

    def count_favorites(self, link: Optional[dict[str, Any]] = None) -> None:
        """Count favorite links."""

        def _count():
            return self.links.count_favorites()

        self._run_db_task(
            _count,
            description="count_favorites()",
            on_finished=lambda fav_count: self._on_favorites_counted(
                int(fav_count), [], link
            ),
        )

    def delete_link(self, link_id: int) -> None:
        """Delete a link."""
        if not self._validate_link_id(link_id):
            return

        self._run_db_task(
            lambda: self.links.delete_link(link_id),
            description=f"delete_link({link_id})",
            on_finished=lambda _: self._on_delete_finished(link_id),
            task_id=link_id,
        )

    @validate_link_form
    @handle_errors
    @measure_time("create_link", log_threshold_ms=200)
    def create_link(self, link_data: dict[str, Any]) -> int:
        """Create a new link.

        ✅ Метрика производительности: измеряется время выполнения.
        """
        self.logger.warning(
            "Using synchronous save_link; consider using save_link_async for async"
        )

        result = self.links.create_or_update_link(link_data)
        if result and not link_data.get("id"):
            link_data["id"] = result

        self.logger.info("Link saved: %s", link_data.get("id", "[new]"))

        try:
            self._invalidate_cache()
            self.link_updated.emit(link_data)
        except Exception as emit_err:
            self.logger.warning("Failed to emit link_updated: %s", emit_err)

        return result

    @validate_link_form
    @handle_errors
    def save_link(self, link_data: dict[str, Any]) -> int:
        """Backward-compatible synchronous save.

        Delegates to ``create_link`` to persist data and emit ``link_updated``.
        Used by legacy UI code expecting a synchronous save method.
        """
        return self.create_link(link_data)

    @validate_link_form
    def save_link_async(self, link_data: dict[str, Any]) -> None:
        """Save a link asynchronously."""
        self._run_db_task(
            lambda: self.links.create_or_update_link(link_data),
            description="save_link_async",
            on_finished=lambda result: self._on_link_saved(link_data, result),
        )

    def _on_link_saved(self, link_data: dict[str, Any], result: int) -> None:
        if result and not link_data.get("id"):
            link_data["id"] = result
        self._invalidate_cache()
        self.link_updated.emit(link_data)
        self.logger.info("Link saved async: %s", link_data.get("id", "[new]"))

    def update_link_last_used(self, link_id: int) -> None:
        """Update the last-used timestamp for a link."""
        if not self._validate_link_id(link_id):
            return

        self._run_db_task(
            lambda: self.links.update_last_used(link_id),
            description=f"update_link_last_used({link_id})",
            on_finished=lambda _: self._on_last_used_updated(link_id),
            task_id=link_id,
        )

    def toggle_favorite(self, link: dict[str, Any]) -> None:
        """Toggle favorite status for a link."""
        if (
            not isinstance(link, dict)
            or not isinstance(link.get("id"), int)
            or link["id"] <= 0
        ):
            raise ValueError(self.tr("Invalid link data for toggle_favorite"))

        link_id = link.get("id")

        # Atomic update: read and modify within a single transaction
        def _toggle() -> tuple[int, dict[str, Any]]:
            # Use QMutexLocker for RAII-style lock management
            locker = QMutexLocker(self._mutex)
            try:
                current_link = self.links.get_link_by_id(link_id)
                if not current_link:
                    raise ValueError(self.tr("Link not found"))
                old_status = current_link.get("is_favorite", False)
                new_status = not old_status
                self.logger.debug(
                    "Toggle favorite for link %s: %s -> %s",
                    link_id,
                    old_status,
                    new_status,
                )
                link_data = current_link.copy()
                link_data["is_favorite"] = new_status
                result = self.links.create_or_update_link(link_data)
                return result, link_data
            finally:
                locker.unlock()

        self._run_db_task(
            _toggle,
            description=f"toggle_favorite({link_id})",
            on_finished=lambda data: self._on_favorite_toggled(data[0], data[1]),
            task_id=link_id,
        )

    def _on_favorite_toggled(self, result: int, link_data: dict[str, Any]) -> None:
        self.logger.info("Favorite status updated successfully, result ID: %s", result)
        self._invalidate_cache()
        self.count_favorites(link_data)

    def load_recent_links(self, limit: int = DEFAULT_RECENT_LIMIT) -> None:
        """Load recent links asynchronously."""
        if limit <= 0:
            self.logger.warning("Invalid limit for recent links: %s", limit)
            self.recent_links_loaded.emit([])
            return

        cache_key = f"recent_links_{limit}"
        if cache_key in self._cache:
            self.recent_links_loaded.emit(self._cache[cache_key])
            return

        self._run_db_task(
            lambda: self.links.get_recent_links(limit),
            description="load_recent_links",
            on_finished=lambda links: self._cache_links_and_emit(
                cache_key, links or [], self.recent_links_loaded.emit
            ),
        )

    def load_favorite_links(self) -> None:
        """Load favorite links asynchronously."""
        cache_key = "favorite_links"
        if cache_key in self._cache:
            self.favorite_links_loaded.emit(self._cache[cache_key])
            return

        self._run_db_task(
            lambda: self.links.get_favorite_links(),
            description="load_favorite_links",
            on_finished=lambda links: self._cache_links_and_emit(
                cache_key, links or [], self.favorite_links_loaded.emit
            ),
        )

    def clear_favorites_async(self) -> None:
        """Clear favorite links asynchronously."""
        self._run_db_task(
            lambda: self.links.clear_favorites() or True,
            description="clear_favorites_async",
            on_finished=self._on_favorites_cleared,
        )

    def load_link_by_id(self, link_id: int) -> None:
        """Fetch a link by ID asynchronously."""
        if not self._validate_link_id(link_id):
            self.link_by_id_loaded.emit({}, link_id)
            return

        cache_key = f"link_{link_id}"
        if cache_key in self._cache:
            self.link_by_id_loaded.emit(self._cache[cache_key], link_id)
            return

        self._run_db_task(
            lambda: self.links.get_link_by_id(link_id) or {},
            description=f"load_link_by_id({link_id})",
            on_finished=lambda link: self._cache_links_and_emit(
                cache_key,
                link,
                lambda link_data: self.link_by_id_loaded.emit(link_data, link_id),
            ),
        )

    def load_next_position(self, category_id: int) -> None:
        """Load the next position asynchronously."""
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning(
                "Invalid category_id for load_next_position: %s", category_id
            )
            self.next_position_loaded.emit(0, category_id)
            return

        cache_key = f"next_pos_{category_id}"
        if cache_key in self._cache:
            self.next_position_loaded.emit(self._cache[cache_key], category_id)
            return

        self._run_db_task(
            lambda: self.links.get_next_position(category_id),
            description=f"load_next_position({category_id})",
            on_finished=lambda pos: self._cache_links_and_emit(
                cache_key, pos, lambda p: self.next_position_loaded.emit(p, category_id)
            ),
        )

    def batch_update_links_async(self, links_data: list[dict[str, Any]]) -> None:
        """Execute a batch link update asynchronously."""
        if not links_data:
            self.logger.warning("Empty links_data for batch_update_links_async")
            self.batch_updated.emit(True)
            return

        for i, link_data in enumerate(links_data):
            if not isinstance(link_data, dict) or not link_data:
                self.logger.error("Invalid link data at index %s: %s", i, link_data)
                self.batch_updated.emit(False)
                return

        self._run_db_task(
            lambda: self.links.batch_update(links_data),
            description="batch_update_links_async",
            on_finished=self._on_batch_updated,
        )

    @handle_errors
    def create_links_for_import_bulk(self, links_payload: list[dict[str, Any]]) -> int:
        """Bulk create/update links during import without per-link cache churn."""
        if not isinstance(links_payload, list) or not links_payload:
            return 0

        category_ids: set[int] = set()
        for item in links_payload:
            if not isinstance(item, dict):
                continue
            cid = item.get("category_id")
            if isinstance(cid, int) and cid > 0:
                category_ids.add(int(cid))
        if not category_ids:
            return 0

        existing_pairs: dict[int, set[tuple[str, str]]] = defaultdict(set)
        try:
            existing_links = self.links.get_links_for_categories(list(category_ids))
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.debug(
                "create_links_for_import_bulk: failed to preload existing links: %s",
                exc,
                exc_info=True,
            )
            existing_links = {}
        for cid, rows in (existing_links or {}).items():
            bucket = existing_pairs.setdefault(int(cid), set())
            for row in rows or []:
                name = str(row.get("name") or "").strip()
                url = str(row.get("url") or "").strip()
                if name and url:
                    bucket.add((name, url))

        batch_pairs: dict[int, set[tuple[str, str]]] = defaultdict(set)
        prepared: list[dict[str, Any]] = []

        for raw_link in links_payload:
            if not isinstance(raw_link, dict):
                continue
            data = dict(raw_link)
            category_id = data.get("category_id")
            if not isinstance(category_id, int) or category_id <= 0:
                continue

            link_type = data.get("type") or "web"
            url = (data.get("url") or "").strip()
            name = (data.get("name") or "").strip()
            if not url:
                continue
            if not name:
                name = url
            if not validate_link_form_data(name, url, link_type):
                continue

            normalized_pair = (name.strip(), url.strip())
            if normalized_pair in existing_pairs.get(category_id, set()):
                continue
            if normalized_pair in batch_pairs[category_id]:
                continue
            batch_pairs[category_id].add(normalized_pair)

            prepared_link: dict[str, Any] = {
                "category_id": category_id,
                "name": name,
                "url": url,
                "type": link_type,
                "notes": data.get("notes") or "",
                "is_favorite": int(data.get("is_favorite") or 0),
                "icon_path": data.get("icon_path") or "",
                "args": data.get("args") or "",
            }
            browser_key = data.get("browser_key")
            if browser_key is not None:
                prepared_link["browser_key"] = browser_key
            prepared.append(prepared_link)

        if not prepared:
            return 0

        result_ids = self.links.batch_create_or_update_links(prepared) or []
        self._invalidate_cache()
        return len(result_ids) if result_ids else len(prepared)

    @validate_link_form
    @handle_errors
    def create_link_for_import(self, link_data: dict[str, Any]) -> Optional[int]:
        """Create a new link during background data import.

        Args:
            link_data: dictionary containing the link payload.

        Returns:
            The ID of the created link, or ``None`` if creation failed.
        """
        result_id = self.links.create_or_update_link(link_data)
        if result_id:
            self._invalidate_cache()
            self.logger.debug(
                "Created link for import: %s", link_data.get("name", "<no name>")
            )
            return result_id
        else:
            self.logger.warning("Failed to create link for import")
            return None

    # Private helpers for validation and shared operations

    def _validate_link_id(self, link_id: int) -> bool:
        """Validate that a link identifier is a positive integer."""
        if not isinstance(link_id, int) or link_id <= 0:
            self.logger.warning("Invalid link_id: %s", link_id)
            return False
        return True

    def _get_all_links_safe(self) -> list[dict[str, Any]]:
        """Return all links for internal usage with caching."""
        cache_key = "all_links_safe"
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self.links.get_all_links() or []
        self._cache[cache_key] = result
        return result

    def _get_cached(self, cache_key: str, loader: Callable[[], Any]) -> Any:
        """Retrieve a value from the local cache or load it via ``loader``."""
        if cache_key in self._cache:
            return self._cache[cache_key]

        value = loader()
        self._cache[cache_key] = value
        return value

    def _run_db_task(
        self,
        task: Callable[[], Any],
        description: str,
        on_finished: Callable[[Any], None],
        task_id: Optional[Any] = None,
    ) -> None:
        """Wrapper around ``run_db`` that centralizes error handling."""

        # Ensure that callbacks from worker threads are marshalled back to this QObject's thread
        def _emit_finished(result: Any) -> None:
            try:
                # Emit queued to the object thread; handler will call original on_finished safely
                self._finished_dispatch.emit(on_finished, result)
            except Exception as e:
                # If dispatching failed, log and fallback to direct call
                self.logger.debug(
                    "Failed to emit finished dispatch: %s", e, exc_info=True
                )
                on_finished(result)

        def _emit_error(exc: Exception) -> None:
            try:
                self._error_dispatch.emit(str(exc), task_id)
            except Exception as e:
                self.logger.debug("Failed to emit error dispatch: %s", e, exc_info=True)
                # Fallback: direct handler (may run in worker thread)
                self._on_worker_error(str(exc), task_id=task_id)

        run_db(
            task,
            description=description,
            on_finished=_emit_finished,
            on_error=_emit_error,
        )

    def _invalidate_cache(self) -> None:
        """Invalidate caches after a mutating operation."""
        self._cache.clear()

    def _cache_links_and_emit(
        self, key: str, data: Any, emit_func: Callable[[Any], None]
    ) -> None:
        self._cache[key] = data
        emit_func(data)

    # Helpers for handling asynchronous results

    def _on_reorder_finished(self, _: Any) -> None:
        """Handle completion of a link reordering operation."""
        self._invalidate_cache()
        self.logger.debug("Link reordering completed")

    def _on_delete_finished(self, link_id: int) -> None:
        """Handle completion of a link deletion."""
        self._invalidate_cache()
        self.link_deleted.emit(link_id)

    def _on_last_used_updated(self, link_id: int) -> None:
        """Handle completion of a last-used timestamp update."""
        self._invalidate_cache()
        self.logger.debug("Link last_used updated: %s", link_id)

    def _on_favorites_cleared(self, result: bool) -> None:
        """Handle completion of clearing favorites."""
        self._invalidate_cache()
        self.favorites_cleared.emit(result)

    def _on_batch_updated(self, result: bool) -> None:
        """Handle completion of a batch update."""
        self._invalidate_cache()
        self.batch_updated.emit(result)

    # Slots for handling asynchronous results

    @pyqtSlot(object, int, int)
    def _on_links_loaded(
        self, links: list[dict[str, Any]], category_id: int, task_id: int
    ) -> None:
        """Handle completion of link loading."""
        # Avoid emitting signals while holding the lock to prevent potential deadlocks
        should_emit = False
        with self._tasks_lock:
            if task_id in self.pending_tasks:
                del self.pending_tasks[task_id]
                should_emit = True
        if should_emit:
            self.links_loaded.emit(links or [], category_id, task_id)

    @pyqtSlot(object)
    def _on_search_finished(self, search_results: list[dict[str, Any]]) -> None:
        """Handle completion of a search operation."""
        self.search_results_ready.emit(search_results or [])

    @pyqtSlot(int, object, object)
    def _on_favorites_counted(
        self,
        fav_count: int,
        links: list[dict[str, Any]],
        link: Optional[dict[str, Any]],
    ) -> None:
        """Handle completion of counting favorites."""
        self.favorites_counted.emit(fav_count, links or [], link)

    @pyqtSlot(str, object)
    def _on_worker_error(self, error_msg: str, task_id: Optional[int] = None) -> None:
        """Handle errors emitted by background workers."""
        self.logger.error("Worker error: %s", error_msg)
        self.error_occurred.emit(str(error_msg))
        if task_id is not None:
            with self._tasks_lock:
                if task_id in self.pending_tasks:
                    del self.pending_tasks[task_id]

    # Internal queued dispatchers
    @pyqtSlot(object, object)
    def _dispatch_finished(self, handler: Callable[[Any], None], result: Any) -> None:
        try:
            if not callable(handler):
                self.logger.error("Finished handler is not callable: %r", handler)
                return
            handler(result)
        except Exception as e:
            self.logger.error("Error in finished handler: %s", e, exc_info=True)

    @pyqtSlot(str, object)
    def _dispatch_error(self, error_msg: str, task_id: Optional[int] = None) -> None:
        try:
            self._on_worker_error(error_msg, task_id)
        except Exception as e:
            self.logger.error("Error in _dispatch_error: %s", e, exc_info=True)
