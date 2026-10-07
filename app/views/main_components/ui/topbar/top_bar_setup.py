# app/views/main_components/top_bar_setup.py
from __future__ import annotations

from contextlib import contextmanager
import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QToolBar, QToolButton, QWidget

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.ui.icon.path_service import icon_path_service
from app.views.main_components.ui.topbar.toolbar_adapters import (
    LinksToolbarAdapter,
    QuickAddToolbarAdapter,
    RecentHistoryToolbarAdapter,
    StructureActionsToolbarAdapter,
    ToolbarSeparatorController,
    ToolsToolbarAdapter,
    _icon_from_path,
    _resolve_theme,
    _setup_topbar_button_contrast,
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
            if not btn.property("toolbar_btn"):
                btn.setProperty("toolbar_btn", True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setArrowType(Qt.ArrowType.NoArrow)
                btn.setIconSize(self.iconSize())
                from app.utils.ui.menu_builders.base import get_menu_icon
                theme = _resolve_theme()
                icon = get_menu_icon("more", theme)
                if not icon or icon.isNull():
                    icon_path = icon_path_service.get_ui_icons_dir() / "base" / "more.svg"
                    icon = _icon_from_path(icon_path)
                if icon and not icon.isNull():
                    btn.setIcon(icon)
                style = btn.style()
                if style is not None:
                    style.unpolish(btn)
                    style.polish(btn)

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

            sep_add_tools = toolbar.addSeparator()
            sep_tools_recent = toolbar.addSeparator()
            sep_recent_fav = toolbar.addSeparator()

            sep_controller = ToolbarSeparatorController(
                sep_add_tools, sep_tools_recent, sep_recent_fav
            )
            structure_adapter = StructureActionsToolbarAdapter(
                toolbar,
                insert_before=anchor_quick,
                category_provider=self.window,
                separator_controller=sep_controller,
            )
            quick_adapter = QuickAddToolbarAdapter(
                toolbar,
                insert_before=sep_add_tools,
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

            end_marker = QAction(toolbar)
            end_marker.setVisible(False)
            toolbar.addAction(end_marker)

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

            # Responsive folding controller for Favorites block
            class _ResponsiveTopBarFilter(QObject):
                def __init__(self, fav_adapt, host_w):
                    super().__init__(host_w)
                    self._fav = fav_adapt
                    self._host = host_w

                def eventFilter(self, watched, event):
                    if event.type() == QEvent.Type.Resize:
                        items = self._fav.get_items()
                        k = len(items)
                        expanded_fav_w = k * 34 + max(0, k - 1) * 4
                        needed_w = 323 + 27 + 220 + 110 + expanded_fav_w
                        w = self._host.width()
                        if self._fav.is_folded():
                            if w >= needed_w + 20:
                                self._fav.set_folded(False)
                        else:
                            if w < needed_w - 20:
                                self._fav.set_folded(True)
                    return False

            top_bar_filter = _ResponsiveTopBarFilter(fav_adapter, top_bar_host)
            top_bar_host.installEventFilter(top_bar_filter)
            self.window._top_bar_responsive_filter = top_bar_filter

        # Add separator before search
        try:
            sep_spacing = int(app_config.ui.get_topbar_separator_spacing())
            top_bar.addSpacing(sep_spacing)
            search_sep = self.ui._create_vertical_separator()
            top_bar.addWidget(search_sep)
            self.window.search_separator = search_sep
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
            theme_layout.setContentsMargins(sep_spacing, 0, 0, 0)
            theme_layout.setSpacing(sep_spacing)
            theme_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

            theme_separator = self.ui._create_vertical_separator()
            theme_layout.addWidget(theme_separator)
            self.window.theme_selector_separator = theme_separator

            from app.utils.ui.menu_builders.base import get_menu_icon
            from app.views.main_components.ui.topbar.toolbar_adapters import _resolve_theme
            theme = _resolve_theme()

            btn_size = int(app_config.ui.get_top_panel_button_size())
            icon_sz = app_config.ui.get_top_panel_icon_size()
            settings_toolbar = TopBarToolBar(theme_container, button_height=btn_size)
            settings_toolbar.setObjectName("topBarToolbar")
            settings_toolbar.setMovable(False)
            settings_toolbar.setFloatable(False)
            settings_toolbar.setContentsMargins(0, 0, 0, 0)
            settings_toolbar.setSizePolicy(
                getattr(QSizePolicy.Policy, "Fixed", QSizePolicy.Policy.Fixed),
                QSizePolicy.Policy.Fixed,
            )

            # Light themes rotation button
            light_icon = get_menu_icon("light", theme)
            if not light_icon or light_icon.isNull():
                light_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "light.svg")
            light_text = QCoreApplication.translate("MenuActions", "Light themes")
            light_action = QAction(light_icon, "", settings_toolbar)
            light_action.setToolTip(light_text)
            if hasattr(self.window, "theme_ctrl") and self.window.theme_ctrl:
                light_action.triggered.connect(self.window.theme_ctrl.rotate_light_theme)
            settings_toolbar.addAction(light_action)
            light_btn = settings_toolbar.widgetForAction(light_action)
            if isinstance(light_btn, QToolButton):
                light_btn.setObjectName("topBarLightThemeButton")
                light_btn.setIconSize(QSize(int(icon_sz[0]), int(icon_sz[1])))
                light_btn.setProperty("toolbar_btn", True)
                light_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _setup_topbar_button_contrast(light_btn, light_icon, "light.svg")
            self.window.light_theme_button = light_btn
            self.window.light_theme_action = light_action

            # Dark themes rotation button
            dark_icon = get_menu_icon("dark", theme)
            if not dark_icon or dark_icon.isNull():
                dark_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "dark.svg")
            dark_text = QCoreApplication.translate("MenuActions", "Dark themes")
            dark_action = QAction(dark_icon, "", settings_toolbar)
            dark_action.setToolTip(dark_text)
            if hasattr(self.window, "theme_ctrl") and self.window.theme_ctrl:
                dark_action.triggered.connect(self.window.theme_ctrl.rotate_dark_theme)
            settings_toolbar.addAction(dark_action)
            dark_btn = settings_toolbar.widgetForAction(dark_action)
            if isinstance(dark_btn, QToolButton):
                dark_btn.setObjectName("topBarDarkThemeButton")
                dark_btn.setIconSize(QSize(int(icon_sz[0]), int(icon_sz[1])))
                dark_btn.setProperty("toolbar_btn", True)
                dark_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _setup_topbar_button_contrast(dark_btn, dark_icon, "dark.svg")
            self.window.dark_theme_button = dark_btn
            self.window.dark_theme_action = dark_action

            settings_icon = get_menu_icon("settings", theme)
            if not settings_icon or settings_icon.isNull():
                settings_icon = _icon_from_path(icon_path_service.get_ui_icons_dir() / "base" / "settings.svg")
            settings_text = QCoreApplication.translate("MenuActions", "Settings")
            settings_action = QAction(settings_icon, "", settings_toolbar)
            settings_action.setToolTip(settings_text)
            settings_handler = getattr(self.window, "show_settings_dialog", None)
            if callable(settings_handler):
                settings_action.triggered.connect(settings_handler)
            settings_toolbar.addAction(settings_action)
            settings_btn = settings_toolbar.widgetForAction(settings_action)
            if isinstance(settings_btn, QToolButton):
                settings_btn.setObjectName("topBarSettingsButton")
                settings_btn.setIconSize(QSize(int(icon_sz[0]), int(icon_sz[1])))
                settings_btn.setProperty("toolbar_btn", True)
                settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _setup_topbar_button_contrast(settings_btn, settings_icon, "settings.svg")
            theme_layout.addWidget(settings_toolbar)
            self.window.settings_toolbar = settings_toolbar
            self.window.settings_button = settings_btn
            self.window.settings_action = settings_action

            theme_container.setLayout(theme_layout)
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

