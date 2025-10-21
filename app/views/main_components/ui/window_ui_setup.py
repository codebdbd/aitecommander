from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Protocol

from PyQt6.QtCore import (
    QT_TRANSLATE_NOOP,
    QCoreApplication,
    QFile,
    QEvent,
    QObject,
    QSize,
    QTimer,
)
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
from app.utils.cache.topbar_snapshot import TopBarSnapshot, TopBarSnapshotStore
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.views.main_components.ui.topbar.top_bar_layout_manager import (
    TopBarLayoutManager,
)
from app.views.main_components.ui.topbar.models.topbar_constants import (
    TOPBAR_CONSTANTS as TOPBAR_CONST,
)
from app.views.models.structure_tree_model import StructureTreeModel
from app.views.widgets.custom_widgets import StructureTreeView
from app.views.widgets.panels.favorites_panel_widget import FavoritesPanelWidget
from app.views.widgets.panels.quick_add_panel_widget import QuickAddPanelWidget
from app.views.widgets.panels.recent_panel_widget import RecentPanelWidget
from app.views.widgets.status_bar import setup_status_bar as init_status_bar
from i18n.language_service import LanguageService

logger = logging.getLogger(__name__)

_SEARCH_PLACEHOLDER = QT_TRANSLATE_NOOP("WindowUISetup", "Search\u2026 (Ctrl+F)")

# lupdate hint for dynamic placeholder text
if False:  # pragma: no cover
    QCoreApplication.translate("WindowUISetup", "Search\u2026 (Ctrl+F)")


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
    def settings(self) -> object: ...
    @property
    def theme_ctrl(self) -> object: ...


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

        self._language_service = LanguageService.instance()
        self._connect_language_service()

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
        self.window.setMenuBar(self.window.menu_controller.create_main_menu())

    def setup_central_widget(self) -> None:
        central = QFrame(self.window)
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

    def _apply_snapshot_to_widgets(self, snapshot: TopBarSnapshot) -> bool:
        """Apply snapshot data directly to widgets when controller is unavailable."""
        applied = False
        fav_widget = getattr(self.window, "fav_widget", None)
        recent_widget = getattr(self.window, "recent_links_widget", None)
        try:
            if fav_widget and hasattr(fav_widget, "set_data"):
                fav_widget.set_data(snapshot.favorites)
                applied = applied or bool(snapshot.favorites)
        except Exception:
            logger.debug(
                "WindowUISetup: failed to apply favorites snapshot directly",
                exc_info=True,
            )
        try:
            if recent_widget and hasattr(recent_widget, "set_data"):
                recent_widget.set_data(snapshot.recents)
                applied = applied or bool(snapshot.recents)
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

        applied = False
        if controller is None:
            applied = self._apply_snapshot_to_widgets(snapshot)
            if applied:
                self._pending_topbar_snapshot = snapshot
                setattr(self.window, "_pending_topbar_snapshot", snapshot)
        else:
            try:
                applied = controller.apply_snapshot(
                    snapshot.favorites, snapshot.recents
                )
            except Exception:
                logger.debug(
                    "WindowUISetup: failed to apply top bar snapshot via controller",
                    exc_info=True,
                )
        if applied:
            self._topbar_snapshot_applied = True
        return applied, snapshot

    def _schedule_topbar_initialization(self, mgr: TopBarLayoutManager) -> None:
        if getattr(self.window, "_topbar_initialized", False):
            return
        self.window._topbar_initialized = True
        QTimer.singleShot(0, partial(self._finalize_topbar_startup, mgr))

    def _finalize_topbar_startup(self, mgr: TopBarLayoutManager) -> None:
        try:
            mgr.prepare_initial_layout()
        except (RuntimeError, AttributeError):
            logger.debug("TopPanel: prepare_initial_layout failed", exc_info=True)
        except Exception:
            logger.debug("TopPanel: initial layout setup failed", exc_info=True)

        controller = getattr(self.window, "top_panels_controller", None)

        snapshot_loaded = False
        snapshot: TopBarSnapshot | None = None
        if controller:
            snapshot_loaded, snapshot = self._prefill_topbar_from_snapshot(controller)

        if controller and hasattr(controller, "data_loaded"):
            try:
                from PyQt6.QtCore import Qt

                controller.data_loaded.connect(
                    mgr.mark_data_ready, Qt.ConnectionType.SingleShotConnection
                )
                logger.debug("TopPanel: connected to data_loaded signal")
            except Exception as e:
                logger.warning(f"TopPanel: failed to connect data_loaded: {e}")

        if controller and hasattr(controller, "refresh_all"):
            QTimer.singleShot(0, lambda: self._safe_refresh_all(controller))

        try:
            mgr.mark_data_ready()
        except Exception:
            logger.debug("TopPanel: immediate mark_data_ready failed", exc_info=True)

        if snapshot_loaded and snapshot is not None:
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

    def _safe_refresh_all(self, controller) -> None:
        try:
            controller.refresh_all()
        except (RuntimeError, AttributeError):
            logger.warning("TopPanel: refresh_all failed", exc_info=True)

    def _schedule_top_panels_refresh(self) -> None:
        controller = getattr(self.window, "top_panels_controller", None)
        if not controller or not hasattr(controller, "refresh_all"):
            return
        QTimer.singleShot(0, lambda: self._safe_refresh_all(controller))

    def _on_language_changed(self, _lang_code: str) -> None:
        try:
            from PyQt6.QtCore import QCoreApplication

            search = getattr(self.window, "search", None)
            if search is not None and hasattr(search, "setPlaceholderText"):
                placeholder = QCoreApplication.translate("WindowUISetup", "Search\u2026 (Ctrl+F)")
                search.setPlaceholderText(placeholder)
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
            search_h = 32
        try:
            btn_h = int(app_config.ui.get_top_panel_button_size())
        except (TypeError, ValueError):
            btn_h = 32
        return max(search_h, btn_h)

    def _compute_panel_placeholder_width(self, mode: str) -> int:
        """Estimate placeholder width for data-driven panels."""
        if mode == "quick":
            # Quick panel has static content immediately; no placeholder needed.
            return 0

        try:
            button_size = int(app_config.ui.get_top_panel_button_size())
        except (TypeError, ValueError):
            button_size = TOPBAR_CONST.DEFAULT_BUTTON_SIZE

        try:
            spacing = int(app_config.ui.get_top_bar_buttons_spacing())
        except (TypeError, ValueError):
            spacing = TOPBAR_CONST.SEPARATOR_SPACING_VISIBLE

        baseline_items = {
            "favorites": max(3, TOPBAR_CONST.DEFAULT_MIN_FAV or 3),
            "recent": max(3, TOPBAR_CONST.DEFAULT_MIN_RECENT or 3),
        }.get(mode, 3)

        effective_count = max(1, baseline_items)
        width = button_size * effective_count
        if effective_count > 1:
            width += spacing * (effective_count - 1)

        # Add padding for container margins/borders
        width += 16

        try:
            search_min = int(app_config.ui.get_top_panel_search_min_width())
        except (TypeError, ValueError):
            search_min = TOPBAR_CONST.MIN_SEARCH_WIDTH

        minimum = max(TOPBAR_CONST.MIN_PANEL_WIDTH * 2, int(search_min * 0.5))
        return max(width, minimum)

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
                setattr(widget, "_placeholder_min_width", placeholder_width)
                widget.setMinimumWidth(placeholder_width)
            except Exception:
                logger.debug(
                    f"TopPanel: failed to configure placeholder width on {log_label}",
                    exc_info=True,
                )

    def _adjust_panel_spacing(self, widget, log_label: str) -> None:
        try:
            lay = getattr(widget, "panel_layout", None)
            if lay is not None and hasattr(lay, "spacing") and hasattr(lay, "setSpacing"):
                cur = int(lay.spacing())
                lay.setSpacing(max(0, cur - 1))
        except Exception:
            logger.debug(f"TopPanel: failed to adjust spacing for {log_label}", exc_info=True)

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
                    top_bar.addSpacing(4)
                    top_bar.addWidget(self._create_vertical_separator())
                    top_bar.addSpacing(4)
                except Exception:
                    logger.debug("TopPanel: failed to insert separator", exc_info=True)

        try:
            top_bar.addSpacing(4)
            top_bar.addWidget(self._create_vertical_separator())
            top_bar.addSpacing(4)
        except Exception:
            logger.debug("TopPanel: failed to insert separator before search", exc_info=True)

        self.setup_search_widget(top_bar)

    def _create_vertical_separator(self) -> QWidget:
        sep = QWidget(self.window)
        sep.setObjectName("vSeparator")
        sep.setProperty("class", "vertical_separator")
        try:
            w = int(app_config.ui.get_separator_width())
        except (TypeError, ValueError):
            w = 1
        try:
            sep.setFixedWidth(max(1, w))
        except Exception:
            logger.debug("TopPanel: failed to set separator width", exc_info=True)
        try:
            sep.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        except Exception:
            logger.debug("TopPanel: failed to set separator policy", exc_info=True)
        return sep

    def setup_search_widget(self, top_bar: QHBoxLayout) -> None:
        from PyQt6.QtCore import QCoreApplication

        self.window.search = QLineEdit()
        placeholder = QCoreApplication.translate("WindowUISetup", "Search\u2026 (Ctrl+F)")
        self.window.search.setPlaceholderText(placeholder)
        self.window.search.setClearButtonEnabled(True)
        try:
            self.window.search.setFixedHeight(int(app_config.ui.get_top_panel_search_height()))
        except (TypeError, ValueError, RuntimeError):
            self.window.search.setFixedHeight(32)
            logger.warning("SearchWidget: invalid height, using 32")
        self.window.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        try:
            min_search_w = int(app_config.ui.get_top_panel_search_min_width())
        except (TypeError, ValueError):
            min_search_w = 140
            logger.warning("SearchWidget: invalid min width, using 140")
        try:
            self.window.search.setMinimumWidth(min_search_w)
        except Exception:
            logger.debug("SearchWidget: failed to set min width", exc_info=True)
        self.window.search.setObjectName("mainSearch")

        handler = getattr(self.window, "on_search", None)
        if callable(handler):
            try:
                self.window.search.textChanged.connect(handler)
            except (TypeError, RuntimeError):
                logger.warning("SearchWidget: failed to connect handler", exc_info=True)
        else:
            logger.warning("SearchWidget: on_search handler not found")
        top_bar.addWidget(self.window.search)

    def _normalize_top_bar_stretches(self, top_bar: QHBoxLayout) -> None:
        try:
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
                    logger.debug(f"TopPanel: failed to setStretch({stretch}) at index {i}", exc_info=True)
        except Exception:
            logger.debug("TopPanel: _normalize_top_bar_stretches failed", exc_info=True)

    def setup_main_content(self) -> None:
        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )
        h_line_top = QWidget(container_parent)
        h_line_top.setProperty("class", "separator")
        if self.main_layout is not None:
            self.main_layout.addWidget(h_line_top)

        mid = QHBoxLayout()
        mid.setContentsMargins(*app_config.ui.get_layout_margins("mid"))
        mid.setSpacing(app_config.ui.get_main_layout_spacing())
        self.setup_left_panel(mid)
        self.setup_right_panel(mid)
        if self.main_layout is not None:
            self.main_layout.addLayout(mid)

        h_line_2 = QWidget(container_parent)
        h_line_2.setProperty("class", "separator")
        if self.main_layout is not None:
            self.main_layout.addWidget(h_line_2)

    def setup_left_panel(self, mid: QHBoxLayout) -> None:
        left_panel = QWidget(self.window)
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
        eff_icon = max(0, min(base_icon, max(0, int(row_h) - 8)))
        self.window.tree.setIconSize(QSize(eff_icon, eff_icon))

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

        RightPanelBuilder(self).build(mid)

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
            setattr(self.window, "_pending_topbar_snapshot", snapshot)
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
            min_w = 280
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
                    QTimer.singleShot(0, self.window._auto_hide_tree_filter._apply)
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
        self.window.setWindowTitle(app_config.ui.get_main_window_title())
        self.window.resize(*app_config.ui.get_main_window_size())
        try:
            min_w = int(app_config.ui.get_window_min_width())
            min_h = int(app_config.ui.get_window_min_height())
            self.window.setMinimumSize(min_w, min_h)
        except (TypeError, ValueError):
            logger.warning("WindowProps: failed to set minimum size", exc_info=True)
        current_file = Path(__file__).resolve()
        base_dir = current_file.parent
        app_dir = (base_dir / ".." / ".." / "..").resolve()
        views_dir = (base_dir / ".." / "..").resolve()

        candidates: list[str] = ["appres:logo/logo.png"]
        file_candidates = [
            app_dir / "resources" / "logo" / "logo.png",
            views_dir / "resources" / "logo" / "logo.png",
            app_dir / "logo" / "logo.png",
        ]

        if hasattr(sys, "_MEIPASS"):
            file_candidates.extend(
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

        candidates.extend(str(path) for path in file_candidates)

        def _candidate_exists(candidate: str) -> bool:
            if candidate.startswith(("appres:", ":/")):
                return QFile.exists(candidate)
            try:
                return Path(candidate).exists()
            except (OSError, ValueError):
                return False

        logo_path = next((candidate for candidate in candidates if _candidate_exists(candidate)), None)
        if logo_path:
            self.window.setWindowIcon(create_icon_from_path(logo_path))
        else:
            logger.warning(f"Logo icon not found in: {candidates}")

    def cleanup(self) -> None:
        logger.debug("WindowUISetup: starting cleanup")

        self._disconnect_language_service()
        if hasattr(self.window, "_auto_hide_tree_filter"):
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

        logger.info("WindowUISetup: cleanup completed")
