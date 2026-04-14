import logging
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, QThread
from PyQt6.QtWidgets import QApplication

from app.config_data.runtime_config import get_runtime_app_config
from app.core.paths.path_manager import PathManager
from app.core.settings_manager import SettingsManager
from app.core.style_manager import StyleManager
from app.services.theme_registry import theme_registry
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
        self._theme_registry = theme_registry
        self._stylesheet_service = stylesheet_service or ThemeStylesheetService(
            get_runtime_app_config(), settings=settings
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
        """Populate theme list from ThemeRegistry."""
        detected: list[dict[str, Any]] = []
        try:
            for theme in self._theme_registry.list_themes():
                display_name, context = self._resolve_display_metadata(
                    theme.theme_id, theme.name
                )
                detected.append(
                    {
                        "name": theme.theme_id,
                        "display_name": display_name,
                        "display_context": context,
                        "qss_path": theme.qss_path,
                        "is_dark": bool(theme.is_dark),
                        "source": theme.source,
                    }
                )
        except Exception as exc:
            logger.warning(
                "ThemeController: failed to load themes from registry: %s",
                exc,
                exc_info=True,
            )

        if not detected:
            logger.info("ThemeController: falling back to default theme list")
            detected = self._default_theme_entries()

        self._themes = detected

    def _resolve_display_metadata(self, theme_id: str, name: str) -> tuple[str, str]:
        """Return display name and translation context for theme."""
        canonical = theme_id.lower()
        if canonical == "light":
            return (QT_TRANSLATE_NOOP("ThemeController", "Light"), "ThemeController")
        if canonical == "dark":
            return (QT_TRANSLATE_NOOP("ThemeController", "Dark"), "ThemeController")

        humanized = name.strip() if name else canonical.replace("_", " ").strip()
        if not humanized:
            humanized = "Theme"
        return (humanized, "ThemeController")

    def _infer_is_dark(self, theme_name: str) -> bool:
        """Best-effort detection for dark themes based on name."""
        lowered = theme_name.lower()
        if lowered == "dark":
            return True
        explicit_dark = {"matrix", "violet_pulse"}
        if lowered in explicit_dark:
            return True
        markers = ("dark", "night", "noir", "black")
        return any(marker in lowered for marker in markers)

    def _default_theme_entries(self) -> list[dict[str, Any]]:
        """Return built-in fallback theme list."""
        qss_dir = PathManager.qss_dir()
        return [
            {
                "name": "light",
                "display_name": QT_TRANSLATE_NOOP("ThemeController", "Light"),
                "display_context": "ThemeController",
                "qss_path": qss_dir / "light.qss",
                "is_dark": False,
                "source": "bundled",
            },
            {
                "name": "dark",
                "display_name": QT_TRANSLATE_NOOP("ThemeController", "Dark"),
                "display_context": "ThemeController",
                "qss_path": qss_dir / "dark.qss",
                "is_dark": True,
                "source": "bundled",
            },
        ]

    def _apply_saved_theme(self) -> None:
        saved_theme = SettingsManager.get("theme.name")
        if not saved_theme:
            return
        if QApplication.instance() is None:
            logger.debug("ThemeController: QApplication not ready for saved theme")
            return
        try:
            self.apply(str(saved_theme))
        except Exception as exc:
            logger.warning(
                "ThemeController: failed to apply saved theme: %s", exc, exc_info=True
            )

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
        canonical_name, theme_config = self._resolve_theme_config(name, normalized_name)
        if theme_config is None:
            return False

        # Invalidate cache before load
        self.clear_cache()

        qss_content = self._load_qss_content(canonical_name, theme_config)
        if qss_content is None:
            logger.error("Failed to load composed QSS for theme: %s", name)
            return False

        if not self._validate_gui_thread():
            return False

        if not StyleManager.apply_qss_string(qss_content):
            logger.error("Failed to apply theme via StyleManager: %s", name)
            return False

        return self._finalize_apply(theme_config, canonical_name, name)

    def clear_cache(self) -> None:
        """Clear QSS cache."""
        self._stylesheet_service.clear_cache()

    # --- Helpers to reduce complexity of apply() ---
    def _resolve_theme_config(
        self, original_name: str, normalized_name: str
    ) -> tuple[str, dict[str, Any] | None]:
        """Resolve theme configuration and canonical name with fallback.

        Returns (canonical_name, theme_config) or (normalized_name, None) on failure.
        """
        theme_config = self._get_theme_by_name(normalized_name)
        if not theme_config:
            logger.error("Theme not found: %s", original_name)
            fallback = self._theme_registry.get_default_theme_id()
            theme_config = self._get_theme_by_name(fallback)
            if not theme_config:
                return normalized_name, None
            normalized_name = fallback
        canonical_name = theme_config.get("name", normalized_name)
        return canonical_name, theme_config

    def _load_qss_content(
        self, canonical_name: str, theme_config: dict[str, Any]
    ) -> str | None:
        """Load composed QSS content for a theme.

        Supports absolute and resource-relative paths.
        """
        qss_path = theme_config.get("qss_path")
        if qss_path:
            p = Path(str(qss_path))
            if not p.is_absolute():
                parts = p.parts
                if parts and parts[0].lower() == "resources":
                    p = Path(*parts[1:])
                p = PathManager.get_resource_path(p)
            return self._stylesheet_service.load_stylesheet_from_path(canonical_name, p)
        return self._stylesheet_service.load_stylesheet(
            canonical_name, f"{canonical_name}.qss"
        )

    def _validate_gui_thread(self) -> bool:
        """Ensure apply() is executed on the GUI thread."""
        app_instance = QApplication.instance()
        if app_instance and QThread.currentThread() is not app_instance.thread():
            logger.error("ThemeController.apply must be called from the GUI thread")
            return False
        return True

    def _finalize_apply(
        self, theme_config: dict[str, Any], canonical_name: str, log_name: str
    ) -> bool:
        """Finalize theme application: configure icon theme and persist settings."""
        try:
            if theme_config.get("source") == "bundled":
                try:
                    configure_qicon_theme(canonical_name)
                except Exception as icon_exc:
                    logger.warning(
                        "Failed to apply Qt icon theme: %s", icon_exc, exc_info=True
                    )

            logger.info("Applied theme: %s", canonical_name)
            self.settings.set_theme(canonical_name)
            SettingsManager.set("theme.name", canonical_name)
            SettingsManager.save()
            if self.main_window and hasattr(self.main_window, "update_theme"):
                self.main_window.update_theme()
            return True
        except Exception as exc:
            logger.error("Theme application error %s: %s", log_name, exc, exc_info=True)
            return False

    def refresh_themes(self) -> None:
        """Reload themes from registry (e.g., after import/remove)."""
        self._theme_registry.invalidate()
        self._load_available_themes()

    def _clear_icon_cache_safe(self) -> None:
        """Clear icon cache with error handling."""
        try:
            clear_icon_cache()
            from app.utils.ui.icon.path_service import icon_path_service

            icon_path_service.clear_cache()
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
                if getattr(self.main_window, "_topbar_refresh_requested", False):
                    return
                self.top_panels_controller.request_refresh(150)
        except Exception as exc:
            logger.warning("Top panels update error: %s", exc, exc_info=True)

    def _perform_ui_updates(self, mw) -> None:
        """Perform all UI updates (menu, structure, panels)."""
        try:
            action_controller = getattr(mw, "action_controller", None)
            if action_controller and hasattr(action_controller, "refresh_action_icons"):
                action_controller.refresh_action_icons()
        except Exception as exc:
            logger.warning("Global action icon refresh error: %s", exc, exc_info=True)
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
            "ThemeController: batch UI update after theme change: menu -> structure icons -> top panels"
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
                    "ThemeController: require_suspend_updates=True, but suspend_updates utility unavailable - skipping batch UI update"
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
