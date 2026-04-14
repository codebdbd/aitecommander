from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from functools import partial, wraps
from pathlib import Path
from time import perf_counter
from typing import Protocol

from PyQt6.QtCore import (
    QT_TRANSLATE_NOOP,
    QCoreApplication,
    QEvent,
    QFile,
    QObject,
    QSize,
    Qt,
    QTimer,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.controllers.ui.undo.stack import UndoManager
from app.core.constants import AppConstants
from app.core.paths.path_manager import PathManager
from app.core.settings_manager import SettingsManager
from app.core.strings import WindowStrings
from app.utils.cache.topbar_snapshot import TopBarSnapshot, TopBarSnapshotStore
from app.utils.ui.focus import WidgetRegistry, WidgetType
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.views.main_components.ui.topbar.top_bar_layout_manager import (
    TopBarLayoutManager,
)
from app.views.models.structure_tree_model import StructureTreeModel
from app.views.widgets.custom_widgets import StructureTreeView
from app.views.widgets.panels.favorites_panel_widget import FavoritesPanelWidget
from app.views.widgets.panels.quick_add_panel_widget import QuickAddPanelWidget
from app.views.widgets.panels.recent_panel_widget import RecentPanelWidget
from app.views.widgets.status_bar import setup_status_bar as init_status_bar
from i18n.language_service import LanguageService

logger = logging.getLogger(__name__)

_SEARCH_PLACEHOLDER = QT_TRANSLATE_NOOP(
    "WindowUISetup", WindowStrings.SEARCH_PLACEHOLDER
)


class UIConstants:
    """Non-configurable constants for layout scheduling."""

    IMMEDIATE_TIMER = 0


def safe_ui_operation(
    log_message: str,
    default=None,
    exc: tuple[type[BaseException], ...] = (RuntimeError, AttributeError),
    log_fn=None,
):
    """Decorator to reduce repetitive UI try/except logging."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exc:
                (log_fn or logger.debug)(log_message, exc_info=True)
                return default

        return wrapper

    return decorator


@dataclass(frozen=True)
class PanelPlaceholderCalculator:
    button_size: int
    spacing: int
    baseline_items: int
    min_search_width: int
    padding: int
    min_panel_width: int

    def width(self) -> int:
        count = max(1, self.baseline_items)
        items_width = self.button_size * count
        spacing_width = self.spacing * (count - 1) if count > 1 else 0
        min_required = max(self.min_panel_width * 2, int(self.min_search_width * 0.5))
        return max(items_width + spacing_width + self.padding, min_required)

    @classmethod
    def from_mode(cls, mode: str) -> PanelPlaceholderCalculator:
        try:
            button_size = int(app_config.ui.get_top_panel_button_size())
        except (TypeError, ValueError):
            button_size = app_config.ui.get_topbar_button_size()

        try:
            spacing = int(app_config.ui.get_top_bar_buttons_spacing())
        except (TypeError, ValueError):
            spacing = int(app_config.ui.get_top_bar_buttons_spacing())

        baseline_items = {
            "favorites": max(3, app_config.ui.get_topbar_min_visible_fav() or 3),
            "recent": max(3, app_config.ui.get_topbar_min_visible_recent() or 3),
        }.get(mode, 3)

        try:
            min_search_width = int(app_config.ui.get_top_panel_search_min_width())
        except (TypeError, ValueError):
            min_search_width = app_config.ui.get_topbar_min_search_width_absolute()

        padding = app_config.ui.get_topbar_panel_padding()
        min_panel_width = app_config.ui.get_topbar_min_panel_width()
        return cls(
            button_size=button_size,
            spacing=spacing,
            baseline_items=baseline_items,
            min_search_width=min_search_width,
            padding=padding,
            min_panel_width=min_panel_width,
        )

# lupdate hint for dynamic placeholder text
if False:  # pragma: no cover
    QCoreApplication.translate("WindowUISetup", WindowStrings.SEARCH_PLACEHOLDER)


class PanelMode(str, Enum):
    QUICK = "quick"
    FAVORITES = "favorites"
    RECENT = "recent"


@dataclass(frozen=True)
class SplitterState:
    sizes: tuple[int, ...]
    stack_index: int | None


class WindowInitializerProtocol(Protocol):
    @property
    def window(self) -> QWidget: ...
    @property
    def settings(self) -> object: ...  # TODO: narrow to concrete Settings type
    @property
    def theme_ctrl(self) -> object: ...  # TODO: narrow to concrete ThemeController type


class TopPanelsControllerProtocol(Protocol):
    """Minimal protocol for top panels controller interactions."""

    def apply_snapshot(self, favorites, recents) -> bool: ...
    def request_refresh(self) -> None: ...
    data_loaded: object


def _get_top_panels_controller(window: QWidget) -> TopPanelsControllerProtocol | None:
    """Return typed top panels controller if it matches expected interface."""
    ctrl = getattr(window, "top_panels_controller", None)
    if ctrl and hasattr(ctrl, "request_refresh") and hasattr(ctrl, "apply_snapshot"):
        return ctrl  # type: ignore[return-value]
    return None


class _AutoHideTreeFilter(QObject):
    def __init__(
        self,
        window: QWidget,
        threshold_width: int,
        default_sizes: list[int],
        logger_: logging.Logger = logger,
    ):
        super().__init__(window)
        self.window = window
        self.threshold = int(threshold_width)
        self.default_sizes = (
            default_sizes[:] if isinstance(default_sizes, (list, tuple)) else [250, 750]
        )
        self._is_collapsed = False
        self._saved_state: SplitterState | None = None
        self._logger = logger_
        try:
            self._manage_topbar_panels = bool(
                app_config.ui.get_auto_hide_manage_topbar()
            )
        except (AttributeError, TypeError, ValueError):
            self._manage_topbar_panels = False

    def _save_current_state(self, splitter, stack) -> None:
        sizes: tuple[int, ...] | None = None
        stack_idx: int | None = None

        try:
            if splitter is not None:
                sizes = tuple(splitter.sizes())
        except (AttributeError, RuntimeError):
            self._logger.debug("AutoHideTree: failed to read splitter sizes", exc_info=True)

        try:
            if stack is not None:
                stack_idx = stack.currentIndex()
        except (AttributeError, RuntimeError):
            self._logger.debug("AutoHideTree: failed to read stack index", exc_info=True)

        if sizes is not None:
            self._saved_state = SplitterState(sizes=sizes, stack_index=stack_idx)

    def _collapse_splitter(self, splitter, w: int) -> None:
        if splitter is None:
            return
        try:
            splitter.setCollapsible(0, True)
            splitter.setSizes([0, max(1, w)])
        except (RuntimeError, TypeError):
            self._logger.debug("AutoHideTree: failed to collapse splitter", exc_info=True)

    def _switch_to_table_view(self, stack, table) -> None:
        try:
            switch_to_table = bool(app_config.ui.get_auto_hide_switch_to_table())
        except (AttributeError, TypeError, ValueError):
            switch_to_table = False

        if not switch_to_table or stack is None or table is None:
            return

        try:
            table_container = getattr(self.window, "table_container", None)
            for i in range(stack.count()):
                wgt = stack.widget(i)
                if wgt is table or (table_container is not None and wgt is table_container):
                    stack.setCurrentIndex(i)
                    break
        except (AttributeError, RuntimeError):
            self._logger.debug("AutoHideTree: failed to switch to table", exc_info=True)

    def _hide_topbar_panels(self) -> None:
        if not self._manage_topbar_panels:
            return
        toolbar = getattr(self.window, "top_bar_toolbar", None)
        if toolbar is not None:
            try:
                toolbar.setVisible(False)
            except (AttributeError, RuntimeError):
                self._logger.debug("AutoHideTree: failed to hide top bar toolbar", exc_info=True)
            return
        for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
            try:
                panel = getattr(self.window, attr, None)
                if panel is not None:
                    panel.setVisible(False)
            except (AttributeError, RuntimeError):
                self._logger.debug(f"AutoHideTree: failed to hide panel '{attr}'", exc_info=True)

    def _restore_splitter(self, splitter) -> None:
        if splitter is None:
            return
        try:
            if self._saved_state and len(self._saved_state.sizes) == 2:
                splitter.setSizes(list(self._saved_state.sizes))
            else:
                sizes = [int(x) for x in self.default_sizes]
                splitter.setSizes(sizes)
        except (RuntimeError, TypeError, ValueError):
            self._logger.debug("AutoHideTree: failed to restore splitter", exc_info=True)

    def _show_topbar_panels(self) -> None:
        if not self._manage_topbar_panels:
            return
        toolbar = getattr(self.window, "top_bar_toolbar", None)
        if toolbar is not None:
            try:
                toolbar.setVisible(True)
            except (AttributeError, RuntimeError):
                self._logger.debug("AutoHideTree: failed to show top bar toolbar", exc_info=True)
            return
        for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
            try:
                panel = getattr(self.window, attr, None)
                if panel is not None:
                    panel.setVisible(True)
            except (AttributeError, RuntimeError):
                self._logger.debug(f"AutoHideTree: failed to show panel '{attr}'", exc_info=True)

    def _restore_stack_index(self, stack) -> None:
        if stack is None or self._saved_state is None or self._saved_state.stack_index is None:
            return
        try:
            if 0 <= self._saved_state.stack_index < stack.count():
                stack.setCurrentIndex(self._saved_state.stack_index)
        except (RuntimeError, ValueError, TypeError, AttributeError):
            self._logger.debug("AutoHideTree: failed to restore stack index", exc_info=True)

    def _handle_narrow_window(self, splitter, stack, table, w: int) -> None:
        if not self._is_collapsed:
            self._save_current_state(splitter, stack)
            self._collapse_splitter(splitter, w)
            self._switch_to_table_view(stack, table)
            self._is_collapsed = True
        self._hide_topbar_panels()

    def _handle_wide_window(self, splitter, stack) -> None:
        self._restore_splitter(splitter)
        self._show_topbar_panels()
        self._restore_stack_index(stack)
        self._is_collapsed = False

    def _apply(self):
        splitter = getattr(self.window, "splitter", None)
        stack = getattr(self.window, "stack", None)
        table = getattr(self.window, "table", None)

        try:
            w = self.window.width()
        except (AttributeError, RuntimeError):
            return

        if w <= self.threshold:
            self._handle_narrow_window(splitter, stack, table, w)
        elif w > self.threshold and self._is_collapsed:
            self._handle_wide_window(splitter, stack)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self.window and event.type() == QEvent.Type.Resize:
            self._apply()
        return super().eventFilter(obj, event)


class _WindowSettingsFilter(QObject):
    def __init__(self, window: QWidget, logger_: logging.Logger = logger):
        super().__init__(window)
        self.window = window
        self._logger = logger_
        self._save_timer = QTimer(window)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush)

    def _store_state(self) -> None:
        try:
            splitter = getattr(self.window, "splitter", None)
            if splitter is not None:
                try:
                    sizes = splitter.sizes()
                except Exception:
                    sizes = None
                if (
                    isinstance(sizes, list)
                    and len(sizes) >= 2
                    and all(isinstance(size, int) and size > 0 for size in sizes[:2])
                ):
                    SettingsManager.set("window.splitter_left", int(sizes[0]))
                    SettingsManager.set("window.splitter_right", int(sizes[1]))

            if self.window.isMaximized():
                SettingsManager.set("window.maximized", True)
                return
            SettingsManager.set("window.maximized", False)
            size = self.window.size()
            pos = self.window.pos()
            SettingsManager.set("window.width", int(size.width()))
            SettingsManager.set("window.height", int(size.height()))
            SettingsManager.set("window.x", int(pos.x()))
            SettingsManager.set("window.y", int(pos.y()))
        except Exception:
            self._logger.debug("WindowSettings: failed to store state", exc_info=True)

    def _flush(self) -> None:
        try:
            SettingsManager.save()
        except Exception:
            self._logger.debug("WindowSettings: failed to save settings", exc_info=True)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self.window:
            if event.type() == QEvent.Type.Resize:
                self._store_state()
                self._save_timer.start(300)
            elif event.type() == QEvent.Type.Move:
                self._store_state()
                self._save_timer.start(300)
            elif event.type() == QEvent.Type.WindowStateChange:
                self._store_state()
                self._save_timer.start(300)
            elif event.type() == QEvent.Type.Close:
                self._store_state()
                self._flush()
        return super().eventFilter(obj, event)


class WindowUISetup:
    def __init__(self, window_initializer: WindowInitializerProtocol) -> None:
        self.window_initializer = window_initializer
        self.window = window_initializer.window
        self.fonts = app_config.ui.get('ui', {}).get('fonts', {})
        self.settings = window_initializer.settings
        self.theme_ctrl = window_initializer.theme_ctrl
        self.main_layout: QVBoxLayout | None = None
        self._topbar_snapshot_store = TopBarSnapshotStore()
        self._topbar_snapshot_applied = False
        self._pending_topbar_snapshot: TopBarSnapshot | None = None
        self._topbar_refresh_requested = False

        self._language_service = LanguageService.instance()
        self._connect_language_service()

    # --- Internal helpers -------------------------------------------------

    def _connect_language_service(self) -> None:
        if self._language_service is None:
            logger.warning("WindowUISetup: LanguageService not available")
            return

        try:
            self._language_service.languageChanged.connect(self._on_language_changed)
        except (TypeError, RuntimeError) as e:
            logger.error(f"WindowUISetup: failed to connect languageChanged: {e}", exc_info=True)

        if hasattr(self.window, "destroyed"):
            try:
                self.window.destroyed.connect(self._disconnect_language_service)
            except (TypeError, RuntimeError) as e:
                logger.warning(f"WindowUISetup: failed to connect cleanup: {e}", exc_info=True)

    def _get_search_placeholder_text(self) -> str:
        """Return configured placeholder, keeping translation for default text."""
        return QCoreApplication.translate(
            "WindowUISetup", WindowStrings.SEARCH_PLACEHOLDER
        )

    def _disconnect_language_service(self) -> None:
        if self._language_service is None:
            return
        try:
            self._language_service.languageChanged.disconnect(self._on_language_changed)
        except (TypeError, RuntimeError):
            pass

    def setup_basic_attributes(self) -> None:
        self.window.settings = self.window_initializer.settings
        self.window.theme_ctrl = self.window_initializer.theme_ctrl
        self.window.current_category_id = None
        self.window.thread_pool = get_task_scheduler().get_thread_pool()
        self.window.undo_stack = UndoManager(self.window)
        self.window.sphere_buttons = {}

    def setup_menu(self) -> None:
        from app.controllers.ui.menu_controller import MenuController

        self.window.menu_controller = MenuController(self.window)
        menu_bar = self.window.menu_controller.create_main_menu()
        self.window.install_menu_bar_widget(menu_bar)

    def setup_central_widget(self) -> None:
        central = QFrame(self.window)
        try:
            central.setAutoFillBackground(True)
        except (RuntimeError, AttributeError):
            logger.debug(
                "WindowUISetup: setAutoFillBackground failed on central frame",
                exc_info=True,
            )
        central.setFrameShape(QFrame.Shape.NoFrame)
        central.setLineWidth(0)
        self.window.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(*app_config.ui.get_main_layout_margins())
        self.main_layout.setSpacing(app_config.ui.get_main_layout_spacing())
        try:
            left, _, r, b = self.main_layout.getContentsMargins()
        except (RuntimeError, AttributeError):
            left, r, b = 0, 0, 0
        try:
            self.main_layout.setContentsMargins(
                int(left or 0), 0, int(r or 0), int(b or 0)
            )
        except (RuntimeError, AttributeError):
            logger.debug(
                "WindowUISetup: failed to force top margin=0 for main_layout",
                exc_info=True,
            )

    def setup_top_panel(self) -> None:
        from app.views.main_components.ui.topbar.top_bar_setup import TopBarBuilder

        TopBarBuilder(self).build()

    def _build_top_bar_widgets_with_metrics(self, top_bar: QHBoxLayout) -> None:
        """Build top bar widgets."""
        self.setup_top_bar_widgets(top_bar)

    def _create_top_bar_host(
        self, container_parent: QWidget, top_bar: QHBoxLayout
    ) -> QWidget:
        top_bar_host = QWidget(container_parent)
        top_bar_host.setObjectName("topBarHost")
        top_bar_host.setLayout(top_bar)
        try:
            top_bar_host.setFixedHeight(app_config.ui.get_top_bar_height())
            top_bar_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except (RuntimeError, TypeError, AttributeError):
            logger.warning("TopPanel: failed to set size policy", exc_info=True)
        return top_bar_host

    def _uses_toolbar_topbar(self) -> bool:
        toolbar = getattr(self.window, "top_bar_toolbar", None)
        return isinstance(toolbar, QToolBar)

    def _init_and_schedule_topbar_manager(self) -> None:
        if self._uses_toolbar_topbar():
            self.window._topbar_manager = None
            try:
                if hasattr(self.window, "shown"):
                    self.window.shown.connect(
                        partial(self._schedule_topbar_initialization, None)
                    )
                else:
                    QTimer.singleShot(
                        UIConstants.IMMEDIATE_TIMER,
                        partial(self._schedule_topbar_initialization, None),
                    )
            except Exception:
                logger.debug(
                    "TopPanel: failed to schedule toolbar initialization",
                    exc_info=True,
                )
            return
        try:
            self.window._topbar_manager = TopBarLayoutManager(self.window)
            self._register_topbar_cleanup(self.window._topbar_manager)
        except (RuntimeError, TypeError):
            self.window._topbar_manager = None
            logger.exception("TopPanel: failed to initialize TopBarLayoutManager")
            return
        mgr = getattr(self.window, "_topbar_manager", None)
        if not mgr:
            return
        try:
            if hasattr(self.window, "shown"):
                self.window.shown.connect(
                    partial(self._schedule_topbar_initialization, mgr)
                )
            else:
                QTimer.singleShot(UIConstants.IMMEDIATE_TIMER, partial(self._schedule_topbar_initialization, mgr))
        except Exception:
            logger.debug(
                "TopPanel: failed to schedule topbar initialization", exc_info=True
            )

    def _apply_snapshot_to_widgets(self, snapshot: TopBarSnapshot) -> bool:
        """Apply snapshot directly to top-bar widgets or via controller."""
        controller = _get_top_panels_controller(self.window)
        if controller is not None:
            try:
                return bool(controller.apply_snapshot(snapshot.favorites, snapshot.recents))
            except Exception:
                logger.debug(
                    "WindowUISetup: failed to apply top bar snapshot via controller",
                    exc_info=True,
                )

        applied = False

        fav_widget = getattr(self.window, "fav_widget", None)
        if fav_widget is not None and callable(getattr(fav_widget, "set_data", None)):
            try:
                fav_widget.set_data(snapshot.favorites, fast_icons=True)  # type: ignore[call-arg]
                applied = applied or bool(snapshot.favorites)
            except TypeError:
                try:
                    fav_widget.set_data(snapshot.favorites)  # type: ignore[call-arg]
                    applied = applied or bool(snapshot.favorites)
                except Exception:
                    logger.debug(
                        "WindowUISetup: failed to apply favorites snapshot directly",
                        exc_info=True,
                    )
            except Exception:
                logger.debug(
                    "WindowUISetup: failed to apply favorites snapshot directly",
                    exc_info=True,
                )

        recent_widget = getattr(self.window, "recent_links_widget", None)
        if recent_widget is not None and callable(getattr(recent_widget, "set_data", None)):
            try:
                recent_widget.set_data(snapshot.recents, fast_icons=True)  # type: ignore[call-arg]
                applied = applied or bool(snapshot.recents)
            except TypeError:
                try:
                    recent_widget.set_data(snapshot.recents)  # type: ignore[call-arg]
                    applied = applied or bool(snapshot.recents)
                except Exception:
                    logger.debug(
                        "WindowUISetup: failed to apply recents snapshot directly",
                        exc_info=True,
                    )
            except Exception:
                logger.debug(
                    "WindowUISetup: failed to apply recents snapshot directly",
                    exc_info=True,
                )

        return applied

    def _prefill_topbar_from_snapshot(
        self, controller
    ) -> tuple[bool, TopBarSnapshot | None]:
        """Load and apply cached top bar snapshot if available."""
        store = getattr(self, "_topbar_snapshot_store", None)
        if store is None:
            return False, None
        try:
            snapshot = store.load()
        except Exception:
            logger.debug(
                "WindowUISetup: failed to load top bar snapshot",
                exc_info=True,
            )
            return False, None
        if snapshot is None:
            return False, None

        if getattr(self, "_topbar_snapshot_applied", False):
            return True, snapshot

        applied = self._apply_snapshot_to_widgets(snapshot)
        if controller is None and applied:
            self._pending_topbar_snapshot = snapshot
            self.window._pending_topbar_snapshot = snapshot
        if applied:
            self._topbar_snapshot_applied = True
        return applied, snapshot

    def _schedule_topbar_initialization(
        self, mgr: TopBarLayoutManager | None
    ) -> None:
        if getattr(self.window, "_topbar_initialized", False):
            return
        self.window._topbar_initialized = True
        QTimer.singleShot(UIConstants.IMMEDIATE_TIMER, partial(self._finalize_topbar_startup, mgr))

    def _prepare_initial_topbar_layout(self, mgr: TopBarLayoutManager | None) -> None:
        """Initialize static topbar layout before data arrives."""
        if mgr is None:
            return
        try:
            mgr.prepare_initial_layout()
        except (RuntimeError, AttributeError):
            logger.debug("TopPanel: prepare_initial_layout failed", exc_info=True)
        except Exception:
            logger.debug("TopPanel: initial layout setup failed", exc_info=True)

    def _load_and_apply_snapshot(
        self, controller
    ) -> tuple[bool, TopBarSnapshot | None]:
        """Load cached snapshot and apply it via controller or widgets."""
        return self._prefill_topbar_from_snapshot(controller)

    def _connect_topbar_data_signal(
        self, controller, mgr: TopBarLayoutManager | None
    ) -> None:
        """Wire controller data-loaded signal to layout manager readiness."""
        if mgr is None:
            return
        if controller and hasattr(controller, "data_loaded"):
            try:
                from PyQt6.QtCore import Qt

                controller.data_loaded.connect(
                    mgr.mark_data_ready, Qt.ConnectionType.SingleShotConnection
                )
                logger.debug("TopPanel: connected to data_loaded signal")
            except Exception as e:
                logger.warning(f"TopPanel: failed to connect data_loaded: {e}")

    def _trigger_topbar_refresh(self, controller, delay_ms: int | None = None) -> None:
        """Trigger async refresh of controller-managed panels."""
        if controller:
            self._request_topbar_refresh_once(controller, delay_ms)

    def _log_snapshot_info(
        self, snapshot_loaded: bool, snapshot: TopBarSnapshot | None
    ) -> None:
        """Log snapshot application details for diagnostics."""
        if not snapshot_loaded or snapshot is None:
            return
        try:
            logger.debug(
                "TopPanel: warm snapshot applied (favorites=%s, recents=%s, saved_at=%s)",
                len(snapshot.favorites),
                len(snapshot.recents),
                snapshot.saved_at.isoformat(),
            )
        except Exception:
            logger.debug(
                "TopPanel: warm snapshot applied (favorites=%s, recents=%s)",
                len(snapshot.favorites),
                len(snapshot.recents),
            )

    def _finalize_topbar_startup(self, mgr: TopBarLayoutManager | None) -> None:
        self._prepare_initial_topbar_layout(mgr)

        controller = _get_top_panels_controller(self.window)

        snapshot_loaded, snapshot = self._load_and_apply_snapshot(controller)
        self._connect_topbar_data_signal(controller, mgr)
        refresh_delay = 0
        self._trigger_topbar_refresh(controller, delay_ms=refresh_delay)

        if mgr is not None:
            try:
                mgr.mark_data_ready()
            except Exception:
                logger.debug("TopPanel: immediate mark_data_ready failed", exc_info=True)

        self._log_snapshot_info(snapshot_loaded, snapshot)

    @safe_ui_operation("TopPanel: request_refresh failed", exc=(Exception,), log_fn=logger.warning)
    def _safe_request_refresh(self, controller, delay_ms: int | None = None) -> None:
        controller.request_refresh(delay_ms)

    def _request_topbar_refresh_once(
        self, controller, delay_ms: int | None = None
    ) -> None:
        if self._topbar_refresh_requested:
            return
        if not hasattr(controller, "request_refresh"):
            return
        self._topbar_refresh_requested = True
        QTimer.singleShot(
            UIConstants.IMMEDIATE_TIMER if delay_ms is None else int(delay_ms),
            lambda: self._safe_request_refresh(controller, delay_ms),
        )

    def _schedule_top_panels_refresh(self) -> None:
        controller = _get_top_panels_controller(self.window)
        if not controller:
            return
        self._request_topbar_refresh_once(controller)

    def _on_language_changed(self, _lang_code: str) -> None:
        try:
            search = getattr(self.window, "search", None)
            if search is not None and hasattr(search, "setPlaceholderText"):
                search.setPlaceholderText(self._get_search_placeholder_text())
        except Exception:
            logger.debug("WindowUISetup: failed to update search placeholder", exc_info=True)

        try:
            retranslate_cb = getattr(self.window, "_retranslate_status_bar", None)
            if callable(retranslate_cb):
                retranslate_cb()
        except Exception:
            logger.exception("WindowUISetup: failed to retranslate status bar")

        try:
            topbar_manager = getattr(self.window, "_topbar_manager", None)
            if topbar_manager and hasattr(topbar_manager, "retranslate_topbar"):
                topbar_manager.retranslate_topbar()
        except Exception:
            logger.debug("WindowUISetup: failed to retranslate top bar", exc_info=True)

    def _register_topbar_cleanup(self, manager: TopBarLayoutManager | None) -> None:
        if manager is None or not hasattr(self.window, "destroyed"):
            return
        if getattr(self.window, "_topbar_cleanup_connected", False):
            return
        try:
            self.window.destroyed.connect(lambda: manager.cleanup())
            self.window._topbar_cleanup_connected = True
            logger.debug("WindowUISetup: cleanup connected to window.destroyed")
        except Exception:
            logger.warning(
                "WindowUISetup: failed to connect top bar cleanup", exc_info=True
            )

    def _create_widget_by_mode(self, mode: PanelMode | str) -> QWidget:
        mode_enum = PanelMode(mode) if isinstance(mode, str) else mode

        if mode_enum == PanelMode.QUICK:
            return QuickAddPanelWidget(self.window, category_provider=self.window)
        elif mode_enum == PanelMode.FAVORITES:
            return FavoritesPanelWidget(self.window)
        elif mode_enum == PanelMode.RECENT:
            return RecentPanelWidget(self.window)
        else:
            raise ValueError(f"Unknown panel mode: {mode_enum}")

    def _get_panel_height(self) -> int:
        try:
            search_h = int(app_config.ui.get_top_panel_search_height())
        except (TypeError, ValueError):
            search_h = app_config.ui.get_top_panel_search_height()
        try:
            btn_h = int(app_config.ui.get_top_panel_button_size())
        except (TypeError, ValueError):
            btn_h = app_config.ui.get_topbar_button_size()
        return max(search_h, btn_h)

    def _compute_panel_placeholder_width(self, mode: str) -> int:
        """Estimate placeholder width for data-driven panels."""
        if mode == "quick":
            # Quick panel has static content immediately; no placeholder needed.
            return 0

        calculator = PanelPlaceholderCalculator.from_mode(mode)
        return calculator.width()

    def _configure_panel_widget(
        self,
        widget,
        object_name: str | None,
        log_label: str,
        mode: str,
    ) -> None:
        if object_name:
            widget.setObjectName(object_name)
        widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        fixed_h = self._get_panel_height()
        try:
            widget.setFixedHeight(fixed_h)
        except Exception:
            logger.debug(f"TopPanel: failed to set height on {log_label}", exc_info=True)

        placeholder_width = self._compute_panel_placeholder_width(mode)
        if placeholder_width > 0:
            try:
                widget._placeholder_min_width = placeholder_width
                widget.setMinimumWidth(placeholder_width)
            except Exception:
                logger.debug(
                    f"TopPanel: failed to configure placeholder width on {log_label}",
                    exc_info=True,
                )

    @safe_ui_operation("TopPanel: failed to adjust spacing", exc=(Exception,))
    def _adjust_panel_spacing(self, widget, log_label: str) -> None:
        lay = getattr(widget, "panel_layout", None)
        if lay is not None and hasattr(lay, "spacing") and hasattr(lay, "setSpacing"):
            cur = int(lay.spacing())
            # Slightly tighten spacing for a denser look
            adjust = app_config.ui.get_topbar_panel_spacing_adjustment()
            lay.setSpacing(max(0, cur + adjust))

    def _create_top_panel_widget(
        self,
        top_bar: QHBoxLayout,
        mode: str,
        attr_name: str,
        object_name: str | None,
        log_label: str,
    ) -> None:
        try:
            widget = self._create_widget_by_mode(mode)
            self._configure_panel_widget(widget, object_name, log_label, mode)
            setattr(self.window, attr_name, widget)
            top_bar.addWidget(widget)
            self._adjust_panel_spacing(widget, log_label)
        except Exception:
            setattr(self.window, attr_name, None)
            logger.exception(f"TopPanel: failed to create {log_label} widget")

    def setup_top_bar_widgets(self, top_bar: QHBoxLayout) -> None:
        widgets_params = [
            ("quick", "quick_add_widget", None, "QuickAdd"),
            ("favorites", "fav_widget", "favoritesWidget", "Favorites"),
            ("recent", "recent_links_widget", "recentLinksWidget", "Recent"),
        ]
        for idx, (mode, attr_name, obj_name, label) in enumerate(widgets_params):
            self._create_top_panel_widget(top_bar, mode, attr_name, obj_name, label)
            
            if idx < len(widgets_params) - 1:
                try:
                    top_bar.addSpacing(app_config.ui.get_topbar_separator_spacing())
                    top_bar.addWidget(self._create_vertical_separator())
                    top_bar.addSpacing(app_config.ui.get_topbar_separator_spacing())
                except Exception:
                    logger.debug("TopPanel: failed to insert separator", exc_info=True)

        try:
            top_bar.addSpacing(app_config.ui.get_topbar_separator_spacing())
            top_bar.addWidget(self._create_vertical_separator())
            top_bar.addSpacing(app_config.ui.get_topbar_separator_spacing())
        except Exception:
            logger.debug("TopPanel: failed to insert separator before search", exc_info=True)

        self.setup_search_widget(top_bar)

    @safe_ui_operation("TopPanel: failed to create vertical separator", exc=(Exception,))
    def _create_vertical_separator(self) -> QWidget:
        sep = QWidget(self.window)
        sep.setObjectName("vSeparator")
        sep.setProperty("class", "vertical_separator")
        w = int(app_config.ui.get_separator_width())
        sep.setFixedWidth(max(1, w))
        try:
            h = int(app_config.ui.get_top_bar_height())
            sep.setFixedHeight(max(1, h))
            sep.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        except Exception:
            sep.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        return sep

    def setup_search_widget(self, top_bar: QHBoxLayout) -> None:
        placeholder = QWidget(self.window)
        placeholder.setObjectName("mainSearchPlaceholder")
        placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        try:
            min_search_w = int(app_config.ui.get_top_panel_search_min_width())
        except (TypeError, ValueError):
            min_search_w = app_config.ui.get_topbar_min_search_width_absolute()
            logger.warning("SearchWidget: invalid min width, using fallback")
        try:
            placeholder.setMinimumWidth(min_search_w)
        except Exception:
            logger.debug("SearchWidget: failed to set placeholder min width", exc_info=True)
        try:
            placeholder.setFixedHeight(int(app_config.ui.get_top_panel_button_size()))
        except (TypeError, ValueError, RuntimeError):
            fallback_h = app_config.ui.get_top_panel_button_size()
            placeholder.setFixedHeight(int(fallback_h))
            logger.warning("SearchWidget: invalid height, using fallback")

        self.window.search = None
        top_bar.addWidget(placeholder)
        self._schedule_search_widget_materialization(top_bar, placeholder)

    def _schedule_search_widget_materialization(
        self, top_bar: QHBoxLayout, placeholder: QWidget
    ) -> None:
        def _apply() -> None:
            self._materialize_search_widget(top_bar, placeholder)

        try:
            is_visible = bool(getattr(self.window, "isVisible", lambda: False)())
        except Exception:
            is_visible = False

        try:
            if is_visible:
                QTimer.singleShot(UIConstants.IMMEDIATE_TIMER, _apply)
            elif hasattr(self.window, "shown"):
                self.window.shown.connect(_apply)
            else:
                QTimer.singleShot(UIConstants.IMMEDIATE_TIMER, _apply)
        except Exception:
            logger.debug(
                "SearchWidget: failed to schedule materialization",
                exc_info=True,
            )

    def _materialize_search_widget(
        self, top_bar: QHBoxLayout, placeholder: QWidget
    ) -> None:
        if getattr(self.window, "search", None) is not None:
            return

        search = QLineEdit(self.window)
        search.setPlaceholderText(self._get_search_placeholder_text())
        WidgetRegistry.register(WidgetType.SEARCH_FIELD, search)
        try:
            search.setFixedHeight(int(app_config.ui.get_top_panel_button_size()))
        except (TypeError, ValueError, RuntimeError):
            fallback_h = app_config.ui.get_top_panel_button_size()
            search.setFixedHeight(int(fallback_h))
            logger.warning("SearchWidget: invalid height, using fallback")
        search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        try:
            min_search_w = int(app_config.ui.get_top_panel_search_min_width())
        except (TypeError, ValueError):
            min_search_w = app_config.ui.get_topbar_min_search_width_absolute()
            logger.warning("SearchWidget: invalid min width, using fallback")
        try:
            search.setMinimumWidth(min_search_w)
        except Exception:
            logger.debug("SearchWidget: failed to set min width", exc_info=True)
        search.setObjectName("mainSearch")

        handler = getattr(self.window, "on_search", None)
        if callable(handler):
            try:
                search.textChanged.connect(handler)
            except (TypeError, RuntimeError):
                logger.warning("SearchWidget: failed to connect handler", exc_info=True)
        else:
            logger.warning("SearchWidget: on_search handler not found")

        index = top_bar.indexOf(placeholder)
        if index < 0:
            logger.debug("SearchWidget: placeholder missing during materialization")
            return

        top_bar.removeWidget(placeholder)
        placeholder.setParent(None)
        placeholder.deleteLater()
        top_bar.insertWidget(index, search)
        self.window.search = search
        self._schedule_search_widget_enhancements(search)
        self._normalize_top_bar_stretches(top_bar)

        try:
            topbar_manager = getattr(self.window, "_topbar_manager", None)
            if topbar_manager is not None and hasattr(topbar_manager, "adjust"):
                topbar_manager.adjust()
        except Exception:
            logger.debug("SearchWidget: topbar adjust after materialization failed", exc_info=True)

    def _schedule_search_widget_enhancements(self, search_widget: QLineEdit) -> None:
        """Defer cosmetic search-widget setup to keep topbar startup lighter."""

        def _apply() -> None:
            try:
                search_widget.setClearButtonEnabled(True)
            except Exception:
                logger.debug("SearchWidget: failed to enable clear button", exc_info=True)
            try:
                self._setup_search_context_menu(search_widget)
            except Exception:
                logger.debug("SearchWidget: deferred context menu setup failed", exc_info=True)

        try:
            is_visible = bool(getattr(self.window, "isVisible", lambda: False)())
        except Exception:
            is_visible = False

        try:
            if is_visible:
                QTimer.singleShot(UIConstants.IMMEDIATE_TIMER, _apply)
            elif hasattr(self.window, "shown"):
                self.window.shown.connect(_apply)
            else:
                QTimer.singleShot(UIConstants.IMMEDIATE_TIMER, _apply)
        except Exception:
            logger.debug(
                "SearchWidget: failed to schedule deferred enhancements",
                exc_info=True,
            )

    @safe_ui_operation("SearchWidget: failed to setup context menu", exc=(Exception,))
    def _setup_search_context_menu(self, search_widget: QLineEdit) -> None:
        """Setup custom context menu for search widget."""

        search_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        search_widget.customContextMenuRequested.connect(
            lambda pos: self._show_search_context_menu(search_widget, pos)
        )
    
    @safe_ui_operation("SearchWidget: failed to show context menu", exc=(Exception,))
    def _show_search_context_menu(self, widget: QLineEdit, pos) -> None:
        """Show custom context menu for search widget."""
        from app.views.windows.dialogs.base_dialog import create_context_menu

        menu = create_context_menu(widget)
        menu.popup(widget.mapToGlobal(pos))

    @safe_ui_operation("TopPanel: _normalize_top_bar_stretches failed", exc=(Exception,))
    def _normalize_top_bar_stretches(self, top_bar: QHBoxLayout) -> None:
        """Ensure search widget gets stretch while others stay fixed."""
        count = top_bar.count()
        search_widget = getattr(self.window, "search", None)

        for i in range(count):
            it = top_bar.itemAt(i)
            if it is None:
                continue

            w = it.widget()
            stretch = 1 if w is search_widget else 0
            try:
                top_bar.setStretch(i, stretch)
            except Exception:
                logger.debug(f"TopPanel: setStretch({stretch}) at {i} failed", exc_info=True)

    def setup_main_content(self) -> None:
        total_start = perf_counter()
        top_separator_ms = 0.0
        mid_layout_ms = 0.0
        left_panel_ms = 0.0
        right_panel_shell_ms = 0.0
        bottom_separator_ms = 0.0

        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )

        top_sep_start = perf_counter()
        h_line_top = QWidget(container_parent)
        h_line_top.setProperty("class", "separator")
        try:
            sep_h = int(app_config.ui.get_separator_height())
            h_line_top.setFixedHeight(max(1, sep_h))
            h_line_top.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        except Exception:
            logger.debug("MainContent: failed to size top separator", exc_info=True)
        if self.main_layout is not None:
            self.main_layout.addWidget(h_line_top)
        top_separator_ms = (perf_counter() - top_sep_start) * 1000.0

        mid_start = perf_counter()
        mid = QHBoxLayout()
        mid.setContentsMargins(*app_config.ui.get_layout_margins("mid"))
        mid.setSpacing(app_config.ui.get_main_layout_spacing())
        mid_layout_ms = (perf_counter() - mid_start) * 1000.0

        left_start = perf_counter()
        self.setup_left_panel(mid)
        left_panel_ms = (perf_counter() - left_start) * 1000.0

        right_start = perf_counter()
        self.setup_right_panel(mid)
        right_panel_shell_ms = (perf_counter() - right_start) * 1000.0
        if self.main_layout is not None:
            self.main_layout.addLayout(mid)

        bottom_sep_start = perf_counter()
        h_line_2 = QWidget(container_parent)
        h_line_2.setProperty("class", "separator")
        try:
            sep_h = int(app_config.ui.get_separator_height())
            h_line_2.setFixedHeight(max(1, sep_h))
            h_line_2.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        except Exception:
            logger.debug("MainContent: failed to size middle separator", exc_info=True)
        if self.main_layout is not None:
            self.main_layout.addWidget(h_line_2)
        bottom_separator_ms = (perf_counter() - bottom_sep_start) * 1000.0

        logger.info(
            "[Perf] MainContent setup: total=%.2f ms top_separator=%.2f ms "
            "mid_layout=%.2f ms left_panel=%.2f ms right_panel_shell=%.2f ms "
            "bottom_separator=%.2f ms",
            (perf_counter() - total_start) * 1000.0,
            top_separator_ms,
            mid_layout_ms,
            left_panel_ms,
            right_panel_shell_ms,
            bottom_separator_ms,
        )

    def finalize_main_content(self) -> None:
        """Finalize heavy main-content widgets after the shell already exists."""
        total_start = perf_counter()
        self.finalize_right_panel()
        logger.info(
            "[Perf] MainContent finalize: total=%.2f ms",
            (perf_counter() - total_start) * 1000.0,
        )

    def setup_left_panel(self, mid: QHBoxLayout) -> None:
        left_panel = QWidget(self.window)
        self.window.left_panel = left_panel
        left_panel.setObjectName("LeftPanel")
        left_panel.setAutoFillBackground(True)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(*app_config.ui.get_layout_margins("left"))
        left_layout.setSpacing(0)

        self.window.tree = StructureTreeView()
        self.window.tree.setParent(left_panel)
        self.window.tree.setHeaderHidden(True)
        self.window.tree_model = StructureTreeModel(self.window.tree)
        self.window.tree.setModel(self.window.tree_model)

        tree_icon_size = app_config.ui.get_tree_icon_size()
        row_h = app_config.ui.get_row_height()
        base_icon = int(tree_icon_size[0])
        eff_icon = max(0, min(base_icon, max(0, int(row_h) - 8)))
        self.window.tree.setIconSize(QSize(eff_icon, eff_icon))

        WidgetRegistry.register(WidgetType.STRUCTURE_TREE, self.window.tree)
        left_layout.addWidget(self.window.tree)

        self.setup_spheres_bar(left_layout)

    def setup_spheres_bar(self, left_layout: QVBoxLayout) -> None:
        self.window.spheres_bar = QWidget(self.window)
        self.window.spheres_bar.setObjectName("spheres_bar")
        self.window.spheres_bar.setFixedHeight(app_config.ui.get_spheres_bar_height())

        s_layout = QHBoxLayout(self.window.spheres_bar)
        s_layout.setContentsMargins(*app_config.ui.get_spheres_bar_margins())
        s_layout.setSpacing(app_config.ui.get_spheres_bar_spacing())
        self.window.sphere_group = QButtonGroup(self.window)

        left_layout.addWidget(self.window.spheres_bar)

    def setup_right_panel(self, mid: QHBoxLayout) -> None:
        from app.views.main_components.ui.right_panel_setup import RightPanelBuilder

        self._right_panel_builder = RightPanelBuilder(self)
        self._right_panel_builder.build_shell(mid)

    def finalize_right_panel(self) -> None:
        builder = getattr(self, "_right_panel_builder", None)
        if builder is None:
            logger.debug("RightPanel: builder missing during finalize")
            return
        builder.finalize_content()

    def _prefill_topbar_widgets_before_manager(self) -> None:
        """Apply snapshot at widget build stage before manager adjusts layout."""
        if getattr(self, "_topbar_snapshot_applied", False):
            return
        store = getattr(self, "_topbar_snapshot_store", None)
        if store is None:
            return
        try:
            snapshot = store.load()
        except Exception:
            logger.debug(
                "WindowUISetup: early snapshot load failed",
                exc_info=True,
            )
            return
        if snapshot is None:
            return

        applied = self._apply_snapshot_to_widgets(snapshot)
        if applied:
            self._topbar_snapshot_applied = True
            self.window._pending_topbar_snapshot = snapshot
            try:
                logger.debug(
                    "WindowUISetup: top bar prefilled before manager "
                    "(favorites=%s, recents=%s)",
                    len(snapshot.favorites),
                    len(snapshot.recents),
                )
            except Exception:
                pass

    def _setup_auto_hide_tree_filter(self, splitter_sizes: list[int]) -> None:
        try:
            min_w = int(app_config.ui.get_window_min_width())
        except (TypeError, ValueError):
            min_w = app_config.ui.get_window_min_width()
            logger.warning("RightPanel: invalid min width, using 280")

        try:
            self.window._auto_hide_tree_filter = _AutoHideTreeFilter(
                self.window, threshold_width=min_w, default_sizes=splitter_sizes
            )
            self.window.installEventFilter(self.window._auto_hide_tree_filter)
            try:
                if hasattr(self.window, "shown"):
                    self.window.shown.connect(self.window._auto_hide_tree_filter._apply)
                else:
                    QTimer.singleShot(UIConstants.IMMEDIATE_TIMER, self.window._auto_hide_tree_filter._apply)
            except (RuntimeError, AttributeError):
                logger.exception("RightPanel: failed to schedule AutoHideTree")
        except (RuntimeError, TypeError, AttributeError):
            logger.exception("RightPanel: failed to initialize AutoHideTree")

    def setup_bottom_panel(self) -> None:
        from app.views.main_components.ui.bottom_panel_setup import BottomPanelBuilder

        BottomPanelBuilder(self).build()

    def setup_status_bar(self) -> None:
        init_status_bar(self.window)

    def setup_window_properties(self) -> None:
        """Apply window title, geometry, settings filter and icon.

        The method orchestrates small helpers to keep complexity low.
        """
        total_start = perf_counter()

        title_start = perf_counter()
        self._apply_window_title()
        title_ms = (perf_counter() - title_start) * 1000.0

        state_start = perf_counter()
        saved = self._read_saved_window_state()
        width, height = self._compute_window_size(saved)
        state_ms = (perf_counter() - state_start) * 1000.0

        geometry_start = perf_counter()
        self.window.resize(width, height)
        self._apply_minimum_size()
        self._restore_window_state(saved)
        geometry_ms = (perf_counter() - geometry_start) * 1000.0

        filter_start = perf_counter()
        self._ensure_settings_filter()
        filter_ms = (perf_counter() - filter_start) * 1000.0

        icon_start = perf_counter()
        self._schedule_window_icon_apply()
        icon_ms = (perf_counter() - icon_start) * 1000.0

        logger.info(
            "[Perf] Window props setup: total=%.2f ms title=%.2f ms "
            "state_read=%.2f ms geometry=%.2f ms settings_filter=%.2f ms "
            "icon=%.2f ms",
            (perf_counter() - total_start) * 1000.0,
            title_ms,
            state_ms,
            geometry_ms,
            filter_ms,
            icon_ms,
        )

    # --- Helpers to reduce complexity of setup_window_properties() ---
    def _apply_window_title(self) -> None:
        """Set translated window title from configuration."""
        title = app_config.ui.get_main_window_title() or WindowStrings.WINDOW_TITLE
        self.window.setWindowTitle(QCoreApplication.translate("MainWindow", title))

    def _read_saved_window_state(self) -> dict:
        """Read persisted window state from SettingsManager."""
        return {
            "saved_maximized": bool(SettingsManager.get("window.maximized", False)),
            "saved_width": SettingsManager.get("window.width"),
            "saved_height": SettingsManager.get("window.height"),
            "saved_x": SettingsManager.get("window.x"),
            "saved_y": SettingsManager.get("window.y"),
        }

    def _compute_window_size(self, saved: dict) -> tuple[int, int]:
        """Compute initial window size from config and saved values."""
        width, height = app_config.ui.get_main_window_size()
        try:
            width = (
                int(saved["saved_width"]) if (saved["saved_width"] is not None and not saved["saved_maximized"]) else int(width)
            )
        except (TypeError, ValueError):
            width = app_config.ui.get_window_width() or AppConstants.DEFAULT_WINDOW_WIDTH
        try:
            height = (
                int(saved["saved_height"]) if (saved["saved_height"] is not None and not saved["saved_maximized"]) else int(height)
            )
        except (TypeError, ValueError):
            height = app_config.ui.get_window_height() or AppConstants.DEFAULT_WINDOW_HEIGHT
        return int(width), int(height)

    def _apply_minimum_size(self) -> None:
        """Apply minimum window size with fallbacks and logging."""
        try:
            min_w = int(app_config.ui.get_window_min_width() or AppConstants.DEFAULT_WINDOW_MIN_WIDTH)
            min_h = int(app_config.ui.get_window_min_height() or AppConstants.DEFAULT_WINDOW_MIN_HEIGHT)
            self.window.setMinimumSize(min_w, min_h)
        except (TypeError, ValueError):
            logger.warning("WindowProps: failed to set minimum size", exc_info=True)

    def _restore_position(self, saved: dict) -> None:
        """Restore window position if available and not maximized."""
        if not saved["saved_maximized"] and saved["saved_x"] is not None and saved["saved_y"] is not None:
            try:
                self.window.move(int(saved["saved_x"]), int(saved["saved_y"]))
            except (TypeError, ValueError):
                logger.debug("WindowProps: failed to restore position", exc_info=True)

    def _restore_maximized_state(self, saved: dict) -> None:
        """Restore maximized state when previously saved."""
        if saved["saved_maximized"]:
            try:
                self.window.setWindowState(self.window.windowState() | Qt.WindowState.WindowMaximized)
            except Exception:
                logger.debug("WindowProps: failed to restore maximized state", exc_info=True)

    def _finalize_window_state_restore(self, saved: dict) -> None:
        """Restore persisted position/maximized state immediately."""
        if getattr(self.window, "_window_state_restored", False):
            return
        self.window._window_state_restored = True
        self._restore_position(saved)
        self._restore_maximized_state(saved)

    def _restore_window_state(self, saved: dict) -> None:
        """Apply persisted window state before the first show to avoid resize jumps."""
        self.window._window_state_restored = False
        self._finalize_window_state_restore(saved)

    def _ensure_settings_filter(self) -> None:
        """Install settings event filter once per window lifetime."""
        if not hasattr(self.window, "_settings_filter"):
            self.window._settings_filter = _WindowSettingsFilter(self.window)
            self.window.installEventFilter(self.window._settings_filter)

    def _find_logo_path(self) -> tuple[str | None, list[str]]:
        """Pick first existing logo path among resource and filesystem candidates."""
        candidates = self._get_logo_search_paths()

        def _candidate_exists(candidate: str) -> bool:
            if candidate.startswith(("appres:", ":/")):
                return QFile.exists(candidate)
            try:
                return Path(candidate).exists()
            except (OSError, ValueError):
                return False

        logo_path = next((c for c in candidates if _candidate_exists(c)), None)
        return logo_path, candidates

    def _apply_window_icon(self) -> None:
        """Apply window icon from resolved logo path or log a warning."""
        logo_path, candidates = self._find_logo_path()
        if logo_path:
            self.window.setWindowIcon(create_icon_from_path(logo_path))
        else:
            logger.warning(f"Logo icon not found in: {candidates}")

    def _schedule_window_icon_apply(self) -> None:
        """Apply the window icon after the first event-loop turn.

        The icon is non-critical for first paint. Deferring it removes a
        synchronous disk-read from startup when the logo comes from the
        filesystem rather than Qt resources.
        """
        try:
            QTimer.singleShot(UIConstants.IMMEDIATE_TIMER, self._apply_window_icon)
        except Exception:
            logger.debug(
                "WindowProps: failed to defer window icon apply; falling back to sync",
                exc_info=True,
            )
            self._apply_window_icon()

    def _get_logo_search_paths(self) -> list[str]:
        """Return ordered list of logo search paths (resources, disk, bundled)."""
        paths: list[str | Path] = [
            "appres:logo/logo.png",
            PathManager.get_resource_path(Path("logo") / "logo.png"),
            PathManager.app_root() / "logo" / "logo.png",
        ]

        return [
            PathManager.as_str(p) if isinstance(p, Path) else p for p in paths
        ]

    # --- Helpers to reduce complexity of cleanup() ---
    def _cleanup_settings_filter(self) -> None:
        """Detach and delete settings event filter if present."""
        if not hasattr(self.window, "_settings_filter"):
            return
        try:
            filter_obj = self.window._settings_filter
            if filter_obj is not None:
                try:
                    self.window.removeEventFilter(filter_obj)
                except (RuntimeError, AttributeError):
                    pass
                try:
                    filter_obj.deleteLater()
                except (RuntimeError, AttributeError):
                    pass
            self.window._settings_filter = None
        except (RuntimeError, AttributeError) as cleanup_error:
            logger.warning(
                "WindowUISetup: error cleaning up settings filter: %s",
                cleanup_error,
            )

    def _cleanup_auto_hide_filter(self) -> None:
        """Detach and delete auto-hide tree filter if present."""
        if not hasattr(self.window, "_auto_hide_tree_filter"):
            return
        try:
            filter_obj = self.window._auto_hide_tree_filter
            if filter_obj is not None:
                if hasattr(self.window, "shown"):
                    try:
                        self.window.shown.disconnect(filter_obj._apply)
                    except (TypeError, RuntimeError):
                        pass
                try:
                    self.window.removeEventFilter(filter_obj)
                except (RuntimeError, AttributeError):
                    pass
                try:
                    filter_obj.deleteLater()
                except (RuntimeError, AttributeError):
                    pass
                self.window._auto_hide_tree_filter = None
                logger.debug("WindowUISetup: cleaned up _auto_hide_tree_filter")
        except (RuntimeError, AttributeError) as cleanup_error:
            logger.warning(f"WindowUISetup: error cleaning up filter: {cleanup_error}")

    def cleanup(self) -> None:
        logger.debug("WindowUISetup: starting cleanup")
        self._disconnect_language_service()
        self._cleanup_settings_filter()
        self._cleanup_auto_hide_filter()
        logger.info("WindowUISetup: cleanup completed")
