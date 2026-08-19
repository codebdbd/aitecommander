# app/views/main_components/top_bar_setup.py
from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QToolBar, QToolButton, QWidget

from app.config_data.runtime_config import runtime_app_config as app_config
from app.views.main_components.ui.topbar.toolbar_adapters import (
    LinksToolbarAdapter,
    QuickAddToolbarAdapter,
    ToolbarSeparatorController,
)

logger = logging.getLogger(__name__)


class _ExtButtonAligner(QObject):
    """Vertically centres the QToolBar extension button.

    ``QToolBarLayout`` positions the extension button via a separate
    code-path that does not centre it like regular action widgets.
    This event filter fires after each layout pass and adjusts the
    button's geometry so it aligns with the other toolbar buttons.
    """

    def __init__(self, toolbar: QToolBar, button_height: int) -> None:
        super().__init__(toolbar)
        self._toolbar = toolbar
        self._button_height = button_height
        self._pending = False

    # -- QObject overrides --------------------------------------------------

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        etype = event.type()
        if etype in (QEvent.Type.LayoutRequest, QEvent.Type.Resize):
            if not self._pending:
                self._pending = True
                QTimer.singleShot(0, self._centre)
        return False

    # -- internal -----------------------------------------------------------

    def _centre(self) -> None:
        self._pending = False
        try:
            btn = self._toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
        except RuntimeError:
            return
        if btn is None or not btn.isVisible():
            return
        geo = btn.geometry()
        target_y = max(0, (self._toolbar.height() - self._button_height) // 2)
        if geo.y() != target_y or geo.height() != self._button_height:
            btn.setGeometry(geo.x(), target_y, geo.width(), self._button_height)


class TopBarBuilder:
    """Assemble the top bar using ``WindowUISetup`` helpers.

    Does not alter existing behavior.
    """

    def __init__(self, ui: Any) -> None:
        # ui is WindowUISetup; typed as Any to avoid circular imports
        self.ui = ui
        self.window = ui.window
        self.main_layout = ui.main_layout

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
        cleanup_ms = 0.0
        layout_ms = 0.0
        toolbar_ms = 0.0
        prefill_ms = 0.0
        host_ms = 0.0
        search_ms = 0.0
        schedule_ms = 0.0

        cleanup_start = perf_counter()
        # Remove any previously built top bar to keep build() idempotent.
        existing_host = getattr(self.window, "top_bar_host", None)
        if isinstance(existing_host, QWidget):
            try:
                if self.main_layout is not None:
                    self.main_layout.removeWidget(existing_host)
            except Exception:
                logger.debug("TopPanel: failed to detach existing top bar host", exc_info=True)
            try:
                existing_host.setParent(None)
                existing_host.deleteLater()
            except Exception:
                logger.debug("TopPanel: failed to dispose existing top bar host", exc_info=True)
        # Determine parent for helper widgets
        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )
        cleanup_ms = (perf_counter() - cleanup_start) * 1000.0

        # Remove the previous top separator;
        # QMenuBar border-bottom draws the visual line

        # Create top bar layout: toolbar + search field
        layout_start = perf_counter()
        top_bar = QHBoxLayout()
        try:
            side = int(app_config.ui.get_top_bar_widgets_side_spacing())
        except (TypeError, ValueError):
            side = 8
            logger.warning("TopPanel: invalid side spacing in config; using default 8")
        top_bar.setContentsMargins(side, 0, side, 0)
        top_bar.setSpacing(0)
        top_bar.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout_ms = (perf_counter() - layout_start) * 1000.0

        # Build toolbar actions (quick/favorites/recents)
        toolbar_start = perf_counter()
        toolbar = QToolBar(container_parent)
        toolbar.setObjectName("topBarToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        try:
            icon_size = app_config.ui.get_top_panel_icon_size()
            toolbar.setIconSize(QSize(int(icon_size[0]), int(icon_size[1])))
        except Exception:
            pass
        toolbar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        try:
            toolbar.setFixedHeight(int(app_config.ui.get_top_bar_height()))
        except (TypeError, ValueError, AttributeError):
            logger.debug("TopPanel: failed to set toolbar height", exc_info=True)
        try:
            toolbar.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        try:
            spacing = int(app_config.ui.get_top_bar_buttons_spacing())
        except (TypeError, ValueError):
            spacing = 4
        try:
            button_size = int(app_config.ui.get_top_panel_button_size())
        except (TypeError, ValueError):
            button_size = 32
        sep_quick_fav = toolbar.addSeparator()
        sep_fav_recent = toolbar.addSeparator()
        end_marker = QAction(toolbar)
        end_marker.setVisible(False)
        toolbar.addAction(end_marker)

        sep_controller = ToolbarSeparatorController(sep_quick_fav, sep_fav_recent)
        quick_adapter = QuickAddToolbarAdapter(
            toolbar,
            insert_before=sep_quick_fav,
            category_provider=self.window,
            separator_controller=sep_controller,
        )
        fav_adapter = LinksToolbarAdapter(
            toolbar,
            insert_before=sep_fav_recent,
            button_object_name="favoriteButton",
            group_name="fav",
            emit_refresh_on_click=False,
            separator_controller=sep_controller,
        )
        recent_adapter = LinksToolbarAdapter(
            toolbar,
            insert_before=end_marker,
            button_object_name="recentButton",
            group_name="recent",
            emit_refresh_on_click=True,
            separator_controller=sep_controller,
        )

        self.window.top_bar_toolbar = toolbar
        self.window.quick_add_widget = quick_adapter
        self.window.fav_widget = fav_adapter
        self.window.recent_links_widget = recent_adapter

        # Apply cached top-panel data as soon as widgets exist, before the
        # controller and layout manager come online later in startup.
        try:
            self.ui._prefill_topbar_widgets_before_manager()
        except Exception:
            logger.debug(
                "TopPanel: early snapshot prefill failed",
                exc_info=True,
            )
        toolbar_ms = (perf_counter() - toolbar_start) * 1000.0

        # Snapshot prefill is deferred to the post-show startup phase.
        prefill_ms = 0.0

        top_bar.addWidget(toolbar)
        self._apply_toolbar_spacing(toolbar, spacing, button_size)

        # Create and insert host
        host_start = perf_counter()
        top_bar_host = self.ui._create_top_bar_host(container_parent, top_bar)
        self.main_layout.addWidget(top_bar_host)
        self.window.top_bar_host = top_bar_host
        host_ms = (perf_counter() - host_start) * 1000.0

        # Add separator before search
        try:
            top_bar.addSpacing(4)
            top_bar.addWidget(self.ui._create_vertical_separator())
            top_bar.addSpacing(4)
        except Exception:
            logger.debug("TopPanel: failed to insert toolbar/search separator", exc_info=True)

        # Add search widget to layout after toolbar
        search_start = perf_counter()
        self.ui.setup_search_widget(top_bar)
        search_ms = (perf_counter() - search_start) * 1000.0

        # Add vertical separator before Theme Selector
        try:
            if hasattr(top_bar, "addSpacing"):
                top_bar.addSpacing(4)
            theme_separator = self.ui._create_vertical_separator()
            top_bar.addWidget(theme_separator)
            self.window.theme_selector_separator = theme_separator
            if hasattr(top_bar, "addSpacing"):
                top_bar.addSpacing(4)
        except Exception:
            logger.debug("TopPanel: failed to insert theme selector separator", exc_info=True)

        # Add Theme Selector combobox
        try:
            from app.views.widgets.theme_selector import ThemeSelector
            theme_selector = ThemeSelector(self.window.theme_ctrl, top_bar_host)
            theme_selector.setFixedWidth(120)
            try:
                theme_selector.setFixedHeight(int(app_config.ui.get_top_panel_button_size()))
            except Exception:
                pass
            top_bar.addWidget(theme_selector)
            self.window.theme_selector = theme_selector
        except Exception:
            logger.exception("TopPanel: failed to add ThemeSelector")

        # Schedule top panels refresh (toolbar does overflow on its own)
        schedule_start = perf_counter()
        self.ui._init_and_schedule_topbar_manager()
        schedule_ms = (perf_counter() - schedule_start) * 1000.0

        logger.info(
            "[Perf] TopBar build: total=%.2f ms cleanup=%.2f ms layout=%.2f ms "
            "toolbar=%.2f ms prefill=%.2f ms host=%.2f ms search=%.2f ms "
            "schedule=%.2f ms",
            (perf_counter() - total_start) * 1000.0,
            cleanup_ms,
            layout_ms,
            toolbar_ms,
            prefill_ms,
            host_ms,
            search_ms,
            schedule_ms,
        )

    def _apply_toolbar_spacing(
        self, toolbar: QToolBar, spacing: int, button_size: int
    ) -> None:
        effective_spacing = max(0, spacing)
        try:
            toolbar.setStyleSheet(
                "QToolBar#topBarToolbar QToolButton[toolbar_btn=\"true\"] { "
                f"min-width: {button_size}px; "
                f"max-width: {button_size}px; "
                f"min-height: {button_size}px; "
                f"max-height: {button_size}px; "
                f"margin-right: {effective_spacing}px; "
                "}"
                "QToolBar#topBarToolbar QToolButton[toolbar_last=\"true\"] { "
                "margin-right: 0px; }"
            )
        except Exception:
            logger.debug("TopPanel: failed to apply toolbar spacing stylesheet", exc_info=True)
        try:
            # Reserve space for the last button's right margin so it is not clipped.
            toolbar.setContentsMargins(0, 0, effective_spacing, 0)
        except Exception:
            logger.debug("TopPanel: failed to set toolbar right margin", exc_info=True)

        # Centre the Qt extension button (three-dot overflow) vertically.
        # QToolBarLayout positions it via a separate code-path that does
        # not centre it like regular action widgets.
        try:
            aligner = _ExtButtonAligner(toolbar, button_size)
            toolbar.installEventFilter(aligner)
        except Exception:
            logger.debug("TopPanel: failed to install ext-button aligner", exc_info=True)
