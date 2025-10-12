from __future__ import annotations

import logging
import sys
import time
from functools import partial
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QEvent, QObject, QSize, QTimer
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.controllers.ui.undo.stack import UndoManager
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

# Mark strings for translation extraction
_SEARCH_PLACEHOLDER = QT_TRANSLATE_NOOP("WindowUISetup", "Search\u2026 (Ctrl+F)")


class _AutoHideTreeFilter(QObject):
    def __init__(
        self,
        window,
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
        self._saved_splitter_sizes = None
        self._prev_stack_index = None
        self._logger = logger_
        try:
            self._manage_topbar_panels = bool(
                app_config.ui.get_auto_hide_manage_topbar()
            )
        except (AttributeError, TypeError, ValueError):
            self._manage_topbar_panels = False

    def _save_current_state(self, splitter, stack) -> None:
        """Save current splitter sizes and stack index before collapsing."""
        try:
            if splitter is not None:
                self._saved_splitter_sizes = splitter.sizes()
        except (AttributeError, RuntimeError):
            self._saved_splitter_sizes = None
            self._logger.debug(
                "AutoHideTree: failed to read splitter sizes", exc_info=True
            )
        try:
            if stack is not None:
                self._prev_stack_index = stack.currentIndex()
        except (AttributeError, RuntimeError):
            self._prev_stack_index = None
            self._logger.debug(
                "AutoHideTree: failed to read current stack index",
                exc_info=True,
            )

    def _collapse_splitter(self, splitter, w: int) -> None:
        """Collapse left panel in splitter."""
        if splitter is None:
            return
        try:
            splitter.setCollapsible(0, True)
            splitter.setSizes([0, max(1, w)])
        except (RuntimeError, TypeError):
            self._logger.debug(
                "AutoHideTree: failed to collapse left panel on narrow window",
                exc_info=True,
            )

    def _switch_to_table_view(self, stack, table) -> None:
        """Switch stack to table view if configured."""
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
                if wgt is table or (
                    table_container is not None and wgt is table_container
                ):
                    stack.setCurrentIndex(i)
                    break
        except (AttributeError, RuntimeError):
            self._logger.debug(
                "AutoHideTree: failed to switch stack to table",
                exc_info=True,
            )

    def _hide_topbar_panels(self) -> None:
        """Hide top bar panels when window is narrow."""
        if not self._manage_topbar_panels:
            return
        for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
            try:
                panel = getattr(self.window, attr, None)
                if panel is not None:
                    panel.setVisible(False)
            except (AttributeError, RuntimeError):
                self._logger.debug(
                    "AutoHideTree: failed to hide top bar panel '%s'",
                    attr,
                    exc_info=True,
                )

    def _restore_splitter(self, splitter) -> None:
        """Restore splitter sizes when expanding."""
        if splitter is None:
            return
        try:
            if self._saved_splitter_sizes and len(self._saved_splitter_sizes) == 2:
                splitter.setSizes(self._saved_splitter_sizes)
            else:
                sizes = [int(x) for x in self.default_sizes]
                splitter.setSizes(sizes)
        except (RuntimeError, TypeError, ValueError):
            self._logger.debug(
                "AutoHideTree: failed to restore splitter sizes", exc_info=True
            )

    def _show_topbar_panels(self) -> None:
        """Show top bar panels when window is wide."""
        if not self._manage_topbar_panels:
            return
        for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
            try:
                panel = getattr(self.window, attr, None)
                if panel is not None:
                    panel.setVisible(True)
            except (AttributeError, RuntimeError):
                self._logger.debug(
                    "AutoHideTree: failed to re-show top bar panel '%s'",
                    attr,
                    exc_info=True,
                )

    def _restore_stack_index(self, stack) -> None:
        """Restore previous stack index."""
        if stack is None or self._prev_stack_index is None:
            return
        try:
            if 0 <= self._prev_stack_index < stack.count():
                stack.setCurrentIndex(self._prev_stack_index)
        except (RuntimeError, ValueError, TypeError, AttributeError):
            self._logger.debug(
                "AutoHideTree: failed to restore previous stack index",
                exc_info=True,
            )

    def _handle_narrow_window(self, splitter, stack, table, w: int) -> None:
        """Handle window collapse when width <= threshold."""
        if not self._is_collapsed:
            self._save_current_state(splitter, stack)
            self._collapse_splitter(splitter, w)
            self._switch_to_table_view(stack, table)
            self._is_collapsed = True
        self._hide_topbar_panels()

    def _handle_wide_window(self, splitter, stack) -> None:
        """Handle window expand when width > threshold."""
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

    def eventFilter(self, obj, event):
        if obj is self.window and event.type() == QEvent.Type.Resize:
            self._apply()
        return super().eventFilter(obj, event)


class WindowUISetup:
    def __init__(self, window_initializer: Any) -> None:
        self.window_initializer = window_initializer
        self.window = window_initializer.window
        self.settings = window_initializer.settings
        self.theme_ctrl = window_initializer.theme_ctrl

        self.main_layout = None

        # Subscribe to language changes
        self._language_service = LanguageService.instance()
        try:
            self._language_service.languageChanged.connect(self._on_language_changed)
        except Exception:
            logger.exception("WindowUISetup: failed to connect to languageChanged")
        if hasattr(self.window, "destroyed"):
            try:
                self.window.destroyed.connect(self._disconnect_language_service)
            except Exception:
                logger.debug(
                    "WindowUISetup: failed to connect destroyed cleanup", exc_info=True
                )

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
        self.window.setMenuBar(self.window.menu_controller.create_main_menu())

    def setup_central_widget(self) -> None:
        central = QFrame()
        try:
            central.setAutoFillBackground(True)
        except (RuntimeError, AttributeError):
            logger.debug(
                "WindowUISetup: setAutoFillBackground failed on central frame",
                exc_info=True,
            )
        central.setFrameShape(
            getattr(QFrame.Shape, app_config.ui.get_central_frame_shape())
        )
        self.window.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(*app_config.ui.get_main_layout_margins())
        self.main_layout.setSpacing(app_config.ui.get_main_layout_spacing())
        try:
            left, _, r, b = self.main_layout.getContentsMargins()
        except (RuntimeError, AttributeError):
            left, r, b = 0, 0, 0
        try:
            self.main_layout.setContentsMargins(left, 0, r, b)
        except (RuntimeError, AttributeError):
            logger.debug(
                "WindowUISetup: failed to force top margin=0 for main_layout",
                exc_info=True,
            )

    def setup_top_panel(self) -> None:
        from app.views.main_components.ui.topbar.top_bar_setup import TopBarBuilder

        TopBarBuilder(self).build()

    def _add_top_separator(self, container_parent: QWidget) -> None:
        h_line_top = QWidget(container_parent)
        h_line_top.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_top)

    def _build_top_bar_widgets_with_metrics(self, top_bar: QHBoxLayout) -> None:
        t_widgets_start = time.perf_counter()
        self.setup_top_bar_widgets(top_bar)
        t_widgets_dur = (time.perf_counter() - t_widgets_start) * 1000.0
        try:
            logger.info(
                "TopPanelMetrics: setup_top_bar_widgets: %.1f ms", t_widgets_dur
            )
        except (ValueError, TypeError):
            logger.debug(
                "TopPanelMetrics: failed to log setup_top_bar_widgets duration",
                exc_info=True,
            )

    def _create_top_bar_host(
        self, container_parent: QWidget, top_bar: QHBoxLayout
    ) -> QWidget:
        top_bar_host = QWidget(container_parent)
        top_bar_host.setObjectName("topBarHost")
        top_bar_host.setLayout(top_bar)
        try:
            top_bar_host.setFixedHeight(app_config.ui.get_top_bar_height())
            top_bar_host.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
        except (RuntimeError, TypeError, AttributeError):
            logger.warning(
                "TopPanel: failed to set top bar host size policy/height", exc_info=True
            )
        try:
            top_bar_host.setVisible(False)
        except (RuntimeError, AttributeError):
            logger.debug(
                "TopPanel: failed to initially hide top_bar_host", exc_info=True
            )
        return top_bar_host

    def _init_and_schedule_topbar_manager(self) -> None:
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
                QTimer.singleShot(0, partial(self._schedule_topbar_initialization, mgr))
        except Exception:
            logger.debug(
                "TopPanel: failed to schedule topbar initialization", exc_info=True
            )

    def _schedule_topbar_initialization(self, mgr: TopBarLayoutManager) -> None:
        if getattr(self.window, "_topbar_initialized", False):
            return
        self.window._topbar_initialized = True
        try:
            from app.utils.ui.updates import suspend_updates
        except (ImportError, ModuleNotFoundError):
            suspend_updates = None  # type: ignore[assignment]

        def _activate() -> None:
            host = getattr(self.window, "top_bar_host", None)
            if host and hasattr(host, "setVisible"):
                try:
                    if not host.isVisible():
                        host.setVisible(True)
                except (RuntimeError, AttributeError):
                    logger.debug(
                        "TopPanel: failed to show top_bar_host early", exc_info=True
                    )
            QTimer.singleShot(0, partial(self._finalize_topbar_startup, mgr))

        if suspend_updates is not None and isinstance(self.window, QWidget):
            try:
                with suspend_updates(self.window):
                    _activate()
            except (RuntimeError, AttributeError, TypeError):
                logger.debug(
                    "TopPanel: suspend_updates failed during initialization",
                    exc_info=True,
                )
                _activate()
        else:
            _activate()

    def _finalize_topbar_startup(self, mgr: TopBarLayoutManager) -> None:
        """Finalize topbar initialization after the window becomes visible.

        FIX: rely on the ``data_loaded`` signal to synchronize with data loading,
        avoiding race conditions during startup. Adds a fallback timeout.
        """
        try:
            mgr.prepare_initial_layout()
        except (RuntimeError, AttributeError):
            logger.debug("TopPanel: prepare_initial_layout failed", exc_info=True)

        controller = getattr(self.window, "top_panels_controller", None)

        # FIX: schedule fallback timeout in case data never loads
        try:
            if hasattr(mgr, "_schedule_data_ready_fallback"):
                mgr._schedule_data_ready_fallback()
        except Exception as e:
            logger.debug(f"TopPanel: failed to schedule data_ready fallback: {e}")

        # FIX: streamline initialization by removing redundant adjustments
        # Check whether the new ``data_loaded`` signal exists
        if controller and hasattr(controller, "data_loaded"):
            try:
                # Connect to the data loading signal (single-shot)
                from PyQt6.QtCore import Qt

                controller.data_loaded.connect(
                    mgr.mark_data_ready, Qt.ConnectionType.SingleShotConnection
                )
                logger.debug("TopPanel: connected to data_loaded signal")
            except Exception as e:
                logger.warning(f"TopPanel: failed to connect data_loaded signal: {e}")
                # FIX: fallback path issues a single call instead of two
                QTimer.singleShot(100, mgr.mark_data_ready)
        else:
            # FIX: fallback for older versions — trigger once instead of twice
            logger.debug(
                "TopPanel: data_loaded signal not available, using timer fallback"
            )
            QTimer.singleShot(100, mgr.mark_data_ready)

        # Trigger data refresh
        def _refresh():
            if controller and hasattr(controller, "refresh_all"):
                try:
                    controller.refresh_all()
                except (RuntimeError, AttributeError):
                    logger.warning(
                        "TopPanel: top_panels_controller.refresh_all() failed",
                        exc_info=True,
                    )

        QTimer.singleShot(0, _refresh)

    def _schedule_top_panels_refresh(self) -> None:
        controller = getattr(self.window, "top_panels_controller", None)
        if not controller or not hasattr(controller, "refresh_all"):
            return

        def _refresh() -> None:
            try:
                controller.refresh_all()
            except (RuntimeError, AttributeError):
                logger.warning(
                    "TopPanel: top_panels_controller.refresh_all() failed",
                    exc_info=True,
                )

        QTimer.singleShot(0, _refresh)

    def _on_language_changed(self, _lang_code: str) -> None:
        """Update UI texts when language changes."""
        # Update search placeholder
        try:
            from PyQt6.QtCore import QCoreApplication

            search = getattr(self.window, "search", None)
            if search is not None and hasattr(search, "setPlaceholderText"):
                # Use translated placeholder instead of hardcoded config value
                placeholder = QCoreApplication.translate(
                    "WindowUISetup", "Search\u2026 (Ctrl+F)"
                )
                search.setPlaceholderText(placeholder)
        except Exception:
            logger.debug(
                "WindowUISetup: failed to update search placeholder", exc_info=True
            )

        # Update status bar
        try:
            retranslate_cb = getattr(self.window, "_retranslate_status_bar", None)
            if callable(retranslate_cb):
                retranslate_cb()
        except Exception:
            logger.exception("WindowUISetup: failed to retranslate status bar")

        # Update top bar captions and shortcuts
        try:
            topbar_manager = getattr(self.window, "_topbar_manager", None)
            if topbar_manager and hasattr(topbar_manager, "retranslate_topbar"):
                topbar_manager.retranslate_topbar()
        except Exception:
            logger.debug("WindowUISetup: failed to retranslate top bar", exc_info=True)

    def _disconnect_language_service(self) -> None:
        try:
            self._language_service.languageChanged.disconnect(self._on_language_changed)
        except Exception:
            pass

    def _register_topbar_cleanup(self, manager: TopBarLayoutManager | None) -> None:
        """Connect window destruction to top bar cleanup for deterministic teardown."""
        if manager is None or not hasattr(self.window, "destroyed"):
            return
        if getattr(self.window, "_topbar_cleanup_connected", False):
            return
        try:
            self.window.destroyed.connect(manager.cleanup)
            self.window._topbar_cleanup_connected = True
        except Exception:
            logger.debug(
                "WindowUISetup: failed to connect top bar cleanup", exc_info=True
            )

    def _log_setup_top_panel_total(self, t_total_start: float) -> None:
        try:
            t_total_dur = (time.perf_counter() - t_total_start) * 1000.0
            logger.info("TopPanelMetrics: setup_top_panel total: %.1f ms", t_total_dur)
        except (ValueError, TypeError):
            logger.debug(
                "TopPanelMetrics: failed to log setup_top_panel total", exc_info=True
            )

    def _create_widget_by_mode(self, mode: str):
        """Create panel widget based on mode."""
        if mode == "quick":
            return QuickAddPanelWidget(self.window, category_provider=self.window)
        elif mode == "favorites":
            return FavoritesPanelWidget(self.window)
        elif mode == "recent":
            return RecentPanelWidget(self.window)
        else:
            raise ValueError(f"Unknown panel mode: {mode}")

    def _get_panel_height(self) -> int:
        """Calculate panel height from config."""
        try:
            try:
                search_h = int(app_config.ui.get_top_panel_search_height())
            except (TypeError, ValueError):
                search_h = 32
            try:
                btn_h = int(app_config.ui.get_top_panel_button_size())
            except (TypeError, ValueError):
                btn_h = 32
            return max(search_h, btn_h)
        except Exception:
            return 32

    def _configure_panel_widget(
        self, widget, object_name: str | None, log_label: str
    ) -> None:
        """Configure widget size and properties."""
        if object_name:
            widget.setObjectName(object_name)
        widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        fixed_h = self._get_panel_height()
        try:
            widget.setFixedHeight(fixed_h)
        except Exception:
            logger.debug(
                "TopPanel: failed to set fixed height on %s widget",
                log_label,
                exc_info=True,
            )
        try:
            widget.setMinimumWidth(0)
        except Exception:
            logger.debug(
                "TopPanel: failed to set minimum width on %s widget",
                log_label,
                exc_info=True,
            )

    def _adjust_panel_spacing(self, widget, log_label: str) -> None:
        """Reduce panel button spacing by 1px."""
        try:
            lay = getattr(widget, "panel_layout", None)
            if (
                lay is not None
                and hasattr(lay, "spacing")
                and hasattr(lay, "setSpacing")
            ):
                cur = int(lay.spacing())
                lay.setSpacing(max(0, cur - 1))
        except Exception:
            logger.debug(
                "TopPanel: failed to reduce panel button spacing by 1px for %s",
                log_label,
                exc_info=True,
            )

    def _create_top_panel_widget(
        self,
        top_bar: QHBoxLayout,
        mode: str,
        attr_name: str,
        object_name: str | None,
        log_label: str,
    ) -> None:
        t_start = time.perf_counter()
        try:
            widget = self._create_widget_by_mode(mode)
            self._configure_panel_widget(widget, object_name, log_label)
            setattr(self.window, attr_name, widget)
            top_bar.addWidget(widget)
            self._adjust_panel_spacing(widget, log_label)

            try:
                dur = (time.perf_counter() - t_start) * 1000.0
                logger.info(
                    "TopPanelMetrics: create_widget[%s]: %.1f ms", log_label, dur
                )
            except Exception:
                logger.debug(
                    "TopPanelMetrics: failed to log create_widget[%s] duration",
                    log_label,
                    exc_info=True,
                )
        except Exception:
            setattr(self.window, attr_name, None)
            logger.exception("TopPanel: failed to create %s widget", log_label)

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
                    top_bar.addSpacing(4)
                    top_bar.addWidget(self._create_vertical_separator())
                    top_bar.addSpacing(4)
                except Exception:
                    logger.debug(
                        "TopPanel: failed to insert vertical separator between panels",
                        exc_info=True,
                    )

        try:
            top_bar.addSpacing(4)
            top_bar.addWidget(self._create_vertical_separator())
            top_bar.addSpacing(4)
        except Exception:
            logger.debug(
                "TopPanel: failed to insert vertical separator before search",
                exc_info=True,
            )

        self.setup_search_widget(top_bar)

    def _create_vertical_separator(self) -> QWidget:
        sep = QWidget()
        sep.setObjectName("vSeparator")
        sep.setProperty("class", "vertical_separator")
        try:
            w = int(app_config.ui.get_separator_width())
        except (TypeError, ValueError):
            w = 1
        try:
            sep.setFixedWidth(max(1, w))
        except Exception:
            logger.debug(
                "TopPanel: failed to set fixed width on vertical separator",
                exc_info=True,
            )
        try:
            sep.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        except Exception:
            logger.debug(
                "TopPanel: failed to set size policy on vertical separator",
                exc_info=True,
            )
        return sep

    def setup_search_widget(self, top_bar: QHBoxLayout) -> None:
        from PyQt6.QtCore import QCoreApplication

        t_start = time.perf_counter()
        self.window.search = QLineEdit()
        # Use translated placeholder
        placeholder = QCoreApplication.translate(
            "WindowUISetup", "Search\u2026 (Ctrl+F)"
        )
        self.window.search.setPlaceholderText(placeholder)
        self.window.search.setClearButtonEnabled(True)
        try:
            self.window.search.setFixedHeight(
                int(app_config.ui.get_top_panel_search_height())
            )
        except (TypeError, ValueError, RuntimeError):
            self.window.search.setFixedHeight(32)
            logger.warning("SearchWidget: invalid search height in config; using 32")
        self.window.search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        try:
            min_search_w = int(app_config.ui.get_top_panel_search_min_width())
        except (TypeError, ValueError):
            min_search_w = 140
            logger.warning(
                "SearchWidget: invalid top_panel_search_min_width in config; using 140"
            )
        try:
            self.window.search.setMinimumWidth(min_search_w)
        except Exception:
            logger.debug("SearchWidget: failed to set minimum width", exc_info=True)
        self.window.search.setObjectName("mainSearch")

        handler = getattr(self.window, "on_search", None)
        if callable(handler):
            try:
                self.window.search.textChanged.connect(handler)
            except (TypeError, RuntimeError):
                logger.warning(
                    "SearchWidget: failed to connect on_search handler", exc_info=True
                )
        else:
            logger.warning(
                "SearchWidget: window.on_search handler not found; textChanged not connected"
            )
        # Add without stretch; `TopBarLayoutManager` applies stretch after the final adjust
        top_bar.addWidget(self.window.search)
        try:
            dur = (time.perf_counter() - t_start) * 1000.0
            logger.info("TopPanelMetrics: setup_search_widget: %.1f ms", dur)
        except Exception:
            pass

    def _normalize_top_bar_stretches(self, top_bar: QHBoxLayout) -> None:
        try:
            count = top_bar.count()
            search_widget = getattr(self.window, "search", None)
            search_index = -1
            for i in range(count):
                it = top_bar.itemAt(i)
                w = it.widget()
                if w is search_widget:
                    search_index = i
                try:
                    top_bar.setStretch(i, 0)
                except Exception:
                    logger.debug(
                        "TopPanel: failed to setStretch(0) at index %s",
                        i,
                        exc_info=True,
                    )
            if search_index >= 0:
                try:
                    top_bar.setStretch(search_index, 1)
                except Exception:
                    logger.debug(
                        "TopPanel: failed to setStretch(1) for search at index %s",
                        search_index,
                        exc_info=True,
                    )
        except Exception:
            logger.debug("TopPanel: _normalize_top_bar_stretches failed", exc_info=True)

    def setup_main_content(self) -> None:
        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )
        h_line_top = QWidget(container_parent)
        h_line_top.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_top)

        mid = QHBoxLayout()
        mid.setContentsMargins(*app_config.ui.get_layout_margins("mid"))

        self.setup_left_panel(mid)

        # Right panel containing tiles and table
        self.setup_right_panel(mid)

        self.main_layout.addLayout(mid)

        h_line_2 = QWidget(container_parent)
        h_line_2.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_2)

    def setup_left_panel(self, mid: QHBoxLayout) -> None:
        left_panel = QWidget()
        self.window.left_panel = left_panel
        left_panel.setObjectName("LeftPanel")
        left_panel.setAutoFillBackground(True)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(*app_config.ui.get_layout_margins("left"))
        left_layout.setSpacing(0)

        self.window.tree = StructureTreeView()
        self.window.tree.setHeaderHidden(True)
        self.window.tree_model = StructureTreeModel(self.window.tree)
        self.window.tree.setModel(self.window.tree_model)

        tree_icon_size = app_config.ui.get_tree_icon_size()
        row_h = app_config.ui.get_row_height()
        base_icon = int(tree_icon_size[0])
        eff_icon = max(
            0, min(base_icon, max(0, int(row_h) - 8))
        )  # 4 px top + 4 px bottom
        self.window.tree.setIconSize(QSize(eff_icon, eff_icon))

        left_layout.addWidget(self.window.tree)

        self.setup_spheres_bar(left_layout)

    def setup_spheres_bar(self, left_layout: QVBoxLayout) -> None:
        self.window.spheres_bar = QWidget()
        self.window.spheres_bar.setObjectName("spheres_bar")
        self.window.spheres_bar.setFixedHeight(app_config.ui.get_spheres_bar_height())

        s_layout = QHBoxLayout(self.window.spheres_bar)
        s_layout.setContentsMargins(*app_config.ui.get_spheres_bar_margins())
        # Spacing between items in the spheres panel
        s_layout.setSpacing(app_config.ui.get_spheres_bar_spacing())
        self.window.sphere_group = QButtonGroup(self.window)

        left_layout.addWidget(self.window.spheres_bar)

    def setup_right_panel(self, mid: QHBoxLayout) -> None:
        from app.views.main_components.ui.right_panel_setup import RightPanelBuilder

        RightPanelBuilder(self).build(mid)

    def _setup_auto_hide_tree_filter(self, splitter_sizes: list[int]) -> None:
        try:
            try:
                min_w = int(app_config.ui.get_window_min_width())
            except (TypeError, ValueError):
                min_w = 280
                logger.warning(
                    "RightPanel: invalid window_min_width in config; using 280"
                )
            self.window._auto_hide_tree_filter = _AutoHideTreeFilter(
                self.window, threshold_width=min_w, default_sizes=splitter_sizes
            )
            self.window.installEventFilter(self.window._auto_hide_tree_filter)
            try:
                if hasattr(self.window, "shown"):
                    # type: ignore[attr-defined]
                    self.window.shown.connect(self.window._auto_hide_tree_filter._apply)
                else:
                    QTimer.singleShot(0, self.window._auto_hide_tree_filter._apply)
            except (RuntimeError, AttributeError):
                logger.exception(
                    "RightPanel: failed to schedule AutoHideTree initial apply"
                )
        except (RuntimeError, TypeError, AttributeError):
            logger.exception("RightPanel: failed to initialize AutoHideTree filter")

    def setup_bottom_panel(self) -> None:
        from app.views.main_components.ui.bottom_panel_setup import BottomPanelBuilder

        BottomPanelBuilder(self).build()

    def setup_status_bar(self) -> None:
        init_status_bar(self.window)

    def setup_window_properties(self) -> None:
        self.window.setWindowTitle(app_config.ui.get_main_window_title())
        self.window.resize(*app_config.ui.get_main_window_size())
        try:
            min_w = int(app_config.ui.get_window_min_width())
            min_h = int(app_config.ui.get_window_min_height())
            self.window.setMinimumSize(min_w, min_h)
        except (TypeError, ValueError):
            logger.warning(
                "WindowProps: failed to set minimum size from config", exc_info=True
            )

        # Icon setup
        # Application logo path differs between development and packaged (PyInstaller) builds
        current_file = Path(__file__).resolve()
        base_dir = current_file.parent
        app_dir = (base_dir / ".." / ".." / "..").resolve()
        views_dir = (base_dir / ".." / "..").resolve()

        candidates = [
            app_dir / "resources" / "logo" / "logo.png",
            views_dir / "resources" / "logo" / "logo.png",
            app_dir / "logo" / "logo.png",
        ]

        if hasattr(sys, "_MEIPASS"):
            candidates.extend(
                [
                    Path(sys._MEIPASS)
                    / "app"
                    / "views"
                    / "resources"
                    / "logo"
                    / "logo.png",
                    Path(sys._MEIPASS) / "resources" / "logo" / "logo.png",
                    Path(sys._MEIPASS) / "logo" / "logo.png",
                ]
            )

        logo_path = next((str(p) for p in candidates if p.exists()), None)
        if logo_path:
            self.window.setWindowIcon(create_icon_from_path(logo_path))
        else:
            logger.warning("Logo icon not found in expected locations: %s", candidates)

    def cleanup(self) -> None:
        """Clean up `WindowUISetup` resources.

        FIX: explicitly remove event filters to avoid memory leaks.
        """
        logger.debug("WindowUISetup: starting cleanup")

        # Clear `_AutoHideTreeFilter`
        if hasattr(self.window, "_auto_hide_tree_filter"):
            try:
                filter_obj = self.window._auto_hide_tree_filter
                if filter_obj is not None:
                    # Disconnect signal
                    if hasattr(self.window, "shown"):
                        try:
                            self.window.shown.disconnect(filter_obj._apply)
                        except (TypeError, RuntimeError):
                            pass

                    # Remove event filter
                    try:
                        self.window.removeEventFilter(filter_obj)
                    except (RuntimeError, AttributeError):
                        pass

                    # Delete object
                    try:
                        filter_obj.deleteLater()
                    except (RuntimeError, AttributeError):
                        pass

                    self.window._auto_hide_tree_filter = None
                    logger.debug("WindowUISetup: cleaned up _auto_hide_tree_filter")
            except (RuntimeError, AttributeError) as cleanup_error:
                logger.warning(
                    "WindowUISetup: error cleaning up _auto_hide_tree_filter: %s",
                    cleanup_error,
                )

        logger.info("WindowUISetup: cleanup completed")
