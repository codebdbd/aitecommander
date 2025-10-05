# app/controllers/links_business.py

import logging
import threading
from functools import lru_cache, wraps
from typing import Any, Callable, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.models.db import Database
from app.services.links_service import LinksService
from app.utils.db.api import run_db
from app.utils.db.db_error_handler import handle_db_error
from app.utils.db.synchronization import tasks_lock


def validate_link_form(func):
    """Decorator that validates link data before processing."""
    @wraps(func)
    def wrapper(self, link_data: Dict, *args, **kwargs):
        if not isinstance(link_data, dict):
            raise ValueError(self.tr("Invalid link data provided: not a dict"))
        from app.utils.validators.link_validators import validate_link_form_data

        name = link_data.get("name")
        url = link_data.get("url")
        link_type = link_data.get("type")
        category_id = link_data.get("category_id")
        if not (
            validate_link_form_data(name, url, link_type)
            and isinstance(category_id, int)
            and category_id > 0
        ):
            raise ValueError(self.tr("Invalid link data provided"))
        return func(self, link_data, *args, **kwargs)
    return wrapper


def handle_errors(func):
    """Decorator providing centralized error handling."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
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

    # Signals used to notify the UI layer (PyQt6 typed style)
    links_loaded: pyqtSignal = pyqtSignal(
        list, int, int, name='linksLoaded'
    )  # List[Dict], int, int - links, category ID, task ID
    search_results_ready: pyqtSignal = pyqtSignal(
        list, name='searchResultsReady'
    )  # List[Dict] - search results
    favorites_counted: pyqtSignal = pyqtSignal(
        int, list, object, name='favoritesCounted'
    )  # int, List[Dict], Optional[Dict] - count, links, current link
    link_updated: pyqtSignal = pyqtSignal(dict, name='linkUpdated')  # Dict - updated link
    error_occurred: pyqtSignal = pyqtSignal(str, name='errorOccurred')  # str - error message
    link_deleted: pyqtSignal = pyqtSignal(int, name='linkDeleted')  # int - deleted link ID
    recent_links_loaded: pyqtSignal = pyqtSignal(list, name='recentLinksLoaded')  # List[Dict] - recent links
    favorite_links_loaded: pyqtSignal = pyqtSignal(list, name='favoriteLinksLoaded')  # List[Dict] - favorite links
    favorites_cleared: pyqtSignal = pyqtSignal(bool, name='favoritesCleared')  # bool - success flag
    link_by_id_loaded: pyqtSignal = pyqtSignal(dict, int, name='linkByIdLoaded')  # Dict, int - link, ID
    next_position_loaded: pyqtSignal = pyqtSignal(int, int, name='nextPositionLoaded')  # int, int - position, category_id
    batch_updated: pyqtSignal = pyqtSignal(bool, name='batchUpdated')  # bool - batch result

    def __init__(self, db: Database, parent: QObject = None, logger=None, tasks_lock_instance=None, scheduler=None):
        super().__init__(parent)
        self.db = db
        # Service layer atop the repository to reduce duplication and manage transactions
        self.links = LinksService(db)
        # Dependency injection
        self.scheduler = scheduler or get_task_scheduler()
        self._tasks_lock = tasks_lock_instance or tasks_lock
        self.pending_tasks: Dict[int, int] = {}  # Store task_id -> category_id or other payloads
        self.task_counter = 0
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._cache = {}  # Simple cache for results
        self._mutex = threading.RLock()  # Prevent race conditions

    def shutdown(self, timeout: int = DEFAULT_SHUTDOWN_TIMEOUT):
        """Perform a graceful shutdown."""
        try:
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

    def _clear_pending_tasks(self):
        with self._tasks_lock:
            self.pending_tasks.clear()

    def load_links(self, category_id: int):
        """Load links for a category."""
        self.task_counter += 1
        task_id = self.task_counter

        with self._tasks_lock:
            self.pending_tasks[task_id] = category_id

        self.logger.debug(
            "Loading links for category %s, task_id=%s", category_id, task_id
        )

        self._run_db_task(
            lambda: self.db.links.get_links(category_id) or [],
            description=f"load_links(category_id={category_id})",
            on_finished=lambda links: self._on_links_loaded(
                links, category_id, task_id
            ),
            task_id=task_id,
        )

    @handle_errors
    def get_links(self, category_id: int) -> List[Dict]:
        """Return links for a category synchronously (unified method)."""
        self.logger.warning("Using synchronous get_links; consider using load_links for async operation")
        return self._get_cached(
            f"links_{category_id}",
            lambda: self.links.get_links(category_id),
        )

    def search_links(self, query: str):
        """Search links by query."""
        q = (query or "").strip()
        if not q:
            self.logger.debug(
                "Searching links: empty query -> return ALL links (global)"
            )
            self._run_db_task(
                lambda: self.db.links.get_all_links() or [],
                description="search_links(all)",
                on_finished=self._on_search_finished,
            )
            return

        self.logger.debug("Searching links for query: %s", q)

        self._run_db_task(
            lambda: self.db.links.search_links(q) or [],
            description=f"search_links(query={q!r})",
            on_finished=self._on_search_finished,
        )

    def update_link_order(self, link_ids: list):
        """Update the order of links."""
        if not link_ids:
            return

        self.logger.debug("Updating order for %s links", len(link_ids))

        self._run_db_task(
            lambda: self.links.reorder(link_ids),
            description="update_link_order",
            on_finished=self._on_reorder_finished,
        )

    def count_favorites(self, link: Optional[Dict] = None):
        """Count favorite links."""

        def _count():
            return self.db.links.count_favorites()

        self._run_db_task(
            _count,
            description="count_favorites()",
            on_finished=lambda fav_count: self._on_favorites_counted(
                int(fav_count), [], link
            ),
        )

    def delete_link(self, link_id: int):
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
    def save_link(self, link_data: Dict) -> int:
        """Save a link."""
        self.logger.warning("Using synchronous save_link; consider using save_link_async for async")

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
    def save_link_async(self, link_data: Dict):
        """Save a link asynchronously."""
        self._run_db_task(
            lambda: self.links.create_or_update_link(link_data),
            description="save_link_async",
            on_finished=lambda result: self._on_link_saved(link_data, result),
        )

    def _on_link_saved(self, link_data: Dict, result: int):
        if result and not link_data.get("id"):
            link_data["id"] = result
        self._invalidate_cache()
        self.link_updated.emit(link_data)
        self.logger.info("Link saved async: %s", link_data.get("id", "[new]"))

    def update_link_last_used(self, link_id: int):
        """Update the last-used timestamp for a link."""
        if not self._validate_link_id(link_id):
            return

        self._run_db_task(
            lambda: self.links.update_last_used(link_id),
            description=f"update_link_last_used({link_id})",
            on_finished=lambda _: self._on_last_used_updated(link_id),
            task_id=link_id,
        )

    def toggle_favorite(self, link: Dict):
        """Toggle favorite status for a link."""
        if (
            not isinstance(link, dict)
            or not isinstance(link.get("id"), int)
            or link["id"] <= 0
        ):
            raise ValueError(self.tr("Invalid link data for toggle_favorite"))

        link_id = link.get("id")

        # Atomic update: read and modify within a single transaction
        def _toggle() -> tuple[int, Dict]:
            with self._mutex:
                current_link = self.links.get_link_by_id(link_id)
                if not current_link:
                    raise ValueError(self.tr("Link not found"))
                old_status = current_link.get("is_favorite", False)
                new_status = not old_status
                self.logger.debug(
                    "Toggle favorite for link %s: %s -> %s", link_id, old_status, new_status
                )
                link_data = current_link.copy()
                link_data["is_favorite"] = new_status
                result = self.links.create_or_update_link(link_data)
                return result, link_data

        self._run_db_task(
            _toggle,
            description=f"toggle_favorite({link_id})",
            on_finished=lambda data: self._on_favorite_toggled(data[0], data[1]),
            task_id=link_id,
        )

    def _on_favorite_toggled(self, result: int, link_data: Dict):
        self.logger.info(
            "Favorite status updated successfully, result ID: %s", result
        )
        self._invalidate_cache()
        self.count_favorites(link_data)

    @handle_errors
    def get_recent_links(self, limit: int = DEFAULT_RECENT_LIMIT) -> List[Dict]:
        """Retrieve recent links."""
        self.logger.warning("Using synchronous get_recent_links; consider using load_recent_links for async")
        if limit <= 0:
            self.logger.warning("Invalid limit for recent links: %s", limit)
            return []

        return self._get_cached(
            f"recent_links_{limit}",
            lambda: self.links.get_recent_links(limit),
        )

    def load_recent_links(self, limit: int = DEFAULT_RECENT_LIMIT):
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
            on_finished=lambda links: self._cache_links_and_emit(cache_key, links or [], self.recent_links_loaded.emit),
        )

    @handle_errors
    def get_favorite_links(self) -> List[Dict]:
        """Retrieve favorite links."""
        self.logger.warning("Using synchronous get_favorite_links; consider using load_favorite_links for async")
        return self._get_cached(
            "favorite_links",
            self.links.get_favorite_links,
        )

    def load_favorite_links(self):
        """Load favorite links asynchronously."""
        cache_key = "favorite_links"
        if cache_key in self._cache:
            self.favorite_links_loaded.emit(self._cache[cache_key])
            return

        self._run_db_task(
            lambda: self.links.get_favorite_links(),
            description="load_favorite_links",
            on_finished=lambda links: self._cache_links_and_emit(cache_key, links or [], self.favorite_links_loaded.emit),
        )

    @handle_errors
    def clear_favorites(self) -> bool:
        """Clear all favorite links."""
        self.logger.warning("Using synchronous clear_favorites; consider using clear_favorites_async for async")
        result = self.links.clear_favorites() or True
        self._invalidate_cache()
        self.logger.info("Favorite links cleared")
        return result

    def clear_favorites_async(self):
        """Clear favorite links asynchronously."""
        self._run_db_task(
            lambda: self.links.clear_favorites() or True,
            description="clear_favorites_async",
            on_finished=self._on_favorites_cleared,
        )

    @handle_errors
    def get_link_by_id(self, link_id: int) -> Optional[Dict]:
        """Fetch a link by ID."""
        self.logger.warning("Using synchronous get_link_by_id; consider using load_link_by_id for async")
        if not self._validate_link_id(link_id):
            return None

        return self._get_cached(
            f"link_{link_id}",
            lambda: self.links.get_link_by_id(link_id),
        )

    def load_link_by_id(self, link_id: int):
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
            on_finished=lambda link: self._cache_links_and_emit(cache_key, link, lambda link_data: self.link_by_id_loaded.emit(link_data, link_id)),
        )

    @handle_errors
    def get_next_position(self, category_id: int) -> int:
        """Calculate the next position for a new link within a category."""
        self.logger.warning("Using synchronous get_next_position; consider using load_next_position for async")
        if not isinstance(category_id, int) or category_id <= 0:
            self.logger.warning(
                "Invalid category_id for get_next_position: %s", category_id
            )
            return 0

        return self._get_cached(
            f"next_pos_{category_id}",
            lambda: self.links.get_next_position(category_id),
        )

    def load_next_position(self, category_id: int):
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
            on_finished=lambda pos: self._cache_links_and_emit(cache_key, pos, lambda p: self.next_position_loaded.emit(p, category_id)),
        )

    @handle_errors
    def batch_update_links(self, links_data: List[Dict]) -> bool:
        """Perform a transactional batch update of links."""
        self.logger.warning("Using synchronous batch_update_links; consider using batch_update_links_async for async")
        if not links_data:
            self.logger.warning("Empty links_data for batch_update_links")
            return True

        for i, link_data in enumerate(links_data):
            if not isinstance(link_data, dict) or not link_data:
                self.logger.error("Invalid link data at index %s: %s", i, link_data)
                return False

        result = self.links.batch_update(links_data)
        self._invalidate_cache()
        return result

    def batch_update_links_async(self, links_data: List[Dict]):
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

    @validate_link_form
    @handle_errors
    def create_link_for_import(self, link_data: Dict[str, Any]) -> Optional[int]:
        """Create a new link during background data import.

        Args:
            link_data: Dictionary containing the link payload.

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

    @lru_cache(maxsize=32)
    def _get_all_links_safe(self) -> List[Dict]:
        """Return all links for internal usage with caching."""
        return self.links.get_all_links()

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
        run_db(
            task,
            description=description,
            on_finished=on_finished,
            on_error=lambda e: self._on_worker_error(str(e), task_id=task_id),
        )

    def _invalidate_cache(self):
        """Invalidate caches after a mutating operation."""
        self._cache.clear()
        self._get_all_links_safe.cache_clear()  # Clear lru_cache

    def _cache_links_and_emit(self, key: str, data: Any, emit_func):
        self._cache[key] = data
        emit_func(data)

    # Helpers for handling asynchronous results

    def _on_reorder_finished(self, _):
        """Handle completion of a link reordering operation."""
        self._invalidate_cache()
        self.logger.debug("Link reordering completed")

    def _on_delete_finished(self, link_id: int):
        """Handle completion of a link deletion."""
        self._invalidate_cache()
        self.link_deleted.emit(link_id)

    def _on_last_used_updated(self, link_id: int):
        """Handle completion of a last-used timestamp update."""
        self._invalidate_cache()
        self.logger.debug("Link last_used updated: %s", link_id)

    def _on_favorites_cleared(self, result: bool):
        """Handle completion of clearing favorites."""
        self._invalidate_cache()
        self.favorites_cleared.emit(result)

    def _on_batch_updated(self, result: bool):
        """Handle completion of a batch update."""
        self._invalidate_cache()
        self.batch_updated.emit(result)

    # Slots for handling asynchronous results

    @pyqtSlot(object, int, int)
    def _on_links_loaded(self, links: List[Dict], category_id: int, task_id: int):
        """Handle completion of link loading."""
        with self._tasks_lock:
            if task_id in self.pending_tasks:
                del self.pending_tasks[task_id]
                self.links_loaded.emit(links or [], category_id, task_id)

    @pyqtSlot(object)
    def _on_search_finished(self, search_results: List[Dict]):
        """Handle completion of a search operation."""
        self.search_results_ready.emit(search_results or [])

    @pyqtSlot(int, object, object)
    def _on_favorites_counted(
        self, fav_count: int, links: List[Dict], link: Optional[Dict]
    ):
        """Handle completion of counting favorites."""
        self.favorites_counted.emit(fav_count, links or [], link)

    @pyqtSlot(str)
    def _on_worker_error(self, error_msg: str, task_id: Optional[int] = None):
        """Handle errors emitted by background workers."""
        self.logger.error("Worker error: %s", error_msg)
        self.error_occurred.emit(str(error_msg))
        if task_id and task_id in self.pending_tasks:
            with self._tasks_lock:
                del self.pending_tasks[task_id]