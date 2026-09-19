# app/views/main_components/top_bar_setup.py
from __future__ import annotations

from contextlib import contextmanager
import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QToolBar, QToolButton, QWidget

from app.config_data.runtime_config import runtime_app_config as app_config
from app.views.main_components.ui.topbar.toolbar_adapters import (
    FavoritesToolbarAdapter,
    LinksToolbarAdapter,
    QuickAddToolbarAdapter,
    RecentHistoryToolbarAdapter,
    StructureActionsToolbarAdapter,
    ToolbarSeparatorController,
    ToolsToolbarAdapter,
)
from app.views.widgets.theme_selector import ThemeSelector

if TYPE_CHECKING:
    from app.views.main_components.ui.window_ui_setup import WindowUISetup

__all__ = ["TopBarToolBar", "TopBarBuilder"]

logger = logging.getLogger(__name__)

_DEFAULT_SPACING: int = 4
_DEFAULT_BUTTON_SIZE: int = 32


class _StageTimer:
    """Lightweight stage timing collector for diagnostic logging."""

    def __init__(self) -> None:
        self.timings: dict[str, float] = {}

    @contextmanager
    def measure(self, name: str):
        start = perf_counter()
        try:
            yield
        finally:
            self.timings[name] = (perf_counter() - start) * 1000.0


class TopBarToolBar(QToolBar):
    """QToolBar subclass that vertically centres the Qt extension (overflow) button."""

    def __init__(self, parent: QWidget | None = None, button_height: int = _DEFAULT_BUTTON_SIZE) -> None:
        if isinstance(parent, QWidget):
            super().__init__(parent)
        else:
            try:
                super().__init__(parent)
            except TypeError:
                super().__init__()
        self._button_height = max(1, int(button_height))
        try:
            if self.layout() is not None:
                self.layout().setSpacing(_DEFAULT_SPACING)
        except (RuntimeError, AttributeError):
            pass

    def set_button_height(self, height: int) -> None:
        self._button_height = max(1, int(height))
        self._centre_ext_button()

    def resizeEvent(self, event) -> None:
        try:
            super().resizeEvent(event)
        except (RuntimeError, AttributeError):
            pass
        self._centre_ext_button()

    def _centre_ext_button(self) -> None:
        try:
            btn = self.findChild(QToolButton, "qt_toolbar_ext_button")
        except (RuntimeError, AttributeError):
            return
        if btn is None or btn.isHidden():
            return
        try:
            geo = btn.geometry()
            target_y = max(0, (self.height() - self._button_height) // 2)
            if geo.y() != target_y or geo.height() != self._button_height:
                btn.setGeometry(geo.x(), target_y, geo.width(), self._button_height)
        except (RuntimeError, AttributeError):
            pass


class TopBarBuilder:
    """Assemble the top bar using ``WindowUISetup`` helpers.

    Does not alter existing behavior.
    """

    def __init__(self, ui: WindowUISetup) -> None:
        self.ui = ui
        self.window = ui.window
        self.main_layout = ui.main_layout

    def _resolve_container_parent(self) -> QWidget | None:
        """Determine parent widget for top-bar helper components."""
        parent_fn = getattr(self.main_layout, "parentWidget", None)
        if callable(parent_fn):
            try:
                parent = parent_fn()
                if isinstance(parent, QWidget):
                    return parent
            except (RuntimeError, AttributeError):
                pass
        central_fn = getattr(self.window, "centralWidget", None)
        if callable(central_fn):
            try:
                central = central_fn()
                if isinstance(central, QWidget):
                    return central
            except (RuntimeError, AttributeError):
                pass
        return None

    def build(self) -> None:
        """Construct and attach the top bar.

        Responsibilities:
        - Insert the top separator into the main layout.
        - Create and configure the top-bar layout (margins, spacing, alignment).
        - Populate the top bar via existing helpers
          (Quick/Favorites/Recent/Search).
        - Create the host widget, add it to ``self.main_layout``,
          set ``window.top_bar_host``.
        - Initialize ``TopBarLayoutManager`` and schedule post-shown
          adjustments.

        Note: the method preserves existing behavior
        (metrics, timing, visibility rules).
        """
        total_start = perf_counter()
        timer = _StageTimer()

        with timer.measure("cleanup"):
            # Remove any previously built top bar to keep build() idempotent.
            existing_host = getattr(self.window, "top_bar_host", None)
            if isinstance(existing_host, QWidget):
                try:
                    if self.main_layout is not None:
                        self.main_layout.removeWidget(existing_host)
                except (RuntimeError, AttributeError):
                    logger.debug("TopPanel: failed to detach existing top bar host", exc_info=True)
                try:
                    existing_host.setParent(None)
                    existing_host.deleteLater()
                except (RuntimeError, AttributeError):
                    logger.debug("TopPanel: failed to dispose existing top bar host", exc_info=True)
            # Determine parent for helper widgets
            container_parent = self._resolve_container_parent()

        # Remove the previous top separator;
        # QMenuBar border-bottom draws the visual line

        # Create top bar layout: toolbar + search field
        with timer.measure("layout"):
            top_bar = QHBoxLayout()
            try:
                side = int(app_config.ui.get_top_bar_widgets_side_spacing())
            except (TypeError, ValueError):
                side = 6
                logger.warning("TopPanel: invalid side spacing in config; using default 8")
            top_bar.setContentsMargins(4, 0, side, 0)
            top_bar.setSpacing(0)
            top_bar.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Build toolbar actions (quick/favorites/recents)
        with timer.measure("toolbar"):
            try:
                spacing = int(app_config.ui.get_top_bar_buttons_spacing())
            except (TypeError, ValueError):
                spacing = _DEFAULT_SPACING
            try:
                button_size = int(app_config.ui.get_top_panel_button_size())
            except (TypeError, ValueError):
                button_size = _DEFAULT_BUTTON_SIZE

            toolbar = TopBarToolBar(container_parent, button_height=button_size)
            toolbar.setObjectName("topBarToolbar")
            toolbar.setMovable(False)
            toolbar.setFloatable(False)
            toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            icon_size = None
            try:
                icon_size = app_config.ui.get_top_panel_icon_size()
                toolbar.setIconSize(QSize(int(icon_size[0]), int(icon_size[1])))
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            toolbar.setSizePolicy(
                getattr(QSizePolicy.Policy, "Maximum", QSizePolicy.Policy.Fixed),
                QSizePolicy.Policy.Fixed,
            )
            try:
                toolbar.setFixedHeight(int(app_config.ui.get_top_bar_height()))
            except (TypeError, ValueError, AttributeError):
                logger.debug("TopPanel: failed to set toolbar height", exc_info=True)
            toolbar.setContentsMargins(0, 0, 0, 0)
            anchor_quick = QAction(toolbar)
            anchor_quick.setVisible(False)
            toolbar.addAction(anchor_quick)

            anchor_tools = QAction(toolbar)
            anchor_tools.setVisible(False)
            toolbar.addAction(anchor_tools)

            sep_tools_recent = toolbar.addSeparator()
            sep_recent_fav = toolbar.addSeparator()

            # Invisible anchor action: ensures Favorite actions are inserted
            # before any trailing items added to the toolbar later.
            end_marker = QAction(toolbar)
            end_marker.setVisible(False)
            toolbar.addAction(end_marker)

            sep_controller = ToolbarSeparatorController(sep_tools_recent, sep_recent_fav)
            structure_adapter = StructureActionsToolbarAdapter(
                toolbar,
                insert_before=anchor_quick,
                category_provider=self.window,
                separator_controller=sep_controller,
            )
            quick_adapter = QuickAddToolbarAdapter(
                toolbar,
                insert_before=anchor_tools,
                category_provider=self.window,
                separator_controller=sep_controller,
            )
            tools_adapter = ToolsToolbarAdapter(
                toolbar,
                insert_before=sep_tools_recent,
                category_provider=self.window,
                separator_controller=sep_controller,
            )
            recent_adapter = RecentHistoryToolbarAdapter(
                toolbar,
                insert_before=sep_recent_fav,
                button_object_name="recentButton",
                category_provider=self.window,
                emit_refresh_on_click=True,
                separator_controller=sep_controller,
            )
            fav_adapter = LinksToolbarAdapter(
                toolbar,
                insert_before=end_marker,
                button_object_name="favoriteButton",
                group_name="fav",
                emit_refresh_on_click=False,
                separator_controller=sep_controller,
            )

            self.window.top_bar_toolbar = toolbar
            self.window.structure_actions_widget = structure_adapter
            self.window.quick_add_widget = quick_adapter
            self.window.tools_actions_widget = tools_adapter
            self.window.recent_links_widget = recent_adapter
            self.window.fav_widget = fav_adapter

            # Apply cached top-panel data as soon as widgets exist, before the
            # controller and layout manager come online later in startup.
            try:
                self.ui._prefill_topbar_widgets_before_manager()
            except (RuntimeError, AttributeError, TypeError):
                logger.debug(
                    "TopPanel: early snapshot prefill failed",
                    exc_info=True,
                )

            top_bar.addWidget(toolbar)
            self._apply_toolbar_spacing(toolbar, spacing, button_size)

        # Snapshot prefill is deferred to the post-show startup phase.
        timer.timings["prefill"] = 0.0

        # Create and insert host
        with timer.measure("host"):
            top_bar_host = self.ui._create_top_bar_host(container_parent, top_bar)
            self.main_layout.addWidget(top_bar_host)
            self.window.top_bar_host = top_bar_host

        # Add separator before search
        try:
            sep_spacing = int(app_config.ui.get_topbar_separator_spacing())
            top_bar.addSpacing(sep_spacing)
            top_bar.addWidget(self.ui._create_vertical_separator())
            top_bar.addSpacing(sep_spacing)
        except (RuntimeError, AttributeError):
            logger.debug("TopPanel: failed to insert toolbar/search separator", exc_info=True)

        # Add search widget to layout after toolbar
        with timer.measure("search"):
            self.ui.setup_search_widget(top_bar)

        # Add Theme Selector & Separator container
        try:
            theme_container = QWidget(top_bar_host if isinstance(top_bar_host, QWidget) else None)
            theme_container.setObjectName("themeSelectorContainer")
            try:
                theme_container.setFixedHeight(int(app_config.ui.get_top_bar_height()))
                theme_container.setSizePolicy(
                    getattr(QSizePolicy.Policy, "Maximum", QSizePolicy.Policy.Fixed),
                    QSizePolicy.Policy.Fixed,
                )
            except (TypeError, ValueError, AttributeError):
                pass

            sep_spacing = int(app_config.ui.get_topbar_separator_spacing())
            theme_layout = QHBoxLayout()
            theme_layout.setContentsMargins(0, 0, 0, 0)
            theme_layout.setSpacing(sep_spacing)
            theme_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            theme_separator = self.ui._create_vertical_separator()
            theme_layout.addWidget(theme_separator)
            self.window.theme_selector_separator = theme_separator

            theme_selector = ThemeSelector(self.window.theme_ctrl, theme_container)
            try:
                theme_selector.setFixedHeight(int(app_config.ui.get_top_panel_button_size()))
                theme_selector.setSizePolicy(
                    getattr(QSizePolicy.Policy, "Maximum", QSizePolicy.Policy.Fixed),
                    QSizePolicy.Policy.Fixed,
                )
                theme_selector.setMaximumWidth(120)
            except (TypeError, ValueError, AttributeError):
                pass
            theme_layout.addWidget(theme_selector)
            self.window.theme_selector = theme_selector

            theme_container.setLayout(theme_layout)
            top_bar.addSpacing(sep_spacing)
            top_bar.addWidget(theme_container)
            self.window.theme_selector_container = theme_container
        except (RuntimeError, TypeError, AttributeError):
            logger.exception("TopPanel: failed to add ThemeSelector container")

        # Ensure search widget receives stretch while toolbar and selectors stay fixed
        try:
            if hasattr(self.ui, "_normalize_top_bar_stretches"):
                self.ui._normalize_top_bar_stretches(top_bar)
        except (RuntimeError, AttributeError):
            logger.debug("TopPanel: failed to normalize top bar stretches", exc_info=True)

        # Schedule top panels refresh (toolbar does overflow on its own)
        with timer.measure("schedule"):
            self.ui._init_and_schedule_topbar_manager()

        logger.info(
            "[Perf] TopBar build: total=%.2f ms cleanup=%.2f ms layout=%.2f ms "
            "toolbar=%.2f ms prefill=%.2f ms host=%.2f ms search=%.2f ms "
            "schedule=%.2f ms",
            (perf_counter() - total_start) * 1000.0,
            timer.timings.get("cleanup", 0.0),
            timer.timings.get("layout", 0.0),
            timer.timings.get("toolbar", 0.0),
            timer.timings.get("prefill", 0.0),
            timer.timings.get("host", 0.0),
            timer.timings.get("search", 0.0),
            timer.timings.get("schedule", 0.0),
        )

    def _apply_toolbar_spacing(
        self, toolbar: QToolBar, spacing: int, button_size: int
    ) -> None:
        try:
            toolbar.setContentsMargins(0, 0, 0, 0)
        except (RuntimeError, AttributeError):
            logger.debug("TopPanel: failed to set toolbar right margin", exc_info=True)
        if isinstance(toolbar, TopBarToolBar):
            toolbar.set_button_height(button_size)
        try:
            if toolbar.layout() is not None:
                toolbar.layout().setSpacing(max(0, int(spacing)))
        except (RuntimeError, AttributeError):
            logger.debug("TopPanel: failed to set toolbar layout spacing", exc_info=True)

