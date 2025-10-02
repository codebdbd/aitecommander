"""Константы для компонентов главного окна.

УЛУЧШЕНИЕ: Централизованные константы заменяют магические строки и числа,
улучшая поддерживаемость и предотвращая опечатки.
"""

from __future__ import annotations

from enum import Enum


# === Имена атрибутов виджетов ===

class WidgetAttribute(str, Enum):
    """Имена атрибутов виджетов на главном окне."""
    
    # Верхняя панель
    TOP_BAR_HOST = "top_bar_host"
    CONTENT_CONTAINER = "content_container"
    QUICK_ADD_WIDGET = "quick_add_widget"
    FAV_WIDGET = "fav_widget"
    RECENT_LINKS_WIDGET = "recent_links_widget"
    SEARCH = "search"
    
    # Основная область
    LEFT_PANEL = "left_panel"
    TREE = "tree"
    TREE_MODEL = "tree_model"
    SPLITTER = "splitter"
    STACK = "stack"
    TILES = "tiles"
    TILES_SCROLL = "tiles_scroll"
    TABLE = "table"
    TABLE_CONTAINER = "table_container"
    
    # Нижняя панель
    SPHERES_BAR = "spheres_bar"
    SPHERE_GROUP = "sphere_group"
    SPHERE_BUTTONS = "sphere_buttons"
    BOTTOM_BAR_CONTAINER = "bottom_bar_container"
    SWITCH_SPHERE_BUTTON = "switch_sphere_button"
    
    # Контроллеры
    STRUCTURE_BUSINESS = "structure_business"
    TOP_PANELS_CONTROLLER = "top_panels_controller"
    UI_STATE = "ui_state"


class ObjectName(str, Enum):
    """Qt objectName для виджетов."""
    
    TOP_BAR_HOST = "topBarHost"
    MAIN_SEARCH = "mainSearch"
    FAVORITES_WIDGET = "favoritesWidget"
    RECENT_LINKS_WIDGET = "recentLinksWidget"
    LEFT_PANEL = "LeftPanel"
    SPHERES_BAR = "spheres_bar"
    BOTTOM_BAR_CONTAINER = "bottomBarContainer"
    BOTTOM_SEPARATOR = "bottomSeparator"
    V_SEPARATOR = "vSeparator"


# === Таймауты и интервалы ===

class Timeout(int, Enum):
    """Таймауты в миллисекундах.
    
    ВАЖНО: Значения по умолчанию. Для runtime-конфигурируемых параметров
    используй app_config.ui.get_topbar_throttle_ms() и другие методы.
    """
    
    # Инициализация
    DATA_READY_FALLBACK = 500  # Таймаут ожидания загрузки данных
    DB_POLL_INTERVAL = 100  # Интервал опроса готовности БД
    
    # UI обновления (fallback значения, читай из config для customization)
    THROTTLE_RESIZE = 50  # Throttle для resize событий (см. ui.topbar.throttle_ms)
    DEFER_OPERATION = 0  # QTimer.singleShot для defer операций
    TOPBAR_SHOW_DELAY = 10  # Задержка показа topbar после инициализации
    DIAGNOSTICS_DELAY = 100  # Задержка для диагностики после показа окна
    
    # Анимации
    ANIMATION_DURATION = 140  # Длительность анимаций появления/скрытия

# Удобные алиасы для частых случаев
MS_100 = Timeout.DB_POLL_INTERVAL
MS_50 = Timeout.THROTTLE_RESIZE
DEFER = Timeout.DEFER_OPERATION


# === Размеры и отступы ===

class Size(int, Enum):
    """Размеры UI элементов в пикселях.
    
    ВАЖНО: Это fallback значения. Для runtime-конфигурируемых параметров
    читай из app_config.ui:
    - get_window_min_width(), get_window_min_height()
    - get_top_panel_search_min_width(), get_spheres_bar_height()
    - get_top_bar_height(), get_separator_width()
    """
    
    # Минимальные размеры (для алгоритмов, не меняются в runtime)
    MIN_PANEL_WIDTH = 50
    MIN_SEARCH_WIDTH = 50
    
    # Максимальные размеры (Qt ограничения)
    MAX_WIDGET_WIDTH = 16777215  # Qt QWIDGETSIZE_MAX
    MAX_SEARCH_WIDTH = 800
    MAX_VISIBLE_BUTTONS = 20
    
    # Пороги для адаптивности (не конфигурируются через JSON)
    NARROW_MODE_THRESHOLD = 380  # Ширина для переключения в узкий режим
    HYSTERESIS_THRESHOLD = 8  # Базовый порог для hysteresis


class Spacing(int, Enum):
    """Отступы и spacing в пикселях.
    
    ВАЖНО: Для UI spacing читай из app_config.ui:
    - get_top_bar_spacing(), get_top_bar_widgets_side_spacing()
    - get_main_layout_spacing(), get_bottom_layout_spacing()
    """
    
    # Константы для алгоритмов (не меняются в runtime)
    SEPARATOR_SPACING_VISIBLE = 4
    SEPARATOR_SPACING_HIDDEN = 0


# === Лимиты производительности ===

class PerformanceLimit(int, Enum):
    """Лимиты для производительности."""
    
    CACHE_MAX_SIZE = 100  # Максимальный размер LRU кэша
    MAX_RESIZE_LOGS = 5  # Максимум логов resize событий
    MAX_MOVE_LOGS = 5  # Максимум логов move событий
    
    # Пороги медленных операций (миллисекунды)
    SLOW_ADJUST_THRESHOLD = 35  # Порог медленного adjust
    SLOW_CLAMP_THRESHOLD = 15  # Порог медленного clamp_search_width


# === Сообщения статус-бара ===

class StatusMessage(str, Enum):
    """Сообщения для статус-бара."""
    
    READY = "Готово"
    WAITING_FOR_DB = "Ожидание готовности базы данных..."
    INITIALIZING = "Инициализация..."
    LOADING = "Загрузка..."


# === Ключи конфигурации ===

class ConfigKey(str, Enum):
    """Ключи конфигурации приложения."""
    
    # UI конфигурация
    UI_TOPBAR_THROTTLE_MS = "ui.topbar.throttle_ms"
    UI_TOPBAR_LOG_INFO = "ui.topbar.log_info"
    TOPBAR_MIN_VISIBLE = "topbar.min_visible"
    
    # Диагностика
    DIAG_RESIZE_LOG_MAX_RESIZES = "diag.resize_log.max_resizes"
    DIAG_RESIZE_LOG_MAX_MOVES = "diag.resize_log.max_moves"
    
    # Auto-hide
    UI_AUTO_HIDE_MANAGE_TOPBAR = "ui.auto_hide_manage_topbar"
    UI_AUTO_HIDE_SWITCH_TO_TABLE = "ui.auto_hide_switch_to_table"


# === Источники событий ===

class EventSource(str, Enum):
    """Источники событий для трекинга."""
    
    CATEGORY_TILES = "CategoryTiles"
    TREE_VIEW = "TreeView"
    SEARCH = "Search"
    MENU = "Menu"
    KEYBOARD = "Keyboard"


# === CSS классы ===

class CSSClass(str, Enum):
    """CSS классы для стилизации."""
    
    SEPARATOR = "separator"
    VERTICAL_SEPARATOR = "vertical_separator"
    LAST_BUTTON = "last"  # Для последней кнопки в панели


# === Приоритеты логирования ===

class LogTag(str, Enum):
    """Теги для структурированного логирования."""
    
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


# === Метрики ===

class MetricName(str, Enum):
    """Имена метрик для мониторинга."""
    
    # Инициализация
    LIGHT_INIT_WINDOW_PROPERTIES = "light:_init_window_properties"
    LIGHT_INIT_BASIC_ATTRIBUTES = "light:_init_basic_attributes"
    LIGHT_INIT_MENU = "light:_init_menu"
    LIGHT_INIT_CENTRAL_WIDGET = "light:_init_central_widget"
    LIGHT_CAPTURE_MAIN_LAYOUT = "light:_capture_main_layout"
    LIGHT_INIT_TOP_PANEL = "light:_init_top_panel"
    
    # Асинхронные операции
    ASYNC_STRUCTURE_LOAD = "async:structure_load"
    ASYNC_LOAD_STRUCTURE_ASYNC_STARTED = "async:load_structure_async started"
    
    # Финальные операции
    FINAL_WINDOW_SHOW = "final:window_show"
    
    # TopBar операции
    TOPBAR_ADJUST = "adjust"
    TOPBAR_CLAMP_SEARCH_WIDTH = "clamp_search_width"
    TOPBAR_SETUP_WIDGETS = "setup_top_bar_widgets"
    TOPBAR_SETUP_SEARCH = "setup_search_widget"
    TOPBAR_CREATE_WIDGET_QUICK = "create_widget[QuickAdd]"
    TOPBAR_CREATE_WIDGET_FAVORITES = "create_widget[Favorites]"
    TOPBAR_CREATE_WIDGET_RECENT = "create_widget[Recent]"


