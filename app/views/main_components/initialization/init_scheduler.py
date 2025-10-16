# app/views/main_components/init_scheduler.py
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication


class AsyncStepRunner:
    """Universal runner that executes asynchronous initialization steps.

    Steps are performed sequentially while yielding back to the UI event loop,
    timing metrics are recorded, and optional post-hooks are supported.
    """

    def __init__(
        self,
        metrics,
        set_status_message: Callable[[str], None],
    ) -> None:
        self._metrics = metrics
        self._set_status_message = set_status_message

    def run(
        self,
        steps: List[Tuple[str, Callable[[], None]]],
        index_getter: Callable[[], int],
        index_setter: Callable[[int], None],
        on_completed: Callable[[], None],
        on_error: Optional[Callable[[Exception], None]] = None,
        special_hooks: Optional[Dict[Callable[[], None], Callable[[], None]]] = None,
    ) -> None:
        """Run the provided steps sequentially.

        Args:
            steps: List of pairs ``(label, step_func)`` with no-argument callables.
            index_getter: Function that returns the current step index.
            index_setter: Function that stores the next step index.
            on_completed: Callback that runs after all steps finish.
            special_hooks: Optional callbacks that run after specific steps.
        """
        QTimer.singleShot(
            0,
            lambda: self._execute_next(
                steps, index_getter, index_setter, on_completed, on_error, special_hooks
            ),
        )

    # Internal recursive helper
    def _execute_next(
        self,
        steps: List[Tuple[str, Callable[[], None]]],
        index_getter: Callable[[], int],
        index_setter: Callable[[int], None],
        on_completed: Callable[[], None],
        on_error: Optional[Callable[[Exception], None]],
        special_hooks: Optional[Dict[Callable[[], None], Callable[[], None]]],
    ) -> None:
        idx = int(index_getter())
        if idx >= len(steps):
            on_completed()
            return

        step_name, step_func = steps[idx]
        # Update status (if already available)
        try:
            self._set_status_message(step_name)
        except Exception:
            # Do not interrupt execution, just log the failure to update status
            import logging as _logging

            _logging.getLogger(__name__).debug(
                "AsyncStepRunner: failed to set status message: %s",
                step_name,
                exc_info=True,
            )

        # Execute the step while recording metrics
        try:
            with self._metrics.time_span(f"heavy:{step_func.__name__}"):
                step_func()
        except Exception as e:
            if on_error:
                try:
                    on_error(e)
                finally:
                    return
            else:
                raise

        # Run special hooks after completing the step
        if special_hooks and step_func in special_hooks:
            try:
                special_hooks[step_func]()
            except Exception as e:
                if on_error:
                    try:
                        on_error(e)
                    finally:
                        return
                # Swallow the exception to keep the pipeline running, but log it
                import logging as _logging

                _logging.getLogger(__name__).debug(
                    "AsyncStepRunner: special hook failed for %s",
                    getattr(step_func, "__name__", str(step_func)),
                    exc_info=True,
                )

        # Increment the index and continue
        index_setter(idx + 1)

        # Let the UI thread process pending events
        QApplication.processEvents()

        # Schedule the next step
        QTimer.singleShot(
            0,
            lambda: self._execute_next(
                steps, index_getter, index_setter, on_completed, on_error, special_hooks
            ),
        )
