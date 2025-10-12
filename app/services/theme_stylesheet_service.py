from __future__ import annotations

import logging
import re
from collections import OrderedDict
from threading import RLock

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class ThemeStylesheetService:
    """Responsible for QSS preparation: reading files, building override blocks and LRU-cache."""

    def __init__(self, app_config, *, max_cache_size: int | None = None, settings=None):
        self._app_config = app_config
        self._settings = settings  # User settings for dynamic font sizes
        self._qss_cache: OrderedDict[str, str] = OrderedDict()
        self._common_qss: str | None = None
        self._cache_lock = RLock()
        # ✅ FIX: Cache for QSS overrides
        self._overrides_cache: str | None = None
        try:
            initial_size = max_cache_size
            if initial_size is None:
                initial_size = int(getattr(app_config, "qss_cache_size", 10))
        except Exception:
            initial_size = 10
        if initial_size is None:
            initial_size = 10
        if initial_size < 0:
            logger.warning(
                "ThemeStylesheetService: negative cache size (%s) normalized to 0",
                initial_size,
            )
            initial_size = 0
        self._max_cache_size = initial_size

    # ---------------------- Public methods ----------------------
    def clear_cache(self) -> None:
        """Clears all caches (themes, common.qss, overrides).

        ✅ FIX: Also clears overrides_cache.
        """
        with self._cache_lock:
            cache_size = len(self._qss_cache)
            self._qss_cache.clear()
            self._common_qss = None
            self._overrides_cache = None  # ✅ Clear overrides
        logger.debug(
            "ThemeStylesheetService: cache cleared, removed %d entries", cache_size
        )

    def get_cache_stats(self) -> dict[str, object]:
        with self._cache_lock:
            return {
                "cache_size": len(self._qss_cache),
                "max_size": self._max_cache_size,
                "cached_themes": list(self._qss_cache.keys()),
                "common_qss_loaded": self._common_qss is not None,
            }

    def load_stylesheet(self, theme_name: str, qss_filename: str) -> str | None:
        if not self._is_safe_filename(qss_filename):
            logger.error(
                "ThemeStylesheetService: unsafe theme file name: %s", qss_filename
            )
            return None

        theme_path = self._app_config.paths.get_qss_dir() / qss_filename
        try:
            qss_dir = self._app_config.paths.get_qss_dir().resolve()
            full_path = theme_path.resolve()
            if not str(full_path).startswith(str(qss_dir)):
                logger.error(
                    "ThemeStylesheetService: attempt to access file outside theme directory: %s",
                    theme_path,
                )
                return None
        except Exception as exc:
            logger.error(
                "ThemeStylesheetService: error checking theme file path %s: %s",
                theme_path,
                exc,
                exc_info=True,
            )
            return None

        cached = self._get_from_cache(theme_name)
        if cached is not None:
            return cached

        if not theme_path.exists():
            logger.error("ThemeStylesheetService: theme file not found: %s", theme_path)
            return None

        try:
            with theme_path.open("r", encoding="utf-8") as fh:
                theme_qss = fh.read()
        except UnicodeDecodeError as exc:
            logger.error(
                "ThemeStylesheetService: error decoding theme file %s: %s",
                theme_name,
                exc,
            )
            return None
        except PermissionError as exc:
            logger.error(
                "ThemeStylesheetService: no access to theme file %s: %s",
                theme_name,
                exc,
            )
            return None
        except OSError as exc:
            logger.error(
                "ThemeStylesheetService: error reading theme %s: %s", theme_name, exc
            )
            return None
        except Exception as exc:
            logger.error(
                "ThemeStylesheetService: unexpected error reading theme %s: %s",
                theme_name,
                exc,
                exc_info=True,
            )
            return None

        common_qss = self._load_common_qss()
        combined_qss = (
            f"{common_qss}\n{theme_qss}" if common_qss is not None else theme_qss
        )

        # ✅ FIX: Use cached overrides
        try:
            overrides = self._get_cached_overrides()
            if overrides:
                combined_qss = f"{combined_qss}\n\n/* ==== AppConfig overrides (auto-generated) ==== */\n{overrides}"
        except Exception as exc:
            logger.warning(
                "ThemeStylesheetService: failed to build QSS overrides from configuration: %s",
                exc,
            )

        with self._cache_lock:
            self._qss_cache[theme_name] = combined_qss
            self._qss_cache.move_to_end(theme_name, last=True)
            self._enforce_cache_limit()

        logger.debug("ThemeStylesheetService: loaded and cached theme: %s", theme_name)
        return combined_qss

    # ---------------------- Internal methods ----------------------
    def _get_from_cache(self, theme_name: str) -> str | None:
        with self._cache_lock:
            if theme_name in self._qss_cache:
                self._qss_cache.move_to_end(theme_name, last=True)
                return self._qss_cache[theme_name]
        return None

    def _load_common_qss(self) -> str | None:
        with self._cache_lock:
            if self._common_qss is not None:
                return self._common_qss

        common_path = self._app_config.paths.get_qss_dir() / "common.qss"
        if not common_path.exists():
            logger.warning(
                "ThemeStylesheetService: common styles file not found: %s", common_path
            )
            with self._cache_lock:
                self._common_qss = ""
            return ""

        try:
            with common_path.open("r", encoding="utf-8") as fh:
                content = fh.read()
            with self._cache_lock:
                self._common_qss = content
            logger.debug(
                "ThemeStylesheetService: loaded common styles from %s", common_path
            )
            return content
        except UnicodeDecodeError as exc:
            logger.error(
                "ThemeStylesheetService: error decoding common styles: %s", exc
            )
        except PermissionError as exc:
            logger.error("ThemeStylesheetService: no access to common styles: %s", exc)
        except OSError as exc:
            logger.error("ThemeStylesheetService: error reading common styles: %s", exc)
        except Exception as exc:
            logger.error(
                "ThemeStylesheetService: unexpected error loading common styles: %s",
                exc,
                exc_info=True,
            )
        with self._cache_lock:
            self._common_qss = ""
        return ""

    def _enforce_cache_limit(self) -> None:
        with self._cache_lock:
            if self._max_cache_size <= 0:
                removed = len(self._qss_cache)
                self._qss_cache.clear()
                if removed:
                    logger.debug(
                        "ThemeStylesheetService: cache disabled, cleared %d entries",
                        removed,
                    )
                return
            while len(self._qss_cache) > self._max_cache_size:
                key, _ = self._qss_cache.popitem(last=False)
                logger.debug("ThemeStylesheetService: LRU removed theme %s", key)

    def _get_cached_overrides(self) -> str:
        """Returns cached QSS overrides.

        ✅ FIX: Caches result of _build_config_overrides_qss().
        """
        with self._cache_lock:
            if self._overrides_cache is not None:
                return self._overrides_cache

        # Generate overrides
        overrides = self._build_config_overrides_qss()

        with self._cache_lock:
            self._overrides_cache = overrides

        return overrides

    def invalidate_overrides_cache(self) -> None:
        """Resets overrides cache when settings change.

        ✅ FIX: Public method to reset cache.

        Call this method after changing font sizes or other UI settings.
        """
        with self._cache_lock:
            self._overrides_cache = None
        logger.debug("ThemeStylesheetService: overrides cache invalidated")

    def _is_safe_filename(self, filename: str) -> bool:
        if not filename or re.search(r'[<>:"/\\|?*]', filename):
            return False
        if ".." in filename or "/" in filename or "\\" in filename:
            return False
        return filename.endswith(".qss")

    def _collect_font_sizes(self) -> dict[str, int | None]:
        """Collect all font sizes from config."""
        app_config = self._app_config

        def _get_font_px(key: str, default: int | None) -> int | None:
            try:
                val = app_config.ui.get(f"ui.fonts.{key}", default)
                return int(val) if val is not None else None
            except Exception:
                return default

        sizes = {
            "table_header_px": _get_font_px("table_header_px", 11),
            "table_row_px": _get_font_px("table_row_px", None),
            "notes_editor_px": _get_font_px("notes_editor_px", None),
            "button_text_px": _get_font_px("button_text_px", None),
            "menubar_px": _get_font_px("menubar_px", None),
            "menu_item_px": _get_font_px("menu_item_px", None),
            "context_menu_px": _get_font_px("context_menu_px", None),
            "bottom_bar_button_px": _get_font_px("bottom_bar_button_px", None),
            "tooltip_px": _get_font_px("tooltip_px", None),
            "tree_px": _get_font_px("tree_px", None),
            "tiles_px": _get_font_px("tiles_px", None),
            "form_label_px": _get_font_px("form_label_px", None),
            "form_field_px": _get_font_px("form_field_px", None),
            "link_type_button_px": _get_font_px("link_type_button_px", None),
        }

        # Apply user font size override
        if self._settings and hasattr(self._settings, "get_font_size"):
            try:
                user_font_size = int(self._settings.get_font_size())
                if 9 <= user_font_size <= 20:
                    sizes["tree_px"] = user_font_size
                    sizes["table_row_px"] = user_font_size
            except Exception:
                pass

        return sizes

    def _collect_menu_params(self) -> dict[str, int | None]:
        """Collect menu-related parameters."""

        def _safe_int(getter, default=None):
            try:
                return int(getter())
            except Exception:
                return default

        app_config = self._app_config
        return {
            "menu_font_size": _safe_int(app_config.ui.get_menu_font_size),
            "menubar_font_size": _safe_int(app_config.ui.get_menubar_font_size),
            "menubar_item_height": _safe_int(app_config.ui.get_menubar_item_height),
            "menu_icon_size": _safe_int(app_config.ui.get_menu_icon_size),
            "menu_indicator_size": _safe_int(app_config.ui.get_menu_indicator_size),
        }

    def _get_fonts_units(self) -> str:
        """Get font units (px or pt)."""
        try:
            units = str(self._app_config.ui.get("ui.fonts.units", "px")).strip().lower()
        except Exception:
            units = "px"
        return units if units in ("px", "pt") else "px"

    def _format_size(self, val: int | None, units: str) -> str | None:
        """Format size value with units."""
        if val is None or int(val) <= 0:
            return None
        return f"{int(val)}{units}"

    def _generate_dialog_styles(self, lines: list[str]) -> None:
        """Generate QDialog font styles."""
        try:
            app = QApplication.instance()
            if app:
                dialog_font_size = app.font().pointSize()
                if dialog_font_size and dialog_font_size > 0:
                    lines.append(f"QDialog {{ font-size: {dialog_font_size}pt; }}")
                    lines.append(f"QDialog * {{ font-size: {dialog_font_size}pt; }}")
        except Exception:
            pass

    def _generate_menu_styles(self, lines: list[str], menu_params: dict) -> None:
        """Generate QMenu styles."""
        menu_font_size = menu_params.get("menu_font_size")
        menu_icon_size = menu_params.get("menu_icon_size")
        menu_indicator_size = menu_params.get("menu_indicator_size")

        if menu_font_size:
            for selector in [
                "QMenu",
                "QMenu::item",
                "QMenu::item:selected",
                "QMenu::item:hover",
                "QMenu::item:pressed",
                "QMenu::item:disabled",
            ]:
                lines.append(f"{selector} {{ font-size: {menu_font_size}pt; }}")

        if menu_icon_size:
            lines.append(
                f"QMenu::icon {{ width: {menu_icon_size}px; height: {menu_icon_size}px; }}"
            )

        if menu_indicator_size:
            lines.append(
                f"QMenu::indicator {{ width: {menu_indicator_size}px; height: {menu_indicator_size}px; }}"
            )

    def _generate_menubar_styles(
        self, lines: list[str], menu_params: dict, sizes: dict, units: str
    ) -> None:
        """Generate QMenuBar styles."""
        menubar_font_size = menu_params.get("menubar_font_size")
        menubar_item_height = menu_params.get("menubar_item_height")
        menubar_px = sizes.get("menubar_px")

        menubar_rules = []
        if menubar_font_size:
            menubar_rules.append(f"font-size: {menubar_font_size}pt;")
        if menubar_px:
            sz_val = self._format_size(menubar_px, units)
            if sz_val:
                menubar_rules.append(f"font-size: {sz_val};")
        if menubar_rules:
            lines.append("QMenuBar { " + " ".join(menubar_rules) + " }")

        item_rules = []
        if menubar_font_size:
            item_rules.append(f"font-size: {menubar_font_size}pt;")
        if menubar_item_height:
            item_rules.append(f"min-height: {menubar_item_height}px;")
        if item_rules:
            rules = " ".join(item_rules)
            for selector in [
                "QMenuBar::item",
                "QMenuBar::item:selected",
                "QMenuBar::item:hover",
                "QMenuBar::item:pressed",
            ]:
                lines.append(f"{selector} {{ {rules} }}")

    def _add_simple_widget_styles(
        self, lines: list[str], sizes: dict, units: str
    ) -> None:
        """Add simple widget styles (one selector per size)."""
        simple_styles = [
            ("table_row_px", "QTableView"),
            ("tree_px", "QTreeView"),
            ("notes_editor_px", "QTextEdit"),
            ("button_text_px", "QPushButton"),
            ("tooltip_px", "QToolTip"),
            ("tiles_px", "QListView#categoryTiles"),
            ("form_label_px", "QLabel"),
        ]

        for size_key, selector in simple_styles:
            if sizes.get(size_key):
                fs = self._format_size(sizes[size_key], units)
                if fs:
                    lines.append(f"{selector} {{ font-size: {fs}; }}")

    def _add_table_header_styles(
        self, lines: list[str], sizes: dict, units: str
    ) -> None:
        """Add table header styles."""
        if sizes.get("table_header_px"):
            fs = self._format_size(sizes["table_header_px"], units)
            if fs:
                lines.append(f"QHeaderView {{ font-size: {fs}; font-weight: normal; }}")
                lines.append(
                    f"QTableView QHeaderView, QTreeView QHeaderView {{ font-size: {fs}; font-weight: normal; }}"
                )
                lines.append(
                    "QHeaderView::section:pressed, QHeaderView::section:hover, QHeaderView::section:checked { font-weight: normal; }"
                )

    def _add_menu_and_form_styles(
        self, lines: list[str], sizes: dict, units: str
    ) -> None:
        """Add menu and form field styles."""
        # Menu item
        if sizes.get("menu_item_px"):
            fs = self._format_size(sizes["menu_item_px"], units)
            if fs:
                lines.append(f"QMenu {{ font-size: {fs}; }}")
                lines.append(f"QMenu::item {{ font-size: {fs}; }}")

        # Context menu
        if sizes.get("context_menu_px"):
            fs = self._format_size(sizes["context_menu_px"], units)
            if fs:
                lines.append(f"QMenu[contextMenuPolicy] {{ font-size: {fs}; }}")

        # Form fields
        if sizes.get("form_field_px"):
            fs = self._format_size(sizes["form_field_px"], units)
            if fs:
                for selector in ["QLineEdit", "QTextEdit", "QComboBox", "QSpinBox"]:
                    lines.append(f"{selector} {{ font-size: {fs}; }}")

    def _add_button_styles(self, lines: list[str], sizes: dict, units: str) -> None:
        """Add button-specific styles."""
        # Bottom bar buttons
        if sizes.get("bottom_bar_button_px"):
            fs = self._format_size(sizes["bottom_bar_button_px"], units)
            if fs:
                lines.append(f"QWidget#BottomPanel QPushButton {{ font-size: {fs}; }}")
                lines.append(
                    f"QWidget#bottomBarContainer PushButton {{ font-size: {fs}; }}"
                )

        # Link type button
        if sizes.get("link_type_button_px"):
            fs = self._format_size(sizes["link_type_button_px"], units)
            if fs:
                lines.append(f'QToolButton[link_type="true"] {{ font-size: {fs}; }}')

    def _add_complex_widget_styles(
        self, lines: list[str], sizes: dict, units: str
    ) -> None:
        """Add complex widget styles (multiple selectors or special cases)."""
        self._add_table_header_styles(lines, sizes, units)
        self._add_menu_and_form_styles(lines, sizes, units)
        self._add_button_styles(lines, sizes, units)

    def _generate_widget_styles(
        self, lines: list[str], sizes: dict, units: str
    ) -> None:
        """Generate styles for various widgets."""
        self._add_simple_widget_styles(lines, sizes, units)
        self._add_complex_widget_styles(lines, sizes, units)

    def _build_config_overrides_qss(self) -> str:
        """Build QSS overrides from config parameters."""
        # Collect parameters
        sizes = self._collect_font_sizes()
        menu_params = self._collect_menu_params()
        units = self._get_fonts_units()

        # Generate styles
        lines: list[str] = []
        self._generate_dialog_styles(lines)
        self._generate_menu_styles(lines, menu_params)
        self._generate_menubar_styles(lines, menu_params, sizes, units)
        self._generate_widget_styles(lines, sizes, units)

        return "\n".join(lines)


def configure_qicon_theme(theme_name: str, app_config) -> None:
    if not theme_name:
        return
    ui_icons_dir = app_config.paths.get_ui_icons_dir()
    if not ui_icons_dir.exists():
        logger.debug(
            "ThemeStylesheetService: UI icons directory missing: %s", ui_icons_dir
        )
        return
    theme_dir = ui_icons_dir / theme_name
    if not theme_dir.exists():
        fallback = "light"
        fallback_dir = ui_icons_dir / fallback
        if fallback_dir.exists():
            logger.warning(
                "ThemeStylesheetService: icon theme '%s' not found, using fallback '%s'",
                theme_name,
                fallback,
            )
            theme_name = fallback
        else:
            logger.warning(
                "ThemeStylesheetService: icon theme directory not found: %s, fallback 'light' also missing",
                theme_dir,
            )
    search_paths = [str(ui_icons_dir)]
    try:
        current_paths = QIcon.themeSearchPaths()
        for path in current_paths:
            if path not in search_paths:
                search_paths.append(path)
    except Exception as exc:
        logger.debug(
            "ThemeStylesheetService: failed to get current QIcon theme search paths: %s",
            exc,
            exc_info=True,
        )
    QIcon.setThemeSearchPaths(search_paths)
    QIcon.setThemeName(theme_name)
