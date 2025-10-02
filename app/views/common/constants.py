"""Константы для модуля views.

Централизация всех магических чисел и хардкодов для облегчения
конфигурирования и устранения дублирования.
"""

from PyQt6.QtGui import QColor

# ================================================================================
# ЦВЕТА
# ================================================================================

# Цвета для hover-эффектов
HOVER_COLOR = QColor("#444444")
HOVER_COLOR_LIGHT = QColor("#555555")

# Цвета для neon-эффектов
NEON_DEFAULT_COLOR = QColor("#0194F0")
NEON_HOVER_BLUR_RADIUS = 18

# Цвета для статусов
STATUS_CONNECTED_COLOR = QColor("#4CAF50")
STATUS_DISCONNECTED_COLOR = QColor("#F44336")
STATUS_WARNING_COLOR = QColor("#FF9800")


# ================================================================================
# РАЗМЕРЫ И ОТСТУПЫ
# ================================================================================

# Размеры иконок
DEFAULT_ICON_SIZE = 24
TREE_ICON_SIZE = 20
TABLE_ICON_SIZE = 24
LINK_TYPE_ICON_SIZE = 32

# Отступы
DEFAULT_MARGIN = 10
DEFAULT_SPACING = 8
FORM_LABEL_ALIGNMENT_RIGHT = True

# Размеры кнопок
FIXED_BUTTON_WIDTH = 100
FIXED_BUTTON_HEIGHT = 32

# Размеры диалогов
LINK_DIALOG_MIN_WIDTH = 600
LINK_DIALOG_MIN_HEIGHT = 500


# ================================================================================
# ТАЙМЕРЫ И ЗАДЕРЖКИ
# ================================================================================

# Debounce для поиска и ввода
SEARCH_DEBOUNCE_MS = 300
PATH_INPUT_DEBOUNCE_MS = 300

# Retry механизм
SEARCH_RETRY_ATTEMPTS = 20
SEARCH_RETRY_INTERVAL_MS = 100

# Focus guard
FOCUS_GUARD_DURATION_MS = 300


# ================================================================================
# DRAG & DROP
# ================================================================================

# MIME типы
MIME_LINK = "application/x-aite-link-id"
MIME_STRUCTURE_TREE = "application/x-structure-tree-index"

# Настройки pixmap для drag
DRAG_PIXMAP_MAX_WIDTH = 300
DRAG_PIXMAP_SINGLE_HEIGHT = 40
DRAG_PIXMAP_MULTI_HEIGHT = 50


# ================================================================================
# ТЕКСТОВЫЕ КОНСТАНТЫ (до внедрения i18n)
# ================================================================================

# Статус бар
STATUS_DB_CONNECTED = "🟢 БД подключена"
STATUS_DB_DISCONNECTED = "🔴 БД отключена"
STATUS_READY = "Готово"
STATUS_PATH_PREFIX = "Путь: "
STATUS_LINKS_PREFIX = "Ссылок: "
STATUS_CATEGORIES_PREFIX = "Категорий: "

# Кнопки
BUTTON_OK = "Сохранить"
BUTTON_CANCEL = "Отмена"
BUTTON_BROWSE = "Обзор…"
BUTTON_PROFILE = "Профиль"
BUTTON_ICON = "Иконка"
BUTTON_CLOSE = "Закрыть"

# Заголовки диалогов
DIALOG_TITLE_ADD_LINK = "Добавить ссылку"
DIALOG_TITLE_EDIT_LINK = "Редактировать ссылку"
DIALOG_TITLE_CONFIRM = "Подтверждение"
DIALOG_TITLE_ERROR = "Ошибка"
DIALOG_TITLE_WARNING = "Предупреждение"
DIALOG_TITLE_INFO = "Информация"

# Сообщения
MSG_ICON_NOT_FOUND = "Иконка по умолчанию не найдена."
MSG_CONFIG_INVALID = "Некорректная конфигурация иконок."
MSG_PROCESSING_CANCEL = "Идёт обработка ссылки. Закрыть окно?"


# ================================================================================
# НАСТРОЙКИ ТАБЛИЦ
# ================================================================================

# Индексы колонок таблицы ссылок
COL_FAVORITE = 0
COL_NAME = 1
COL_LAST_USED = 2
COL_NOTES = 3

# Заголовки колонок (до i18n)
TABLE_HEADERS = ["♥", "Название", "Открывалась", "Заметки"]

# Режимы отображения
DISPLAY_MODE_NORMAL = "normal"
DISPLAY_MODE_SEARCH = "search"


# ================================================================================
# НАСТРОЙКИ ДЕРЕВА
# ================================================================================

# Типы узлов
NODE_TYPE_ROOT = "root"
NODE_TYPE_SECTION = "section"
NODE_TYPE_CATEGORY = "category"


# ================================================================================
# ЛИМИТЫ
# ================================================================================

# Максимальные длины для отображения
MAX_NAME_DISPLAY_LENGTH = 100
MAX_TOOLTIP_LENGTH = 500
MAX_NOTES_PREVIEW_LENGTH = 50

# Лимиты для производительности
MAX_PIXMAP_CACHE_SIZE = 100
MAX_ICON_CACHE_SIZE = 500


# ================================================================================
# ШРИФТЫ И СТИЛИ
# ================================================================================

# Размеры шрифтов (по умолчанию, могут переопределяться в конфиге)
DEFAULT_FONT_SIZE = 10
TABLE_FONT_SIZE = 10
TREE_FONT_SIZE = 10
STATUS_BAR_FONT_SIZE = 9

# Стили текста
TEXT_ELIDE_MODE = "right"  # "left", "middle", "right"
