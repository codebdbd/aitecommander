import logging
import threading
from pathlib import Path
from typing import Any, Callable, Optional, cast

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QThread
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.services.theme_stylesheet_service import (
    ThemeStylesheetService,
    configure_qicon_theme,
)
from app.utils.ui.icon.cache_manager import clear_icon_cache

logger = logging.getLogger(__name__)

# Ensure lupdate picks up theme names defined via QT_TRANSLATE_NOOP.
if False:  # pragma: no cover
    QCoreApplication.translate("ThemeController", "Light")
    QCoreApplication.translate("ThemeController", "Dark")


class ThemeController:
    # Application shutdown policy:
    # - UI layer does not call quit()/exit() directly.
    # - Bulk UI update after theme change is performed without closing the application;
    #   shutdown, if required, is delegated to AppShutdownController via window close.
    def __init__(
        self,
        settings,
        main_window=None,
        stylesheet_applier: Optional[Callable] = None,
        gui_scheduler: Optional[Callable] = None,
        *,
        top_panels_controller: Optional[Any] = None,
        stylesheet_service: Optional[ThemeStylesheetService] = None,
    ):
        """Initialize theme controller."""
        self.settings = settings
        self.main_window = main_window
        # TopPanelsController can be injected later via set_top_panels_controller()
        self.top_panels_controller = top_panels_controller
        self._themes: list[dict[str, Any]] = []
        self._stylesheet_service = stylesheet_service or ThemeStylesheetService(
            app_config, settings=settings
        )
        # Dependency injection for testability
        self._stylesheet_applier = stylesheet_applier  # Callable[[str], None]
        self._gui_scheduler = gui_scheduler  # Callable[[Callable[[], None]], None]
        # Initialize cache attributes for get_cache_stats method
        self._cache_lock = threading.Lock()
        self._qss_cache: dict[str, Any] = {}
        self._max_cache_size = 100
        self._common_qss: Optional[str] = None
        # Note: reentrancy protection is not used - restoring original behaviort_cache_stats method

        self._load_available_themes()

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
            "dark": "dark",
            "\u0442\u0435\u043c\u043d\u0430\u044f": "dark",
            "\u0442\u0451\u043c\u043d\u0430\u044f": "dark",
            "\u0442\u0435\u043c\u043d\u044b\u0439": "dark",
            "\u0442\u0451\u043c\u043d\u044b\u0439": "dark",
            "\u0442\u0435\u043c\u043d\u0430": "dark",
            "\u0442\u0435\u043c\u043d\u0435": "dark",
            "\u0442\u0435\u043c\u043d\u0438\u0439": "dark",
            "\u0442\u0435\u043c\u043d\u0430\u044f \u0442\u0435\u043c\u0430": "dark",
            "\u0442\u0435\u043c\u043d\u0430 \u0442\u0435\u043c\u0430": "dark",
            "dark theme": "dark",
            "light": "light",
            "\u0441\u0432\u0435\u0442\u043b\u0430\u044f": "light",
            "\u0441\u0432\u0435\u0442\u043b\u044b\u0439": "light",
            "\u0441\u0432\u0435\u0442\u043b\u0430\u044f \u0442\u0435\u043c\u0430": "light",
            "\u0441\u0432\u0435\u0442\u043b\u0430 \u0442\u0435\u043c\u0430": "light",
            "\u0441\u0432\u0456\u0442\u043b\u0430": "light",
            "\u0441\u0432\u0456\u0442\u043b\u0438\u0439": "light",
            "\u0441\u0432\u0456\u0442\u043b\u0430 \u0442\u0435\u043c\u0430": "light",
            "light theme": "light",
        }
        return synonyms.get(v, v)

    def _load_available_themes(self) -> None:
        """Populate theme list from QSS directory with safe fallbacks."""
        detected: list[dict[str, Any]] = []

        try:
            themes_dir = app_config.paths.get_qss_dir()
        except Exception as exc:
            logger.error(
                "ThemeController: failed to resolve QSS directory: %s",
                exc,
                exc_info=True,
            )
            themes_dir = None

        if themes_dir:
            try:
                directory = Path(themes_dir)
                for qss_file in sorted(
                    directory.glob("*.qss"), key=lambda p: p.name.lower()
                ):
                    if qss_file.name.lower() == "common.qss":
                        continue
                    theme_name = qss_file.stem.lower()
                    display_name, context = self._resolve_display_metadata(theme_name)
                    detected.append(
                        {
                            "name": theme_name,
                            "display_name": display_name,
                            "display_context": context,
                            "qss_file": qss_file.name,
                            "is_dark": self._infer_is_dark(theme_name),
                        }
                    )
            except Exception as exc:
                logger.warning(
                    "ThemeController: failed to auto-detect themes: %s",
                    exc,
                    exc_info=True,
                )

        if not detected:
            logger.info("ThemeController: falling back to default theme list")
            detected = self._default_theme_entries()

        self._themes = detected

    def _resolve_display_metadata(self, theme_name: str) -> tuple[str, str]:
        """Return display name and translation context for theme."""
        canonical = theme_name.lower()
        if canonical == "light":
            return (QT_TRANSLATE_NOOP("ThemeController", "Light"), "ThemeController")
        if canonical == "dark":
            return (QT_TRANSLATE_NOOP("ThemeController", "Dark"), "ThemeController")

        humanized = canonical.replace("_", " ").strip()
        if not humanized:
            humanized = "Theme"
        return (humanized.title(), "ThemeController")

    def _infer_is_dark(self, theme_name: str) -> bool:
        """Best-effort detection for dark themes based on name."""
        lowered = theme_name.lower()
        if lowered == "dark":
            return True
        markers = ("dark", "night", "noir", "black")
        return any(marker in lowered for marker in markers)

    def _default_theme_entries(self) -> list[dict[str, Any]]:
        """Return built-in fallback theme list."""
        return [
            {
                "name": "light",
                "display_name": QT_TRANSLATE_NOOP("ThemeController", "Light"),
                "display_context": "ThemeController",
                "qss_file": "light.qss",
                "is_dark": False,
            },
            {
                "name": "dark",
                "display_name": QT_TRANSLATE_NOOP("ThemeController", "Dark"),
                "display_context": "ThemeController",
                "qss_file": "dark.qss",
                "is_dark": True,
            },
        ]

    def is_dark(self) -> bool:
        """Check if current theme is dark."""
        try:
            current_theme = self.settings.get_theme()
            if not current_theme:
                logger.warning("Current theme not set, using light theme by default")
                return False
            # Normalize name and try to find config
            norm = self._normalize_theme_input(current_theme)
            theme_config = self._get_theme_by_name(norm)
            if theme_config:
                return bool(
                    theme_config.get("is_dark", self._infer_is_dark(norm))
                )
            # If theme not found in config, determine heuristically
            return self._infer_is_dark(norm)
        except Exception as exc:
            logger.error("Error determining dark theme: %s", exc, exc_info=True)
            return False

    def _get_theme_by_name(self, name: str) -> Optional[dict[str, Any]]:
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

    def available(self) -> list[tuple[str, str]]:
        """Get list of available themes."""
        try:
            if not self._themes:
                logger.warning("Theme list is empty, returning default themes")
                # Return theme identifiers that can be translated via QCoreApplication.translate
                return [("light", "light"), ("dark", "dark")]
            result: list[tuple[str, str]] = []
            for theme in self._themes:
                name = theme.get("name")
                if not name:
                    # Skip invalid entries
                    logger.warning("Skipped theme without name in configuration")
                    continue
                display_name = theme.get("display_name")
                context = theme.get("display_context", "ThemeController")
                if not display_name:
                    # Fallback for known themes, return theme identifier for translation
                    if name == "light":
                        display_name = "light"
                    elif name == "dark":
                        display_name = "dark"
                    else:
                        display_name = str(name).replace("_", " ").title()
                    logger.warning(
                        "Theme '%s' has no display_name in configuration, using default value: %s",
                        name,
                        display_name,
                    )
                translated_name = (
                    QCoreApplication.translate(context, display_name)
                    if isinstance(display_name, str)
                    else str(display_name)
                )
                result.append((name, translated_name))
            return result
        except Exception as exc:
            logger.error("Error getting theme list: %s", exc, exc_info=True)
            # Return default theme identifiers on error
            return [("light", "light"), ("dark", "dark")]

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

        app_instance = QApplication.instance()
        if app_instance and QThread.currentThread() is not app_instance.thread():
            logger.error("ThemeController.apply must be called from the GUI thread")
            return False

        try:
            # Apply QSS
            if self._stylesheet_applier is not None:
                self._stylesheet_applier(qss_content)
            else:
                if not app_instance:
                    logger.error("QApplication instance not found")
                    return False
                app = cast(QApplication, app_instance)
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

    def _clear_icon_cache_safe(self) -> None:
        """Clear icon cache with error handling."""
        try:
            clear_icon_cache()
        except Exception as exc:
            logger.warning("Failed to clear icon cache: %s", exc, exc_info=True)

    def _get_suspend_updates_utility(self):
        """Get suspend_updates utility with lazy import."""
        try:
            from app.utils.ui.updates import suspend_updates

            return suspend_updates
        except Exception as exc:
            logger.debug("Failed to import suspend_updates: %s", exc, exc_info=True)
            return None

    def _should_require_suspend(self) -> bool:
        """Check if suspend_updates is required by config."""
        try:
            return bool(getattr(app_config, "REQUIRE_SUSPEND_UPDATES", False))
        except Exception:
            return False

    def _rebuild_menu(self, mw) -> None:
        """Rebuild main menu after theme change."""
        try:
            menu_ctrl = getattr(mw, "menu_controller", None)
            if menu_ctrl:
                menu_ctrl.rebuild_after_theme_change()
        except Exception as exc:
            logger.warning(
                "Menu rebuild error after theme change: %s", exc, exc_info=True
            )

    def _reload_structure_icons(self, mw) -> None:
        """Reload structure tree icons."""
        try:
            structure = getattr(mw, "structure", None)
            if structure and hasattr(structure, "reload_icons"):
                structure.reload_icons()
        except Exception as exc:
            logger.warning("Structure icons reload error: %s", exc, exc_info=True)

    def _refresh_top_panels(self) -> None:
        """Refresh top panels (Favorites/Recent)."""
        try:
            if self.top_panels_controller is not None:
                self.top_panels_controller.refresh_all()
        except Exception as exc:
            logger.warning("Top panels update error: %s", exc, exc_info=True)

    def _perform_ui_updates(self, mw) -> None:
        """Perform all UI updates (menu, structure, panels)."""
        self._rebuild_menu(mw)
        self._reload_structure_icons(mw)
        self._refresh_top_panels()

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

        # Clear icon cache
        self._clear_icon_cache_safe()

        # Check if main window exists
        mw = getattr(self, "main_window", None)
        if not mw:
            return

        app_instance = QApplication.instance()
        if app_instance and QThread.currentThread() is not app_instance.thread():
            logger.error(
                "ThemeController.apply_and_refresh_ui must be called from the GUI thread"
            )
            return

        # Get suspend_updates utility
        suspend_updates = self._get_suspend_updates_utility()
        require_suspend = self._should_require_suspend()

        # Handle case when suspend_updates is unavailable
        if suspend_updates is None:
            if require_suspend:
                logger.warning(
                    "ThemeController: require_suspend_updates=True, but suspend_updates utility unavailable — skipping batch UI update"
                )
                return
            # Fallback: execute without suspended repaint
            self._perform_ui_updates(mw)
            return

        # Main path: execute with suspended window repaint
        if require_suspend:
            logger.debug(
                "ThemeController: executing batch UI update with suspend_updates (strict mode)"
            )

        try:
            with suspend_updates(mw):
                self._perform_ui_updates(mw)
        except Exception as exc:
            logger.warning(
                "ThemeController: batch UI update failure: %s",
                exc,
                exc_info=True,
            )

        # Don't reset font sizes on theme change.
        # Base app size and specific sizes for menu/menubar are managed separately,
        # and user-set tree/table sizes should not be affected by theme.

    def _build_config_overrides_qss(self) -> str:
        """Build QSS block with config parameters to override theme values.

        Returns QSS string. Empty string if nothing to override.

        Delegates to ThemeStylesheetService for actual implementation.
        """
        return self._stylesheet_service._build_config_overrides_qss()

    def get_cache_stats(self) -> dict[str, Any]:
        """Return theme cache statistics."""
        with self._cache_lock:
            return {
                "cache_size": len(self._qss_cache),
                "max_size": self._max_cache_size,
                "cached_themes": list(self._qss_cache.keys()),
                "common_qss_loaded": self._common_qss is not None,
            }
