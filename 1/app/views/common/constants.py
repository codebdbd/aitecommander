"""Constants for the ``views`` module.

Centralize magic numbers and hardcoded values to simplify configuration and
eliminate duplication.
"""

from PyQt6.QtGui import QColor

# ================================================================================
# COLORS
# ================================================================================

# Colors for hover effects
HOVER_COLOR = QColor("#444444")
HOVER_COLOR_LIGHT = QColor("#555555")

# Colors for neon effects
NEON_DEFAULT_COLOR = QColor("#0194F0")
NEON_HOVER_BLUR_RADIUS = 18

# Colors for statuses
STATUS_CONNECTED_COLOR = QColor("#4CAF50")
STATUS_DISCONNECTED_COLOR = QColor("#F44336")
STATUS_WARNING_COLOR = QColor("#FF9800")


# ================================================================================
# SIZES AND MARGINS
# ================================================================================

# Icon sizes
DEFAULT_ICON_SIZE = 24
TREE_ICON_SIZE = 20
TABLE_ICON_SIZE = 24
LINK_TYPE_ICON_SIZE = 32

# Margins
DEFAULT_MARGIN = 10
DEFAULT_SPACING = 8
FORM_LABEL_ALIGNMENT_RIGHT = True

# Button sizes
FIXED_BUTTON_WIDTH = 100
FIXED_BUTTON_HEIGHT = 32

# Dialog sizes
LINK_DIALOG_MIN_WIDTH = 600
LINK_DIALOG_MIN_HEIGHT = 500


# ================================================================================
# TIMERS AND DELAYS
# ================================================================================

# Debounce for search and text input
SEARCH_DEBOUNCE_MS = 300
PATH_INPUT_DEBOUNCE_MS = 300

# Retry mechanism
SEARCH_RETRY_ATTEMPTS = 20
SEARCH_RETRY_INTERVAL_MS = 100

# Focus guard
FOCUS_GUARD_DURATION_MS = 300


# ================================================================================
# DRAG & DROP
# ================================================================================

# MIME types
MIME_LINK = "application/x-aite-link-id"
MIME_STRUCTURE_TREE = "application/x-structure-tree-index"

# Drag pixmap sizes
DRAG_PIXMAP_MAX_WIDTH = 300
DRAG_PIXMAP_SINGLE_HEIGHT = 40
DRAG_PIXMAP_MULTI_HEIGHT = 50


# ================================================================================
# TEXT CONSTANTS (pre-i18n; source language is English)
# ================================================================================

# Status bar
STATUS_DB_CONNECTED = "🟢 DB connected"
STATUS_DB_DISCONNECTED = "🔴 DB disconnected"
STATUS_READY = "Ready"
STATUS_PATH_PREFIX = "Path: "
STATUS_LINKS_PREFIX = "Links: "
STATUS_CATEGORIES_PREFIX = "Categories: "

# Buttons
BUTTON_OK = "Save"
BUTTON_CANCEL = "Cancel"
BUTTON_BROWSE = "Browse…"
BUTTON_PROFILE = "Profile"
BUTTON_ICON = "Icon"
BUTTON_CLOSE = "Close"

# Dialog titles
DIALOG_TITLE_ADD_LINK = "Add link"
DIALOG_TITLE_EDIT_LINK = "Edit link"
DIALOG_TITLE_CONFIRM = "Confirmation"
DIALOG_TITLE_ERROR = "Error"
DIALOG_TITLE_WARNING = "Warning"
DIALOG_TITLE_INFO = "Information"

# Messages
MSG_ICON_NOT_FOUND = "Default icon not found."
MSG_CONFIG_INVALID = "Invalid icon configuration."
MSG_PROCESSING_CANCEL = "A link is being processed. Close the window?"


# ================================================================================
# TABLE SETTINGS
# ================================================================================

# Column indices for the links table
COL_FAVORITE = 0
COL_NAME = 1
COL_LAST_USED = 2
COL_NOTES = 3

# Column headers (pre-i18n)
TABLE_HEADERS = ["♥", "Name", "Last opened", "Notes"]

# Display modes
DISPLAY_MODE_NORMAL = "normal"
DISPLAY_MODE_SEARCH = "search"


# ================================================================================
# TREE SETTINGS
# ================================================================================

# Node types
NODE_TYPE_ROOT = "root"
NODE_TYPE_SECTION = "section"
NODE_TYPE_CATEGORY = "category"


# ================================================================================
# LIMITS
# ================================================================================

# Maximum display lengths
MAX_NAME_DISPLAY_LENGTH = 100
MAX_TOOLTIP_LENGTH = 500
MAX_NOTES_PREVIEW_LENGTH = 50

# Performance-related limits
MAX_PIXMAP_CACHE_SIZE = 100
MAX_ICON_CACHE_SIZE = 500


# ================================================================================
# FONTS AND STYLES
# ================================================================================

DEFAULT_FONT_SIZE = 10
TABLE_FONT_SIZE = 10
TREE_FONT_SIZE = 10
STATUS_BAR_FONT_SIZE = 9

# Text elide mode
# TEXT_ELIDE_MODE = "right"  # "left", "middle", "right"
