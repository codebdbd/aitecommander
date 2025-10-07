import logging
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.utils.ui.icon.cache_manager import clear_icon_cache
from app.services.theme_stylesheet_service import (
    ThemeStylesheetService,
    configure_qicon_theme,
)

logger = logging.getLogger(__name__)


class ThemeController:
    # Application shutdown policy:
    # - UI layer does not call quit()/exit() directly.
    # - Bulk UI update after theme change is performed without closing the application;
    #   shutdown, if required, is delegated to AppShutdownController via window close.
    def __init__(
        self,
        settings,
        main_window=None,
        stylesheet_applier: Optional[callable] = None,
        gui_scheduler: Optional[callable] = None,
        *,
        top_panels_controller: Optional[Any] = None,
        stylesheet_service: Optional[ThemeStylesheetService] = None,
    ):
        """Initialize theme controller."""
        self.settings = settings
        self.main_window = main_window
        # TopPanelsController can be injected later via set_top_panels_controller()
        self.top_panels_controller = top_panels_controller
        self._themes: List[Dict[str, Any]] = []
        self._stylesheet_service = stylesheet_service or ThemeStylesheetService(
            app_config, settings=settings
        )
        # Dependency injection for testability
        self._stylesheet_applier = stylesheet_applier  # Callable[[str], None]
        self._gui_scheduler = gui_scheduler  # Callable[[Callable[[], None]], None]
        # Note: reentrancy protection is not used — restoring original behavior

        # Themes are fixed (light/dark)
        self._init_fixed_themes()

    # Custom shadows for QMenu removed; no event filters applied

    def set_top_panels_controller(self, top_panels_controller) -> None:
        """Inject TopPanelsController dependency.

        Can be called after ThemeController initialization when
        TopPanelsController becomes available. Raises ValueError
        if dependency is not provided or invalid.
        """
        if top_panels_controller is None:
            raise ValueError("TopPanelsController must be provided to ThemeController")
        self.top_panels_controller = top_panels_controller

    def _normalize_theme_input(self, name: Optional[str]) -> str:
        """Normalize theme name: trim spaces, convert to lowercase,
        map known synonyms to canonical names (e.g. Russian variants)."""
        if not name:
            return ""
        v = str(name).strip().lower()
        # Small synonym table
        synonyms = {
            "темная": "dark",
            "тёмная": "dark",
            "темный": "dark",
            "тёмный": "dark",
            "dark": "dark",
            "светлая": "light",
            "light": "light",
        }
        return synonyms.get(v, v)

    def _init_fixed_themes(self) -> None:
        """Initialize fixed theme list."""
        self._themes = [
            {
                "name": "light",
                "display_name": "Светлая",
                "qss_file": "light.qss",
                "is_dark": False,
            },
            {
                "name": "dark",
                "display_name": "Тёмная",
                "qss_file": "dark.qss",
                "is_dark": True,
            },
        ]

    def is_dark(self) -> bool:
        """Check if current theme is dark."""
        try:
            current_theme = self.settings.get_theme()
            if not current_theme:
                logger.warning(
                    "Current theme not set, using light theme by default"
                )
                return False
            # Normalize name and try to find config
            norm = self._normalize_theme_input(current_theme)
            theme_config = self._get_theme_by_name(norm)
            if theme_config:
                return theme_config.get("is_dark", False)
            # If theme not found in config, determine by normalized name
            return norm == "dark"
        except Exception as exc:
            logger.error("Error determining dark theme: %s", exc, exc_info=True)
            return False

    def _get_theme_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get theme dictionary by name (case insensitive)."""
        if not name:
            return None
        name_lc = str(name).lower()
        return next(
            (
                theme
                for theme in self._themes
                if str(theme.get("name", "")).lower() == name_lc
            ),
            None,
        )

    def available(self) -> List[Tuple[str, str]]:
        """Get list of available themes."""
        try:
            if not self._themes:
                logger.warning("Theme list is empty, returning default themes")
                return [("light", "Светлая"), ("dark", "Тёмная")]
            result: List[Tuple[str, str]] = []
            for theme in self._themes:
                name = theme.get("name")
                if not name:
                    # Skip invalid entries
                    logger.warning("Skipped theme without name in configuration")
                    continue
                display_name = theme.get("display_name")
                if not display_name:
                    # Fallback for known themes, otherwise pretty name
                    if name == "light":
                        display_name = "Светлая"
                    elif name == "dark":
                        display_name = "Тёмная"
                    else:
                        display_name = str(name).replace("_", " ").title()
                    logger.warning(
                        "Theme '%s' has no display_name in configuration, using default value: %s",
                        name,
                        display_name,
                    )
                result.append((name, display_name))
            return result
        except Exception as exc:
            logger.error("Error getting theme list: %s", exc, exc_info=True)
            # Return default themes on error
            return [("light", "Светлая"), ("dark", "Тёмная")]

    def apply(self, name: str) -> bool:
        """Apply theme by name and save to settings."""
        normalized_name = self._normalize_theme_input(name)
        theme_config = self._get_theme_by_name(normalized_name)
        if not theme_config:
            logger.error("Theme not found: %s", name)
            return False
        qss_file = theme_config.get("qss_file")
        if not qss_file:
            logger.error("QSS file not specified for theme: %s", name)
            return False

        # Cache and search by canonical name to avoid duplicate keys
        canonical_name = theme_config.get("name", normalized_name)
        # IMPORTANT: invalidate common/theme QSS cache before loading,
        # to ensure style file changes (especially common.qss) are picked up
        # without application restart. Safe: cache will restore on read below.
        self.clear_cache()
        qss_content = self._stylesheet_service.load_stylesheet(canonical_name, qss_file)
        if qss_content is None:
            logger.error("Failed to load QSS for theme: %s", name)
            return False

        try:
            # Apply QSS
            if self._stylesheet_applier is not None:
                self._stylesheet_applier(qss_content)
            else:
                app = QApplication.instance()
                if not app:
                    logger.error("QApplication instance not found")
                    return False
                app.setStyleSheet(qss_content)

            # Custom menu shadows fully disabled — doing nothing

            # Initialize Qt icon theme
            try:
                configure_qicon_theme(canonical_name, app_config)
            except Exception as icon_exc:
                logger.warning(
                    "Failed to apply Qt icon theme: %s", icon_exc, exc_info=True
                )

            # Update settings and window (restore original update_theme call)
            logger.info("Applied theme: %s", canonical_name)
            self.settings.set_theme(canonical_name)
            if self.main_window and hasattr(self.main_window, "update_theme"):
                self.main_window.update_theme()
            return True
        except Exception as exc:
            logger.error("Theme application error %s: %s", name, exc, exc_info=True)
            return False

    def clear_cache(self) -> None:
        """Clear QSS cache."""
        self._stylesheet_service.clear_cache()

    def apply_and_refresh_ui(self) -> None:
        """Centralized UI update after theme application.

        Performs:
        - Clear icon cache
        - Rebuild main menu
        - Reload structure tree icons
        - Update top panels (Favorites/Recent)

        All bulk operations run with suspended main window repaint
        to avoid visual flicker of panel sizes.
        """
        logger.info(
            "ThemeController: batch UI update after theme change: menu → structure icons → top panels"
        )
        try:
            clear_icon_cache()
        except Exception as exc:
            logger.warning("Failed to clear icon cache: %s", exc, exc_info=True)

        mw = getattr(self, "main_window", None)
        if not mw:
            return

        # Lazy import to avoid circular imports on startup
        try:
            from app.utils.ui.updates import suspend_updates
        except Exception as exc:
            suspend_updates = None  # fallback if module unavailable
            logger.debug(
                "Failed to import suspend_updates: %s", exc, exc_info=True
            )

        # Policy: require suspend_updates for batch UI update
        try:
            require_suspend = bool(getattr(app_config, "REQUIRE_SUSPEND_UPDATES", False))
        except Exception:
            require_suspend = False

        if suspend_updates is None:
            if require_suspend:
                logger.warning(
                    "ThemeController: require_suspend_updates=True, but suspend_updates utility unavailable — skipping batch UI update"
                )
                return
            # Fallback: execute operations without suspended repaint
            try:
                menu_ctrl = getattr(mw, "menu_controller", None)
                if menu_ctrl:
                    menu_ctrl.rebuild_after_theme_change()
            except Exception as exc:
                logger.warning(
                    "Menu rebuild error after theme change: %s", exc, exc_info=True
                )
            try:
                structure = getattr(mw, "structure", None)
                if structure and hasattr(structure, "reload_icons"):
                    structure.reload_icons()
            except Exception as exc:
                logger.warning(
                    "Structure icons reload error: %s", exc, exc_info=True
                )
            try:
                self.top_panels_controller.refresh_all()
            except Exception as exc:
                logger.warning(
                    "Error updating top panels: %s", exc, exc_info=True
                )
            return

        # Main path: execute bulk updates with suspended window repaint
        if require_suspend:
            logger.debug("ThemeController: executing batch UI update with suspend_updates (strict mode)")
        try:
            with suspend_updates(mw):
                # Rebuild main menu
                try:
                    menu_ctrl = getattr(mw, "menu_controller", None)
                    if menu_ctrl:
                        menu_ctrl.rebuild_after_theme_change()
                except Exception as exc:
                    logger.warning(
                        "Menu rebuild error after theme change: %s",
                        exc,
                        exc_info=True,
                    )

                # Reload icons in structure
                try:
                    structure = getattr(mw, "structure", None)
                    if structure and hasattr(structure, "reload_icons"):
                        structure.reload_icons()
                except Exception as exc:
                    logger.warning(
                        "Structure icons reload error: %s", exc, exc_info=True
                    )

                # Update top panels — direct dependency from constructor
                try:
                    self.top_panels_controller.refresh_all()
                except Exception as exc:
                    logger.warning(
                        "Top panels update error: %s", exc, exc_info=True
                    )
        except Exception as exc:
            logger.warning(
                "ThemeController: batch UI update failure: %s",
                exc,
                exc_info=True,
            )

        # Don't reset font sizes on theme change.
        # Base app size and specific sizes for menu/menubar are managed separately,
        # and user-set tree/table sizes should not be affected by theme.

    def _apply_qt_icon_theme(self, theme_name: str) -> None:
        """Set Qt icon theme and search paths for correct standard icon display.
        Must be executed in GUI thread before showing first menus/dialogs."""
        if not theme_name:
            return
        # Build search paths: app UI icons as Qt theme
        ui_icons_dir = app_config.paths.get_ui_icons_dir()
        if not ui_icons_dir.exists():
            logger.debug("UI icons dir does not exist: %s", ui_icons_dir)
            return
        # Check theme directory exists, otherwise use fallback 'light'
        theme_dir = ui_icons_dir / theme_name
        if not theme_dir.exists():
            fallback = "light"
            fallback_dir = ui_icons_dir / fallback
            if fallback_dir.exists():
                logger.warning(
                    "Icon theme '%s' not found, using fallback '%s'",
                    theme_name,
                    fallback,
                )
                theme_name = fallback
            else:
                logger.warning(
                    "Icon theme directory not found: %s, fallback 'light' also missing",
                    theme_dir,
                )
        search_paths = [str(ui_icons_dir)]
        try:
            # Add existing search paths to preserve system ones
            current_paths = QIcon.themeSearchPaths()
            for p in current_paths:
                if p not in search_paths:
                    search_paths.append(p)
        except Exception as exc:
            logger.debug(
                "Failed to get current QIcon theme search paths: %s",
                exc,
                exc_info=True,
            )
        QIcon.setThemeSearchPaths(search_paths)
        # Theme name is canonical name, expecting subdirectory ui_icons_dir/<theme_name>
        QIcon.setThemeName(theme_name)

    def _build_config_overrides_qss(self) -> str:
        """Build QSS block with config parameters to override theme values.

        Returns QSS string. Empty string if nothing to override.
        """
        try:
            menu_font_size = int(app_config.ui.get_menu_font_size())
        except Exception:
            menu_font_size = None
        try:
            menubar_font_size = int(app_config.ui.get_menubar_font_size())
        except Exception:
            menubar_font_size = None
        try:
            menubar_item_height = int(app_config.ui.get_menubar_item_height())
        except Exception:
            menubar_item_height = None
        try:
            menu_icon_size = int(app_config.ui.get_menu_icon_size())
        except Exception:
            menu_icon_size = None
        try:
            menu_indicator_size = int(app_config.ui.get_menu_indicator_size())
        except Exception:
            menu_indicator_size = None
        # Unified font registry from config (ui.fonts.*)
        def _get_font_px(key: str, default: int | None) -> int | None:
            try:
                # IMPORTANT: UIConfig keys must start with 'ui.'
                val = app_config.ui.get(f"ui.fonts.{key}", default)
                return int(val) if val is not None else None
            except Exception:
                return default

        table_header_px = _get_font_px("table_header_px", 11)
        table_row_px = _get_font_px("table_row_px", None)
        notes_editor_px = _get_font_px("notes_editor_px", None)
        button_text_px = _get_font_px("button_text_px", None)
        menubar_px = _get_font_px("menubar_px", None)
        menu_item_px = _get_font_px("menu_item_px", None)
        context_menu_px = _get_font_px("context_menu_px", None)
        bottom_bar_button_px = _get_font_px("bottom_bar_button_px", None)
        tooltip_px = _get_font_px("tooltip_px", None)
        tree_px = _get_font_px("tree_px", None)
        tiles_px = _get_font_px("tiles_px", None)
        form_label_px = _get_font_px("form_label_px", None)
        form_field_px = _get_font_px("form_field_px", None)
        link_type_button_px = _get_font_px("link_type_button_px", None)

        # Global font unit: 'px' (default) or 'pt'
        try:
            fonts_units = str(app_config.ui.get("ui.fonts.units", "px")).strip().lower()
        except Exception:
            fonts_units = "px"
        if fonts_units not in ("px", "pt"):
            fonts_units = "px"

        def sz(val: int | None) -> str | None:
            if val is None or int(val) <= 0:
                return None
            return f"{int(val)}{fonts_units}"

        lines = []

        # Dialogs: force system (Qt default) app font size
        # to avoid unwanted changes from themes/styles. Does not change font family.
        try:
            app = QApplication.instance()
            dialog_font_size = app.font().pointSize() if app else None
        except Exception:
            dialog_font_size = None
        if dialog_font_size and dialog_font_size > 0:
            # Propagate to dialog content so nested widgets don't override accidentally
            lines.append(f"QDialog {{ font-size: {dialog_font_size}pt; }}")
            lines.append(f"QDialog * {{ font-size: {dialog_font_size}pt; }}")

        # Menu (QMenu)
        if menu_font_size:
            # Use pt to match global app font and DPI
            lines.append(f"QMenu {{ font-size: {menu_font_size}pt; }}")
            # Apply font size to all menu item states to override theme states
            lines.append(f"QMenu::item {{ font-size: {menu_font_size}pt; }}")
            lines.append(f"QMenu::item:selected {{ font-size: {menu_font_size}pt; }}")
            lines.append(f"QMenu::item:hover {{ font-size: {menu_font_size}pt; }}")
            lines.append(f"QMenu::item:pressed {{ font-size: {menu_font_size}pt; }}")
            lines.append(f"QMenu::item:disabled {{ font-size: {menu_font_size}pt; }}")

        if menu_icon_size:
            # set both width and height; padding-left already defined in common
            lines.append(
                f"QMenu::icon {{ width: {menu_icon_size}px; height: {menu_icon_size}px; }}"
            )

        if menu_indicator_size:
            lines.append(
                f"QMenu::indicator {{ width: {menu_indicator_size}px; height: {menu_indicator_size}px; }}"
            )

        # Menubar (QMenuBar)
        menubar_rules = []
        if menubar_font_size:
            # Also use pt to match system scale
            menubar_rules.append(f"font-size: {menubar_font_size}pt;")
        if menubar_px:
            menubar_rules.append(f"font-size: {sz(menubar_px)};")
        if menubar_rules:
            lines.append("QMenuBar { " + " ".join(menubar_rules) + " }")
        item_rules = []
        if menubar_font_size:
            item_rules.append(f"font-size: {menubar_font_size}pt;")
        if menubar_item_height:
            item_rules.append(f"min-height: {menubar_item_height}px;")
        if item_rules:
            # Base rule for menubar item
            lines.append("QMenuBar::item { " + " ".join(item_rules) + " }")
            # Duplicate for states to avoid theme override
            if menubar_font_size or menubar_item_height:
                lines.append("QMenuBar::item:selected { " + " ".join(item_rules) + " }")
                lines.append("QMenuBar::item:hover { " + " ".join(item_rules) + " }")
                lines.append("QMenuBar::item:pressed { " + " ".join(item_rules) + " }")
        
        # Table/tree headers (QHeaderView): final font size override
        if table_header_px and table_header_px > 0:
            fs = sz(table_header_px)
            lines.append(f"QHeaderView {{ font-size: {fs}; font-weight: normal; }}")
            lines.append(f"QTableView QHeaderView, QTreeView QHeaderView {{ font-size: {fs}; font-weight: normal; }}")
            # Don't force bold in interactive states
            lines.append(
                "QHeaderView::section:pressed, QHeaderView::section:hover, QHeaderView::section:checked { font-weight: normal; }"
            )

        # Table rows by default
        if table_row_px and table_row_px > 0:
            lines.append(f"QTableView {{ font-size: {sz(table_row_px)}; }}")

        # Tree (QTreeView)
        if tree_px and tree_px > 0:
            lines.append(f"QTreeView {{ font-size: {sz(tree_px)}; }}")

        # Notes editor text (QTextEdit)
        if notes_editor_px and notes_editor_px > 0:
            lines.append(f"QTextEdit {{ font-size: {sz(notes_editor_px)}; }}")

        # Buttons (including bottom panel)
        if button_text_px and button_text_px > 0:
            lines.append(f"QPushButton {{ font-size: {sz(button_text_px)}; }}")
        if bottom_bar_button_px and bottom_bar_button_px > 0:
            # Increase specificity for bottom panel: support both container names
            fsb = sz(bottom_bar_button_px)
            lines.append(f"QWidget#BottomPanel QPushButton {{ font-size: {fsb}; }}")
            lines.append(f"QWidget#bottomBarContainer QPushButton {{ font-size: {fsb}; }}")

        # Main menu and dropdown menus
        if menu_item_px and menu_item_px > 0:
            fs = sz(menu_item_px)
            lines.append(f"QMenu {{ font-size: {fs}; }}")
            lines.append(f"QMenu::item {{ font-size: {fs}; }}")
        if context_menu_px and context_menu_px > 0:
            # Context menus are also QMenu; separate key allows distinction if needed
            lines.append(f"QMenu[contextMenuPolicy] {{ font-size: {sz(context_menu_px)}; }}")

        # Tooltips (ToolTip)
        if tooltip_px and tooltip_px > 0:
            lines.append(f"QToolTip {{ font-size: {sz(tooltip_px)}; }}")
        # Category tiles (QListView#categoryTiles)
        if tiles_px and tiles_px > 0:
            lines.append(f"QListView#categoryTiles {{ font-size: {sz(tiles_px)}; }}")
        # Form labels and fields (dialogs and forms)
        if form_label_px and form_label_px > 0:
            fs = sz(form_label_px)
            lines.append(f"QLabel {{ font-size: {fs}; }}")
        if form_field_px and form_field_px > 0:
            fs = sz(form_field_px)
            lines.append(f"QLineEdit {{ font-size: {fs}; }}")
            lines.append(f"QTextEdit {{ font-size: {fs}; }}")
            lines.append(f"QComboBox {{ font-size: {fs}; }}")
            lines.append(f"QSpinBox {{ font-size: {fs}; }}")
        # Link type selection buttons (QToolButton with property link_type)
        if link_type_button_px and link_type_button_px > 0:
            fs = sz(link_type_button_px)
            lines.append(f"QToolButton[link_type=\"true\"] {{ font-size: {fs}; }}")
        return "\n".join(lines)
        
        # Note: code below won't execute due to early return; preserved for future

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return theme cache statistics."""
        with self._cache_lock:
            return {
                "cache_size": len(self._qss_cache),
                "max_size": self._max_cache_size,
                "cached_themes": list(self._qss_cache.keys()),
                "common_qss_loaded": self._common_qss is not None,
            }
