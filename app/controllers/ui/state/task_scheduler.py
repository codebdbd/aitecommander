"""
Unified task scheduler for managing concurrency and deferred operations.

Moved from app/utils/system/task_scheduler.py to UI state layer.
Preserves previous API (TaskScheduler, get_task_scheduler, schedule_*) for
backward compatibility of internal application calls.
"""

import logging
from enum import Enum
from typing import Any, Callable, Optional

from PyQt6.QtCore import (
    QCoreApplication,
    QObject,
    QRunnable,
    QThread,
    QThreadPool,
    QTimer,
    pyqtSignal,
)

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Task types for grouping."""

    FOCUS_MANAGEMENT = "focus"
    SELECTION_RESTORE = "selection"
    UI_LAYOUT = "layout"
    TABLE_UPDATE = "table"
    GENERAL = "general"
    BACKGROUND_TASK = "background"


class LimitedThreadPool(QThreadPool):
    """Thread pool with maximum thread count limit."""

    def __init__(self, max_threads=4, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.setMaxThreadCount(max_threads)
        self.max_threads = max_threads


class TaskScheduler(QObject):
    """Unified task scheduler for managing threads and timers."""

    # Class signal for thread-safe scheduling (QueuedConnection between threads)
    _schedule_sig = pyqtSignal(object, object, object, object, bool)

    def __init__(self, max_threads=4) -> None:
        super().__init__()
        # Bind handler to signal (in main thread)
        self._schedule_sig.connect(self._handle_schedule_request)
        # Initialize thread pool
        self.thread_pool = LimitedThreadPool(max_threads, self)

        # Initialize timers
        self._active_timers: dict[str, QTimer] = {}
        self._pending_operations: dict[TaskType, dict[str, Callable[..., Any]]] = {
            task_type: {} for task_type in TaskType
        }
        self._default_delays = {
            TaskType.FOCUS_MANAGEMENT: 0,  # Immediately after event loop
            TaskType.SELECTION_RESTORE: 100,  # Standard delay for restoration
            TaskType.UI_LAYOUT: 0,  # Immediately for layout
            TaskType.TABLE_UPDATE: 100,  # Standard delay for tables
            TaskType.GENERAL: 50,  # General default delay
            TaskType.BACKGROUND_TASK: 10,  # Delay for background tasks
        }

        # Timers for batching operations
        self._batch_timers: dict[TaskType, QTimer] = {}
        self._setup_batch_timers()
        self._about_to_quit_connected = self._register_about_to_quit_hook()

    def _handle_schedule_request(
        self,
        operation: Callable[..., Any],
        task_type: TaskType,
        delay: Optional[int],
        operation_id: str,
        replace_existing: bool,
    ) -> None:
        """Signal handler: executes scheduling logic in object owner thread."""
        # Reuse real schedule_operation logic, but without re-checking thread
        # Small encapsulation of common part
        self._schedule_operation_internal(
            operation, task_type, delay, operation_id, replace_existing
        )

    def _setup_batch_timers(self):
        """Configures timers for batching operations by types."""
        for task_type in TaskType:
            timer = QTimer(self)
            timer.setSingleShot(True)
            # Use lambda function with closure for proper task_type passing
            timer.timeout.connect(
                lambda t=task_type: self._execute_batched_operations(t)
            )
            self._batch_timers[task_type] = timer

    def _register_about_to_quit_hook(self) -> bool:
        """Ensure thread pool drains gracefully when the app shuts down."""
        app = QCoreApplication.instance()
        if app is None:
            logger.debug(
                "TaskScheduler: no QCoreApplication instance for shutdown hook"
            )
            return False
        try:
            app.aboutToQuit.connect(self._on_app_about_to_quit)
            return True
        except Exception as exc:
            logger.warning("TaskScheduler: failed to connect aboutToQuit hook: %s", exc)
            return False

    def schedule_operation(
        self,
        operation: Callable[..., Any],
        task_type: TaskType = TaskType.GENERAL,
        delay: Optional[int] = None,
        operation_id: Optional[str] = None,
        replace_existing: bool = True,
    ) -> str:
        """
        Schedules operation execution with optimization.

        Args:
            operation: Function to execute
            task_type: Operation type for grouping
            delay: Delay in ms (None = use default)
            operation_id: Unique operation ID (None = auto-generation)
            replace_existing: Whether to replace existing operation with same ID

        Returns:
            Operation ID for possible cancellation
        """
        if delay is None:
            delay = self._default_delays[task_type]

        if operation_id is None:
            operation_key = f"{task_type.value}_{id(operation)}"
        else:
            operation_key = str(operation_id)

        # If called from another thread — send request via signal (queued connection)
        if QThread.currentThread() is not self.thread():
            try:
                self._schedule_sig.emit(
                    operation, task_type, delay, operation_key, replace_existing
                )
            except Exception as e:
                logger.error(
                    "Failed to schedule operation via signal %s: %s",
                    operation_key,
                    e,
                )
            return operation_key

        # Otherwise — same thread, can schedule directly
        self._schedule_operation_internal(
            operation, task_type, delay, operation_key, replace_existing
        )
        return operation_key

    def _schedule_operation_internal(
        self,
        operation: Callable[..., Any],
        task_type: TaskType,
        delay: Optional[int],
        operation_id: str,
        replace_existing: bool,
    ) -> None:
        """Common logic for queuing operation and starting timer.
        Called either from same thread or via queued signal.
        """
        # Check if operation with this ID already exists
        if operation_id in self._pending_operations[task_type]:
            if not replace_existing:
                logger.debug("Operation %s already scheduled, skipping", operation_id)
                return
            else:
                logger.debug("Replacing existing operation %s", operation_id)

        # Add operation to queue
        self._pending_operations[task_type][operation_id] = operation

        # Start or restart batch timer for this type
        batch_timer = self._batch_timers.get(task_type)
        if batch_timer is None:
            return
        if batch_timer.isActive():
            batch_timer.stop()

        if delay is not None:
            batch_timer.start(delay)

        logger.debug(
            "Scheduled operation %s of type %s with delay %sms",
            operation_id,
            task_type.value,
            delay,
        )

    def _execute_batched_operations(self, task_type: TaskType):
        """Executes all accumulated operations of specific type."""
        operations = self._pending_operations[task_type]
        if not operations:
            return

        logger.debug(
            "Executing %s operations of type %s", len(operations), task_type.value
        )

        # Special handling for focus operations - execute only the last one
        if task_type == TaskType.FOCUS_MANAGEMENT:
            if operations:
                # Take last operation (most recent)
                last_operation_id = list(operations.keys())[-1]
                last_operation = operations[last_operation_id]
                try:
                    last_operation()
                    logger.debug("Executed focus operation: %s", last_operation_id)
                except Exception as e:
                    logger.error(
                        "Error executing focus operation %s: %s", last_operation_id, e
                    )
        else:
            # For other types execute all operations
            for operation_id, operation in operations.items():
                try:
                    operation()
                    logger.debug("Executed operation: %s", operation_id)
                except Exception as e:
                    logger.error(
                        "Error executing operation %s: %s", operation_id, str(e)
                    )

        # Clear executed operations
        operations.clear()

    def cancel_operation(
        self, operation_id: str, task_type: Optional[TaskType] = None
    ) -> bool:
        """
        Cancels scheduled operation.

        Args:
            operation_id: ID of operation to cancel
            task_type: Operation type (None = search in all types)

        Returns:
            True if operation was found and cancelled
        """
        if task_type:
            search_types = [task_type]
        else:
            search_types = list(TaskType)

        for tt in search_types:
            if operation_id in self._pending_operations[tt]:
                del self._pending_operations[tt][operation_id]
                logger.debug(
                    "Cancelled operation %s of type %s", operation_id, tt.value
                )
                return True

        logger.debug("Operation %s not found for cancellation", operation_id)
        return False

    def submit_task(self, task: QRunnable) -> None:
        """
        Sends task to thread pool for execution.

        Args:
            task: Task to execute (QRunnable)
        """
        self.thread_pool.start(task)
        logger.debug("Task sent to thread pool")

    def get_thread_pool(self) -> "LimitedThreadPool":
        """Returns thread pool."""
        return self.thread_pool

    def schedule_focus_operation(
        self, widget_focus_func: Callable, widget_name: Optional[str] = None
    ) -> str:
        """Convenient method for scheduling focus setting operations."""
        operation_id = f"focus_{widget_name or id(widget_focus_func)}"
        return self.schedule_operation(
            widget_focus_func,
            TaskType.FOCUS_MANAGEMENT,
            operation_id=operation_id,
            replace_existing=True,
        )

    def schedule_selection_restore(
        self,
        restore_func: Callable,
        item_id: Optional[Any] = None,
        delay: Optional[int] = None,
    ) -> str:
        """Convenient method for scheduling selection restoration."""
        operation_id = f"selection_{item_id or id(restore_func)}"
        return self.schedule_operation(
            restore_func,
            TaskType.SELECTION_RESTORE,
            delay=delay,
            operation_id=operation_id,
            replace_existing=True,
        )

    def schedule_layout_operation(
        self, layout_func: Callable, layout_name: Optional[str] = None
    ) -> str:
        """Convenient method for scheduling layout operations."""
        operation_id = f"layout_{layout_name or id(layout_func)}"
        return self.schedule_operation(
            layout_func,
            TaskType.UI_LAYOUT,
            operation_id=operation_id,
            replace_existing=True,
        )

    def get_pending_operations_count(self, task_type: Optional[TaskType] = None) -> int:
        """Returns number of pending operations."""
        if task_type:
            return len(self._pending_operations[task_type])
        else:
            return sum(len(ops) for ops in self._pending_operations.values())

    def clear_all_operations(self):
        """Clears all scheduled operations and stops timers."""
        for timer in self._batch_timers.values():
            if timer.isActive():
                timer.stop()

        for operations in self._pending_operations.values():
            operations.clear()

        logger.info("All scheduled operations cleared")

    def _on_app_about_to_quit(self) -> None:
        """Flush timers and wait for background tasks before exit."""
        try:
            self.clear_all_operations()
            if self.thread_pool:
                self.thread_pool.waitForDone(3000)
        except Exception as exc:
            logger.warning("TaskScheduler: shutdown cleanup failed: %s", exc)


# Global task scheduler instance (preserved for compatibility within project)
_task_scheduler_instance: Optional[TaskScheduler] = None


def get_task_scheduler() -> TaskScheduler:
    """Returns global TaskScheduler instance (singleton).
    May be replaced with provider from UIStateManager in future.
    """
    global _task_scheduler_instance
    if _task_scheduler_instance is None:
        _task_scheduler_instance = TaskScheduler()
        logger.info("Created global TaskScheduler")
    return _task_scheduler_instance


def schedule_focus(
    widget_focus_func: Callable, widget_name: Optional[str] = None
) -> str:
    """Global function for scheduling focus setting."""
    return get_task_scheduler().schedule_focus_operation(widget_focus_func, widget_name)


def schedule_selection_restore(
    restore_func: Callable,
    item_id: Optional[Any] = None,
    delay: Optional[int] = None,
) -> str:
    """Global function for scheduling selection restoration."""
    return get_task_scheduler().schedule_selection_restore(restore_func, item_id, delay)


def schedule_layout(layout_func: Callable, layout_name: Optional[str] = None) -> str:
    """Global function for scheduling layout operations."""
    return get_task_scheduler().schedule_layout_operation(layout_func, layout_name)


def schedule_operation(
    operation: Callable,
    task_type: TaskType = TaskType.GENERAL,
    delay: Optional[int] = None,
    operation_id: Optional[str] = None,
) -> str:
    """Global function for scheduling arbitrary operations."""
    return get_task_scheduler().schedule_operation(
        operation, task_type, delay, operation_id
    )


def submit_task(task: QRunnable) -> None:
    """Global function for submitting tasks to thread pool."""
    get_task_scheduler().submit_task(task)
