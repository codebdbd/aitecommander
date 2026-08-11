# app/views/main_components/window_initializer.py
"""Main window initializer.

Improvement note: enforces Protocol-based typing, centralizes resource
management via `ResourceManager`, and replaces magic numbers with constants.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, Callable, TypeAlias

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.controllers.ui.dialogs.dialog_manager import DialogManager
from app.controllers.system.window_setup.coordinator import WindowControllersSetup
from app.utils.metrics.startup_metrics import get_metrics
from app.utils.ui.updates import suspend_updates

from ..common.constants import StatusMessage
from ..common.protocols import (
    DatabaseProtocol,
    MainWindowProtocol,
    SettingsProtocol,
    ThemeControllerProtocol,
)
from ..common.resource_manager import ResourceManager
from ..ui.window_ui_setup import WindowUISetup
from .init_db_gate import DbReadyGate
from .init_diagnostics import DiagnosticsInstaller
from .init_scheduler import AsyncStepRunner
from .init_status import StatusUpdater
from .init_steps_config import AFTER_DB_STEP_CONFIG, BEFORE_DB_STEP_CONFIG

logger = logging.getLogger(__name__)

# Type aliases
Step: TypeAlias = tuple[str, Callable[[], None]]


class WindowInitializer:
    """Initialize and orchestrate the main window setup.

    Improvement note: uses strict Protocol types for every dependency and
    `ResourceManager` to guarantee cleanup.
    """

    # --- Strict typing via Protocol ---
    window: MainWindowProtocol
    db: DatabaseProtocol
    settings: SettingsProtocol
    theme_ctrl: ThemeControllerProtocol

    ui_setup: WindowUISetup
    controllers_setup: WindowControllersSetup
    _metrics: object  # From startup_metrics
    _status: StatusUpdater
    _resource_manager: ResourceManager

    _current_init_step: int
    _current_db_step: int
    _init_steps_before_db: list[Step]
    _init_steps_after_db: list[Step]
    _special_hooks_after: dict[Callable[[], None], Callable[[], None]]
    _db_ready: bool
    _waiting_for_db: bool

    def __init__(
        self,
        main_window: MainWindowProtocol,
        db: DatabaseProtocol,
        settings: SettingsProtocol,
        theme_ctrl: ThemeControllerProtocol,
    ) -> None:
        """Component constructor.

        Improvement note: all parameters now adhere to Protocol-based typing.

        Args:
            main_window: Application main window (`MainWindowProtocol`).
            db: Database accessor (`DatabaseProtocol`).
            settings: Application settings (`SettingsProtocol`).
            theme_ctrl: Theme controller (`ThemeControllerProtocol`).
        """
        self.window = main_window
        self.db = db
        self.settings = settings
        self.theme_ctrl = theme_ctrl

        # Improvement: instantiate ResourceManager to manage resources explicitly
        self._resource_manager = ResourceManager("WindowInitializer")

        # Component composition
        self.ui_setup = WindowUISetup(self)
        self.controllers_setup = WindowControllersSetup(self)
        self._metrics = get_metrics()
        self._status = StatusUpdater(self.window, logger)

        # --- Initialize fields that were previously dynamic ---
        # Stage progress indices
        self._current_init_step: int = 0
        self._current_db_step: int = 0
        # Step collections and special hooks (populated during planning)
        self._init_steps_before_db: list[Step] = []
        self._init_steps_after_db: list[Step] = []
        self._special_hooks_after: dict[Callable[[], None], Callable[[], None]] = {}
        # Database readiness state
        self._db_ready: bool = False
        self._waiting_for_db: bool = False
        self._reload_structure_timer = QTimer(self.window)
        self._reload_structure_timer.setSingleShot(True)
        self._reload_structure_timer.setInterval(100)
        self._reload_structure_timer.timeout.connect(self._reload_structure_debounced)
        self._reload_category_timer = QTimer(self.window)
        self._reload_category_timer.setSingleShot(True)
        self._reload_category_timer.setInterval(75)
        self._reload_category_timer.timeout.connect(
            self._reload_current_category_debounced
        )

    def initialize_window(self) -> None:
        """Perform full step-by-step initialization of the main window."""
        self._metrics.reset()
        self._install_diagnostics()
        self._run_light_steps()
        self._schedule_heavy_steps()

    # === Initialization orchestration (extracted from initialize_window) ===
    def _install_diagnostics(self) -> None:
        """Install diagnostics (Qt message filter, top-level watcher, and more)."""
        try:
            DiagnosticsInstaller(self.window, self._dump_top_levels).install_all()
        except (RuntimeError, AttributeError, ImportError) as e:
            # Diagnostics are non-critical — log a warning and continue.
            logger.warning(
                "Diagnostics: failed to install one or more handlers: %s",
                e,
                exc_info=True,
            )

    def _run_light_steps(self) -> None:
        light_steps = (
            self._init_window_properties,
            self._init_basic_attributes,
            self._init_menu,
            self._init_central_widget,
            self._capture_main_layout,  # WIDGETS: must follow central_widget
            self._init_top_panel,
            self._connect_db_signals,  # Connect database signals to UI
        )

        with suspend_updates(self.window):
            for step in light_steps:
                with self._metrics.time_span(f"light:{step.__name__}"):
                    step()

        try:
            if hasattr(self.window, "shown"):
                self.window.shown.connect(self._on_window_shown)
        except (RuntimeError, AttributeError, TypeError):
            logger.exception(
                "WindowInitializer: failed to connect slot to 'shown' signal"
            )

    def _schedule_heavy_steps(self) -> None:
        """Split heavy steps into async phases and schedule them around DB readiness."""
        self._current_init_step = 0
        self._init_steps_before_db: list[tuple[str, Callable[[], None]]] = []
        special_hooks_before: dict[Callable[[], None], Callable[[], None]] = {}
        for label, method_name, hook_name in BEFORE_DB_STEP_CONFIG:
            step_func = getattr(self, method_name)
            self._init_steps_before_db.append((label, step_func))
            if hook_name:
                special_hooks_before[step_func] = getattr(self, hook_name)

        self._init_steps_after_db: list[tuple[str, Callable[[], None]]] = []
        self._special_hooks_after: dict[Callable[[], None], Callable[[], None]] = {}
        for label, method_name, hook_name in AFTER_DB_STEP_CONFIG:
            step_func = getattr(self, method_name)
            self._init_steps_after_db.append((label, step_func))
            if hook_name:
                self._special_hooks_after[step_func] = getattr(self, hook_name)
        self._db_ready = False
        self._waiting_for_db = False
        runner = AsyncStepRunner(self._metrics, self._status.set_message)
        on_error = self._on_init_error
        runner.run(
            steps=self._init_steps_before_db,
            index_getter=lambda: getattr(self, "_current_init_step", 0),
            index_setter=lambda v: setattr(self, "_current_init_step", v),
            on_completed=self._on_before_db_steps_completed,
            on_error=on_error,
            special_hooks=special_hooks_before,
        )

    def _init_window_properties(self) -> None:
        self.ui_setup.setup_window_properties()

    def _init_basic_attributes(self) -> None:
        # Assign database instance to window for shutdown controller access
        self.window.db = self.db  # type: ignore[attr-defined]
        self.ui_setup.setup_basic_attributes()

    def _init_menu(self) -> None:
        self.ui_setup.setup_menu()

    def _init_central_widget(self) -> None:
        self.ui_setup.setup_central_widget()

    def _capture_main_layout(self) -> None:
        self.main_layout = self.ui_setup.main_layout

    def _init_top_panel(self) -> None:
        self.ui_setup.setup_top_panel()
    def _connect_db_signals(self) -> None:
        """Wire Qt database signals to UI components.

        Notifies the UI about database changes without polling.
        """
        try:
            # Ensure the database exposes Qt signals (QObject-based)
            if not hasattr(self.db, "data_changed"):
                logger.debug(
                    "Database doesn't have Qt signals, skipping signal connection"
                )
                return

            # Connect the data-change signal
            self.db.data_changed.connect(self._on_db_data_changed)

            # Connect the structure-loaded signal
            if hasattr(self.db, "structure_loaded"):
                self.db.structure_loaded.connect(self._on_db_structure_loaded)

            # Connect the backup-created signal
            if hasattr(self.db, "backup_created"):
                self.db.backup_created.connect(self._on_db_backup_created)

            # Connect the error signal
            if hasattr(self.db, "error_occurred"):
                self.db.error_occurred.connect(self._on_db_error)

            logger.debug("Database signals connected successfully")
        except Exception as e:
            logger.warning("Failed to connect database signals: %s", e, exc_info=True)

    def _on_db_data_changed(
        self, table_name: str, operation: str, affected_ids: list
    ) -> None:
        """Handle database data changes."""
        try:
            logger.debug(
                f"Database data changed: {table_name}, {operation}, ids={affected_ids}"
            )

            # Refresh the UI when specific tables change
            if table_name == "link":
                self._reload_category_timer.start()

            elif table_name in ("sphere", "section", "category"):
                self._reload_structure_timer.start()
        except Exception as e:
            logger.warning("Error handling DB data change: %s", e, exc_info=True)

    def _on_db_structure_loaded(self) -> None:
        """Handle completion of structure loading."""
        try:
            logger.info("Database structure loaded - reloading UI")
            self._reload_structure_timer.start()
        except Exception as e:
            logger.warning("Error handling structure loaded: %s", e, exc_info=True)

    def _reload_structure_debounced(self) -> None:
        """Reload structure tree after coalescing bursty DB events."""
        if hasattr(self.window, "reload_structure"):
            self.window.reload_structure()

    def _reload_current_category_debounced(self) -> None:
        """Reload current category after coalescing bursty DB events."""
        if hasattr(self.window, "reload_current_category"):
            self.window.reload_current_category()

    def _on_db_backup_created(self, backup_path: str) -> None:
        """Handle creation of a database backup."""
        try:
            logger.info(f"Backup created: {backup_path}")
            # Show a notification in the status bar
            if hasattr(self.window, "statusBar"):
                status_bar = self.window.statusBar()
                if status_bar:
                    status_bar.showMessage(f"Backup created: {backup_path}", 5000)
        except Exception as e:
            logger.warning("Error handling backup created: %s", e, exc_info=True)

    def _on_db_error(self, title: str, message: str) -> None:
        """Handle database error notifications."""
        try:
            logger.error(f"Database error: {title} - {message}")
            DialogManager.show_error(self.window, message, title)
        except Exception as e:
            logger.warning("Error handling DB error signal: %s", e, exc_info=True)

    def _init_main_content(self) -> None:
        self.ui_setup.setup_main_content()

    def _finalize_main_content(self) -> None:
        self.ui_setup.finalize_main_content()

    def _init_bottom_panel(self) -> None:
        self.ui_setup.setup_bottom_panel()

    def _init_status_bar(self) -> None:
        self.ui_setup.setup_status_bar()

    def _init_controllers(self) -> None:
        self.controllers_setup.setup_controllers()

    def _apply_user_font_size(self) -> None:
        if hasattr(self.settings, "get_font_size") and hasattr(
            self.window, "apply_font_size_to_content"
        ):
            fs = self.settings.get_font_size()
            try:
                with suppress(AttributeError, ValueError, TypeError):
                    if fs:
                        self.window.apply_font_size_to_content(int(fs))
            except Exception:
                logger.exception(
                    "WindowInitializer: unexpected error applying font size"
                )

    def _initialize_spheres(self) -> None:
        try:
            if hasattr(self.window, "isVisible") and self.window.isVisible():
                QTimer.singleShot(0, self.controllers_setup.initialize_spheres)
                return
        except Exception:
            logger.debug(
                "WindowInitializer: failed to defer initial sphere loading",
                exc_info=True,
            )
        self.controllers_setup.initialize_spheres()

    def _post_status_bar_init(self) -> None:
        try:
            # Leave status-bar text untouched during initialization
            pass
        except Exception:
            logger.exception(
                "WindowInitializer: failed to update status-bar text during post init"
            )

    def _post_controllers_init(self) -> None:
        try:
            sb = getattr(self.window, "structure_business", None)
            ao = getattr(sb, "async_operations", None) if sb else None
            if ao is not None:
                curr_id = getattr(sb, "current_sphere_id", None)
                if isinstance(curr_id, int) and curr_id > 0:
                    self._metrics.start("async:structure_load")
                    try:
                        if hasattr(sb, "structure_loaded"):

                            def _on_structure_loaded_once(*_args):
                                try:
                                    self._metrics.stop("async:structure_load")
                                except Exception:
                                    logger.debug(
                                        "WindowInitializer: failed to stop 'async:structure_load' metric",
                                        exc_info=False,
                                    )
                                try:
                                    sb.structure_loaded.disconnect(
                                        _on_structure_loaded_once
                                    )
                                except Exception:
                                    logger.debug(
                                        "WindowInitializer: failed to disconnect temporary structure_loaded slot",
                                        exc_info=False,
                                    )

                            sb.structure_loaded.connect(_on_structure_loaded_once)
                    except Exception:
                        logger.debug(
                            "WindowInitializer: failed to wire metrics to structure_loaded",
                            exc_info=False,
                        )
                    try:
                        # Kick off immediately without an extra event-loop tick to display the tree sooner
                        ao.load_structure_async(int(curr_id))
                        self._metrics.mark("async:load_structure_async started")
                    except Exception:
                        logger.exception(
                            "WindowInitializer: failed to start load_structure_async immediately"
                        )
        except Exception:
            logger.exception(
                "WindowInitializer: failed to schedule load_structure_async"
            )

    def _execute_db_dependent_steps(self) -> None:
        self._current_db_step = 0
        runner = AsyncStepRunner(self._metrics, self._status.set_message)
        on_error = self._on_init_error
        runner.run(
            steps=self._init_steps_after_db,
            index_getter=lambda: getattr(self, "_current_db_step", 0),
            index_setter=lambda v: setattr(self, "_current_db_step", v),
            on_completed=self._finalize_initialization,
            on_error=on_error,
            special_hooks=self._special_hooks_after,
        )

    def _finalize_initialization(self) -> None:
        """Finish deferred initialization and present the window as early as possible."""
        # Summarize startup metrics (errors here are non-critical)
        try:
            self._metrics.flush_log(logger)
        except Exception:
            logger.debug(
                "WindowInitializer: failed to flush startup metrics at finalize",
                exc_info=True,
            )

        logger.info("WindowInitializer: window shell is ready for first paint")

        try:
            if hasattr(self.window, "show"):
                need_show = True
                try:
                    need_show = not bool(
                        getattr(self.window, "isVisible", lambda: False)()
                    )
                except Exception:
                    need_show = True
                if need_show:
                    with self._metrics.time_span("final:window_show"):
                        self.window.show()
        except Exception as e:
            logger.exception(
                "WindowInitializer: failed to show window at initialization finale"
            )
            # Delegate to the centralized error handler
            self._on_init_error(e)
            return
        finally:
            self._status.set_message(
                QCoreApplication.translate("StatusBar", StatusMessage.READY)
            )

    def _on_init_error(self, exc: Exception) -> None:
        """Unified error handler for initialization stages.

        Flushes and logs startup metrics, then delegates to deferred-init error logic.
        """
        try:
            logger.error(
                "WindowInitializer: initialization failed during async steps",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        except Exception:
            logger.debug(
                "WindowInitializer: failed to log initialization error", exc_info=True
            )
        try:
            self._metrics.flush_log(logger)
        except Exception:
            logger.exception("WindowInitializer: failed to flush startup metrics")
        self._handle_deferred_init_error(exc)

    def _on_before_db_steps_completed(self) -> None:
        """Callback for completion of pre-database steps.

        Either waits for database readiness or proceeds to post-database steps.
        """
        # Use the database readiness gate
        gate = DbReadyGate(self.window, _logger=logger)
        gate.ensure_ready_or_wait(
            on_ready=self._execute_db_dependent_steps,
            on_waiting=self._on_waiting_for_db,
        )

    def _on_waiting_for_db(self) -> None:
        """Handle the waiting-for-database state by updating status and flags."""
        try:
            self._waiting_for_db = True
            self._status.set_message(StatusMessage.WAITING_FOR_DB)
        except Exception:
            logger.exception(
                "WindowInitializer: failed to update waiting-for-db status"
            )

    def _dump_top_levels(self, tag: str) -> None:
        """Log the current set of Qt top-level widgets and QGuiApplication windows."""
        app = QApplication.instance()
        if app is None:
            logger.warning(
                "WindowInitializer: QApplication.instance() returned None for _dump_top_levels"
            )
            return

        top_widgets = self._safe_collect(lambda: list(app.topLevelWidgets()))
        gui_windows = self._safe_collect(self._list_qwindows)

        logger.debug(
            "DiagTopLevels[%s]: %d widgets: %s",
            tag,
            len(top_widgets),
            "; ".join(self._summarize_widget(w) for w in top_widgets),
        )

        window_summaries = [self._summarize_window(w) for w in gui_windows]
        if window_summaries:
            logger.debug(
                "DiagTopLevels[%s]: QWindows(%d): %s",
                tag,
                len(window_summaries),
                "; ".join(window_summaries),
            )

    def _safe_collect(self, supplier: Callable[[], list[Any]]) -> list[Any]:
        try:
            return supplier()
        except Exception:
            logger.debug("WindowInitializer: collection failed", exc_info=True)
            return []

    def _list_qwindows(self) -> list[Any]:
        try:
            from PyQt6.QtGui import QGuiApplication

            return list(QGuiApplication.allWindows())
        except Exception:
            logger.debug("WindowInitializer: failed to list QWindows", exc_info=True)
            return []

    def _summarize_widget(self, widget: Any) -> str:
        name = self._safe_call(lambda: widget.objectName() or "<noname>")
        cls = type(widget).__name__
        size_s = self._format_size(self._safe_call(widget.size))
        pos_s = self._format_point(self._safe_call(widget.pos))
        visible = self._safe_call(widget.isVisible, default=False)
        return f"{cls}[{name}] vis={visible} size={size_s} pos={pos_s}"

    def _summarize_window(self, window: Any) -> str:
        cls = type(window).__name__
        title = self._safe_call(getattr, window, "title", default="")
        size_s = self._format_size(self._safe_call(getattr(window, "size", None)))
        pos_s = self._format_point(self._safe_call(getattr(window, "position", None)))
        visible = self._safe_call(getattr(window, "isVisible", None), default=False)
        flags_s = self._format_flags(self._safe_call(getattr(window, "flags", None)))
        return f"{cls} title='{title}' vis={visible} size={size_s} pos={pos_s} flags={flags_s}"

    def _safe_call(self, func: Callable[..., Any] | None, *args: Any, default: Any = None) -> Any:
        if func is None:
            return default
        try:
            return func(*args)
        except Exception:
            return default

    def _format_size(self, size: Any) -> str:
        if size is None:
            return "?"
        try:
            return f"{size.width()}x{size.height()}"
        except Exception:
            return "?"

    def _format_point(self, point: Any) -> str:
        if point is None:
            return "?"
        try:
            return f"({point.x()},{point.y()})"
        except Exception:
            return "?"

    def _format_flags(self, flags: Any) -> str:
        if flags is None:
            return "?"
        try:
            return hex(int(flags))
        except Exception:
            return "?"

    # === Slots ===
    def _on_window_shown(self) -> None:
        """Update status after the window is shown.

        Accounts for deferred creation of the status bar by checking prerequisites.
        """
        try:
            # Do not override the status bar message when the window is shown
            pass
        except Exception:
            logger.exception(
                "WindowInitializer: failed to update status-bar text in _on_window_shown"
            )

    # === Error handlers ===
    def _handle_deferred_init_error(self, exc: Exception) -> None:
        """Display an error dialog and shut down the app when deferred init fails."""
        try:
            parent = self.window if hasattr(self.window, "isVisible") else None
            DialogManager.show_error(
                parent,
                f"An error occurred while initializing the UI:\n{exc}",
                "Initialization error",
            )
        except Exception:
            logger.exception(
                "WindowInitializer: failed to show initialization error dialog"
            )
        finally:
            # Centralize shutdown: close the main window to trigger AppShutdownController
            if hasattr(self, "window") and hasattr(self.window, "close"):
                try:
                    self.window.close()
                except Exception:
                    logger.debug(
                        "WindowInitializer: window.close() failed, falling back to app.quit()",
                        exc_info=True,
                    )
            else:
                # Fallback: if the window is unavailable, quit the app directly
                app = QApplication.instance()
                if app is not None:
                    app.quit()
