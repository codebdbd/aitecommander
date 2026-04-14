"""Constants used by the main-window components.

Improvement note: centralized constants replace magic strings and numbers,
which makes maintenance easier and prevents typos.
"""

from __future__ import annotations

from enum import Enum

from app.config_data.runtime_config import runtime_app_config as app_config

# === Widget attribute names ===


class WidgetAttribute(str, Enum):
    """Attribute names stored on the main window widgets."""

    # Top bar
    TOP_BAR_HOST = "top_bar_host"
    CONTENT_CONTAINER = "content_container"
    QUICK_ADD_WIDGET = "quick_add_widget"
    FAV_WIDGET = "fav_widget"
    RECENT_LINKS_WIDGET = "recent_links_widget"
    SEARCH = "search"

    # Main area
    LEFT_PANEL = "left_panel"
    TREE = "tree"
    TREE_MODEL = "tree_model"
    SPLITTER = "splitter"
    STACK = "stack"
    TILES = "tiles"
    TILES_SCROLL = "tiles_scroll"
    TABLE = "table"
    TABLE_CONTAINER = "table_container"

    # Bottom bar
    SPHERES_BAR = "spheres_bar"
    SPHERE_GROUP = "sphere_group"
    SPHERE_BUTTONS = "sphere_buttons"
    BOTTOM_BAR_CONTAINER = "bottom_bar_container"
    SWITCH_SPHERE_BUTTON = "switch_sphere_button"

    # Controllers
    STRUCTURE_BUSINESS = "structure_business"
    TOP_PANELS_CONTROLLER = "top_panels_controller"
    UI_STATE = "ui_state"


class ObjectName(str, Enum):
    """Qt ``objectName`` values for widgets."""

    TOP_BAR_HOST = "topBarHost"
    MAIN_SEARCH = "mainSearch"
    FAVORITES_WIDGET = "favoritesWidget"
    RECENT_LINKS_WIDGET = "recentLinksWidget"
    LEFT_PANEL = "LeftPanel"
    SPHERES_BAR = "spheres_bar"
    BOTTOM_BAR_CONTAINER = "bottomBarContainer"
    BOTTOM_SEPARATOR = "bottomSeparator"
    V_SEPARATOR = "vSeparator"


# === Timeouts and intervals ===


class Timeout(int, Enum):
    """Timeouts expressed in milliseconds.

    IMPORTANT: default fallback values. When runtime configuration is available,
    prefer calls to ``app_config.ui.get_topbar_throttle_ms()`` and similar accessors.
    """

    # Initialization
    DATA_READY_FALLBACK = 500  # Wait for data loading to finish
    DB_POLL_INTERVAL = 100  # Polling interval for database readiness

    # UI updates (fallback values; rely on config for customization)
    THROTTLE_RESIZE = 50  # Resize throttling interval (see ui.topbar.throttle_ms)
    DEFER_OPERATION = 0  # QTimer.singleShot for deferred operations
    TOPBAR_SHOW_DELAY = 10  # Delay before showing the top bar
    DIAGNOSTICS_DELAY = 100  # Delay before running diagnostics after window show

    # Animations
    ANIMATION_DURATION = 140  # Duration of show/hide animations


# Handy aliases for frequent usage
MS_100 = Timeout.DB_POLL_INTERVAL
MS_50 = Timeout.THROTTLE_RESIZE
DEFER = Timeout.DEFER_OPERATION


# === Sizes and padding ===


class Size(int, Enum):
    """UI element sizes in pixels.

    IMPORTANT: fallback values. For runtime-configurable settings consult
    ``app_config.ui`` methods such as:
    - ``get_window_min_width()``, ``get_window_min_height()``
    - ``get_top_panel_search_min_width()``, ``get_spheres_bar_height()``
    - ``get_top_bar_height()``, ``get_separator_width()``
    """

    # Minimum sizes (algorithmic constraints, not changed at runtime)
    MIN_PANEL_WIDTH = app_config.ui.get_topbar_min_panel_width()
    MIN_SEARCH_WIDTH = app_config.ui.get_main_components_min_search_width()

    # Maximum sizes (Qt constraints)
    MAX_WIDGET_WIDTH = app_config.ui.get_topbar_max_widget_width()  # Qt QWIDGETSIZE_MAX
    MAX_SEARCH_WIDTH = app_config.ui.get_main_components_max_search_width()
    MAX_VISIBLE_BUTTONS = app_config.ui.get_topbar_max_visible_buttons()

    # Adaptive thresholds (not configurable via JSON)
    NARROW_MODE_THRESHOLD = app_config.ui.get_topbar_narrow_threshold()
    HYSTERESIS_THRESHOLD = app_config.ui.get_topbar_hysteresis_threshold()


class Spacing(int, Enum):
    """Margins and spacing values in pixels.

    IMPORTANT: for UI spacing prefer ``app_config.ui`` helpers:
    - ``get_top_bar_spacing()``, ``get_top_bar_widgets_side_spacing()``
    - ``get_main_layout_spacing()``, ``get_bottom_layout_spacing()``
    """

    # Algorithm constants (static at runtime)
    SEPARATOR_SPACING_VISIBLE = app_config.ui.get_topbar_separator_search_spacing()
    SEPARATOR_SPACING_HIDDEN = app_config.ui.get_topbar_separator_hidden_spacing()


# === Performance limits ===


class PerformanceLimit(int, Enum):
    """Performance-related thresholds."""

    CACHE_MAX_SIZE = 100  # Maximum LRU cache size
    MAX_RESIZE_LOGS = 5  # Maximum resize log entries
    MAX_MOVE_LOGS = 5  # Maximum move log entries

    # Slow operation thresholds (milliseconds)
    SLOW_ADJUST_THRESHOLD = 35  # Threshold for slow adjust
    SLOW_CLAMP_THRESHOLD = 15  # Threshold for slow clamp_search_width


# === Status bar messages ===


class StatusMessage(str, Enum):
    """Strings shown in the status bar."""

    READY = "Ready"
    WAITING_FOR_DB = "Waiting for database to become ready..."
    INITIALIZING = "Initializing..."
    LOADING = "Loading..."


# === Configuration keys ===


class ConfigKey(str, Enum):
    """Application configuration keys."""

    # UI configuration
    UI_TOPBAR_THROTTLE_MS = "ui.topbar.throttle_ms"
    UI_TOPBAR_LOG_INFO = "ui.topbar.log_info"
    TOPBAR_MIN_VISIBLE = "topbar.min_visible"

    # Diagnostics
    DIAG_RESIZE_LOG_MAX_RESIZES = "diag.resize_log.max_resizes"
    DIAG_RESIZE_LOG_MAX_MOVES = "diag.resize_log.max_moves"

    # Auto-hide
    UI_AUTO_HIDE_MANAGE_TOPBAR = "ui.auto_hide_manage_topbar"
    UI_AUTO_HIDE_SWITCH_TO_TABLE = "ui.auto_hide_switch_to_table"


# === Event sources ===


class EventSource(str, Enum):
    """Event sources tracked by the application."""

    CATEGORY_TILES = "CategoryTiles"
    TREE_VIEW = "TreeView"
    SEARCH = "Search"
    MENU = "Menu"
    KEYBOARD = "Keyboard"


# === CSS classes ===


class CSSClass(str, Enum):
    """CSS class names used for styling."""

    SEPARATOR = "separator"
    VERTICAL_SEPARATOR = "vertical_separator"
    LAST_BUTTON = "last"  # Applied to the last button in a panel


# === Logging tags ===


class LogTag(str, Enum):
    """Tags used for structured logging."""

    INIT = "WindowInit"
    TOPBAR = "TopBar"
    TOPBAR_METRICS = "TopPanelMetrics"
    TOPBAR_DIAG = "TopbarDiag"
    DIAG_TOP_LEVELS = "DiagTopLevels"
    BOTTOM_PANEL = "BottomPanel"
    RIGHT_PANEL = "RightPanel"
    SEARCH_WIDGET = "SearchWidget"
    AUTO_HIDE_TREE = "AutoHideTree"
    RESOURCE_MANAGER = "ResourceManager"


# === Metrics ===


class MetricName(str, Enum):
    """Metric identifiers for monitoring."""

    # Initialization
    LIGHT_INIT_WINDOW_PROPERTIES = "light:_init_window_properties"
    LIGHT_INIT_BASIC_ATTRIBUTES = "light:_init_basic_attributes"
    LIGHT_INIT_MENU = "light:_init_menu"
    LIGHT_INIT_CENTRAL_WIDGET = "light:_init_central_widget"
    LIGHT_CAPTURE_MAIN_LAYOUT = "light:_capture_main_layout"
    LIGHT_INIT_TOP_PANEL = "light:_init_top_panel"

    # Asynchronous operations
    ASYNC_STRUCTURE_LOAD = "async:structure_load"
    ASYNC_LOAD_STRUCTURE_ASYNC_STARTED = "async:load_structure_async started"

    # Final operations
    FINAL_WINDOW_SHOW = "final:window_show"

    # Topbar operations
    TOPBAR_ADJUST = "adjust"
    TOPBAR_CLAMP_SEARCH_WIDTH = "clamp_search_width"
    TOPBAR_SETUP_WIDGETS = "setup_top_bar_widgets"
    TOPBAR_SETUP_SEARCH = "setup_search_widget"
    TOPBAR_CREATE_WIDGET_QUICK = "create_widget[QuickAdd]"
    TOPBAR_CREATE_WIDGET_FAVORITES = "create_widget[Favorites]"
    TOPBAR_CREATE_WIDGET_RECENT = "create_widget[Recent]"
