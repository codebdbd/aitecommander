"""Runtime orchestration for launching the Qt application."""

from __future__ import annotations

import functools
import logging
import os
import platform
import sys
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.controllers.system.db_init import DatabaseInitializer
from app.core.database_manager import DatabaseManager
from app.core.hotkey_manager import HotkeyManager
from app.core.log_manager import LogManager
from app.core.settings_manager import SettingsManager
from app.core.worker_manager import WorkerManager
from app.resources import app_resources_rc, icons_rc
from app.startup.app_factory import create_application
from app.startup.argument_parser import determine_log_level, parse_arguments
from app.startup.browser_profiles_loader import BrowserProfilesLoader
from app.startup.initializer import ApplicationInitializer, StartupMode
from app.startup.signal_handling import (
    SignalManager,
    should_install_signal_handlers,
)
from i18n import resources_rc as i18n_resources_rc
from i18n.language_service import LanguageService


def qInitResources() -> None:
    app_resources_rc.qInitResources()
    icons_rc.qInitResources()
    i18n_resources_rc.qInitResources()


def qCleanupResources() -> None:
    app_resources_rc.qCleanupResources()
    icons_rc.qCleanupResources()
    i18n_resources_rc.qCleanupResources()


_resources_initialized = False

logger = logging.getLogger(__name__)
_qt_prev_message_handler = None


def _install_qt_message_filter() -> None:
    """Install a narrow Qt message filter to suppress noisy painter warnings.

    We only suppress known benign startup warnings:
      - ``QPainter::...``
      - ``...Painter not active...``
    Everything else is forwarded to the previous Qt handler.
    """
    global _qt_prev_message_handler
    try:
        from PyQt6.QtCore import qInstallMessageHandler
    except Exception as exc:
        logger.debug("Qt message filter unavailable: %s", exc)
        return

    if _qt_prev_message_handler is not None:
        return

    def _handler(msg_type: Any, context: Any, message: Any) -> None:  # noqa: ANN401
        msg = str(message) if message is not None else ""
        if msg.startswith("QPainter::") or "Painter not active" in msg:
            return

        prev = _qt_prev_message_handler
        if prev is not None:
            try:
                prev(msg_type, context, message)
            except Exception:
                logger.debug("Previous Qt message handler failed", exc_info=True)

    try:
        _qt_prev_message_handler = qInstallMessageHandler(_handler)
    except Exception as exc:
        logger.debug("Failed to install Qt message filter: %s", exc, exc_info=True)


class ExitCode(IntEnum):
    """Application exit codes following Unix conventions."""

    SUCCESS = 0
    INITIALIZATION_FAILURE = 1
    RUNTIME_ERROR = 2
    SIGNAL_BASE = 128


@dataclass
class StartupOptions:
    mode: StartupMode = StartupMode.GUI
    log_system_details: bool = True
    auto_quit: bool = False
    quit_after_ms: int = 0


def _setup_logging_and_args(options: StartupOptions) -> StartupOptions:
    """Parse arguments and setup logging."""
    args = parse_arguments()
    if args.no_gui and options.mode == StartupMode.GUI:
        options.mode = StartupMode.HEADLESS
    log_level = determine_log_level(args)
    LogManager.set_level(log_level)
    if options.log_system_details:
        _log_system_info()
    return options


def _create_qt_application(mode: StartupMode) -> QApplication | QCoreApplication | None:
    """Create QApplication or QCoreApplication based on mode."""
    if mode == StartupMode.GUI:
        qt_app = QApplication.instance()
        if qt_app is None:
            logger.info("Creating new QApplication instance")
            try:
                QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
                )
            except Exception as exc:
                logger.debug("Failed to set HiDPI rounding policy: %s", exc)
            qt_app = create_application()
            if qt_app is None:
                logger.critical("Failed to create QApplication instance")
                return None
        else:
            logger.info("Using existing QApplication instance")
        return qt_app
    else:
        core_app = QCoreApplication.instance()
        if core_app is None:
            logger.info("Creating new QCoreApplication instance for headless mode")
            core_app = QCoreApplication(sys.argv)
        else:
            logger.info("Using existing QCoreApplication instance")
        return core_app


def _register_cleanup_handler(
    app: QApplication | QCoreApplication,
    initializer: ApplicationInitializer,
) -> bool:
    """Register aboutToQuit cleanup handler."""
    about_to_quit_cleanup = functools.partial(
        initializer.cleanup,
        async_cleanup=False,
    )
    try:
        app.aboutToQuit.connect(about_to_quit_cleanup)
        # Store reference to the specific function for later disconnection
        app._about_to_quit_cleanup = about_to_quit_cleanup
        return True
    except Exception as exc:
        logger.debug("Failed to bind aboutToQuit cleanup handler: %s", exc)
        return False


def _setup_signal_handlers(
    app: QApplication | QCoreApplication,
    initializer: ApplicationInitializer,
    options: StartupOptions,
) -> SignalManager | None:
    """Setup signal handlers if needed."""
    if options.auto_quit:
        logger.info("Auto-quit enabled, skipping signal handlers")
        return None
    if should_install_signal_handlers():
        logger.info("Installing signal handlers for console/headless mode")
        signal_manager = SignalManager(app, initializer)
        signal_manager.install()
        initializer.attach_signal_notifiers(signal_manager.notifiers())
        return signal_manager
    else:
        logger.info(
            "Running in GUI mode, signal handlers disabled for natural Ctrl+C behavior"
        )
        return None


def _initialize_language_service(
    app: QApplication | QCoreApplication,
    mode: StartupMode,
) -> LanguageService | None:
    """Initialize language service for GUI mode."""
    if mode != StartupMode.GUI:
        return None

    try:
        language_service = LanguageService.instance()
        logger.info(
            "Language service initialized, current language: %s",
            language_service.current_language(),
        )
    except Exception as exc:
        logger.warning("Failed to initialize language service: %s", exc)
        return None

    quit_on_last_window = app_config.get("ui.quit_on_last_window_closed", True)
    if isinstance(app, QApplication):
        app.setQuitOnLastWindowClosed(quit_on_last_window)
        logger.info("Set quit on last window closed: %s", quit_on_last_window)

    try:
        language_service.install_translator(app)
    except Exception as exc:
        logger.warning("Failed to install translator: %s", exc)

    return language_service


def _preload_ui_icons() -> None:
    """Preload UI icons for faster menu rendering.
    
    DISABLED: Qt6 handles icon loading efficiently on-demand.
    Pre-loading blocks startup for ~800ms with no measurable benefit.
    """
    # Icons are loaded lazily when first accessed - much faster
    logger.debug("Icon preloading disabled - using lazy loading")


def _initialize_database_and_profiles(
    initializer: ApplicationInitializer,
) -> None:
    """Initialize database and browser profiles asynchronously."""
    db_initializer = DatabaseInitializer(initializer.database, initializer.main_window)
    db_initializer.initialize_async()

    if initializer.main_window is not None:
        profiles_loader = BrowserProfilesLoader(initializer.main_window)
        profiles_loader.setup_lazy_loading()


def _schedule_auto_quit(
    app: QApplication | QCoreApplication,
    options: StartupOptions,
) -> None:
    """Schedule auto quit if requested."""
    if options.auto_quit:
        def _auto_quit() -> None:
            # Disable faulthandler right before exit to avoid teardown AV.
            try:
                if "faulthandler" in sys.modules:
                    import faulthandler

                    if faulthandler.is_enabled():
                        faulthandler.disable()
            except Exception:
                pass
            app.quit()

        QTimer.singleShot(max(0, options.quit_after_ms), _auto_quit)

    if options.mode == StartupMode.GUI:
        startup_delay = app_config.get("startup.app_ready_delay_ms", 100)
        QTimer.singleShot(
            startup_delay, lambda: logger.info("Application started successfully")
        )


def _handle_exit_code(exit_code: int) -> int:
    """Validate and convert Qt exit code to application exit code."""
    if exit_code == -1:
        logger.critical("QApplication exec() failed with error code -1")
        return ExitCode.RUNTIME_ERROR
    if exit_code < 0:
        logger.error("QApplication returned unexpected negative code: %d", exit_code)
        return ExitCode.RUNTIME_ERROR

    logger.info("Application exited with code: %d", exit_code)
    return ExitCode.SUCCESS if exit_code == 0 else ExitCode.INITIALIZATION_FAILURE


def _cleanup_resources(
    initializer: ApplicationInitializer | None,
    signal_manager: SignalManager | None,
    app: QApplication | QCoreApplication | None,
    about_to_quit_cleanup_registered: bool,
) -> None:
    """Cleanup all resources on shutdown."""
    if initializer:
        try:
            initializer.ensure_emergency_cleanup()
        except Exception as exc:
            logger.error("Error during emergency cleanup: %s", exc)

    if signal_manager and signal_manager.installed:
        signal_manager.restore()
        signal_manager.close()

    if about_to_quit_cleanup_registered and hasattr(app, "aboutToQuit"):
        try:
            # Only disconnect our specific cleanup handler, not all handlers
            if hasattr(app, "_about_to_quit_cleanup"):
                app.aboutToQuit.disconnect(app._about_to_quit_cleanup)  # type: ignore[attr-defined]
                delattr(app, "_about_to_quit_cleanup")
        except Exception:
            pass

    log_shutdown()


def _register_hotkeys() -> None:
    """Register all hotkeys with defaults before UI creation."""
    # Global actions
    HotkeyManager.register(
        "global.add_link", "F1", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.edit_link", "F2", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.add_section", "F3", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.add_category", "F4", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.switch_sphere", "F6", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.settings", "F7", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.search_files", "F8", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.enter", "Enter", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.exit", "Alt+F4", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.import_browser", "Ctrl+Alt+C", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.import_icons", "Ctrl+Alt+I", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.import_db", "Ctrl+Alt+D", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.save_db", "Ctrl+Alt+S", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.save", "Ctrl+S", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.export_icons",
        "Ctrl+Alt+E",
        context=Qt.ShortcutContext.WindowShortcut,
    )
    HotkeyManager.register(
        "global.refresh_icons",
        "Ctrl+Alt+H",
        context=Qt.ShortcutContext.WindowShortcut,
    )
    HotkeyManager.register(
        "global.check_bad_urls",
        "Ctrl+Alt+U",
        context=Qt.ShortcutContext.WindowShortcut,
    )
    HotkeyManager.register(
        "global.restore_db",
        "Ctrl+Alt+B",
        context=Qt.ShortcutContext.WindowShortcut,
    )
    HotkeyManager.register(
        "global.clear_favorites",
        "Ctrl+Alt+F",
        context=Qt.ShortcutContext.WindowShortcut,
    )
    HotkeyManager.register(
        "global.delete", "Del", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.undo", "Ctrl+Z", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.redo", "Ctrl+Shift+Z", context=Qt.ShortcutContext.WindowShortcut
    )
    HotkeyManager.register(
        "global.redo_alt", "Ctrl+Y", context=Qt.ShortcutContext.WindowShortcut
    )

    # Table actions
    HotkeyManager.register(
        "table.select_all",
        "Ctrl+A",
        context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
    )
    HotkeyManager.register(
        "table.search_focus",
        "Ctrl+F",
        context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
    )
    HotkeyManager.register(
        "table.search_clear",
        "Escape",
        context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
    )
    HotkeyManager.register(
        "table.cut", "Ctrl+X", context=Qt.ShortcutContext.WidgetWithChildrenShortcut
    )
    HotkeyManager.register(
        "table.copy", "Ctrl+C", context=Qt.ShortcutContext.WidgetWithChildrenShortcut
    )
    HotkeyManager.register(
        "table.paste", "Ctrl+V", context=Qt.ShortcutContext.WidgetWithChildrenShortcut
    )
    HotkeyManager.register(
        "table.notes", "Ctrl+N", context=Qt.ShortcutContext.WidgetWithChildrenShortcut
    )
    HotkeyManager.register(
        "table.toggle_favorite",
        "Ctrl+D",
        context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
    )

    # Context/edit actions
    HotkeyManager.register(
        "edit.undo", "Ctrl+Z", context=Qt.ShortcutContext.WidgetShortcut
    )
    HotkeyManager.register(
        "edit.redo", "Ctrl+Y", context=Qt.ShortcutContext.WidgetShortcut
    )
    HotkeyManager.register(
        "edit.cut", "Ctrl+X", context=Qt.ShortcutContext.WidgetShortcut
    )
    HotkeyManager.register(
        "edit.copy", "Ctrl+C", context=Qt.ShortcutContext.WidgetShortcut
    )
    HotkeyManager.register(
        "edit.paste", "Ctrl+V", context=Qt.ShortcutContext.WidgetShortcut
    )
    HotkeyManager.register(
        "edit.delete", "Del", context=Qt.ShortcutContext.WidgetShortcut
    )
    HotkeyManager.register(
        "edit.select_all", "Ctrl+A", context=Qt.ShortcutContext.WidgetShortcut
    )
    HotkeyManager.register(
        "edit.clear_selection", "Ctrl+Shift+A", context=Qt.ShortcutContext.WidgetShortcut
    )

    # Topbar accessibility shortcuts (Alt+1..9)
    for i in range(1, 10):
        HotkeyManager.register(
            f"topbar.alt.{i}",
            f"Alt+{i}",
            context=Qt.ShortcutContext.WindowShortcut,
        )

    HotkeyManager.detect_conflicts()

def _log_system_info() -> None:
    """Log system information for debugging."""
    try:
        if not logger.isEnabledFor(logging.DEBUG):
            return
    except (AttributeError, RuntimeError):
        logger.warning("Failed to check log level", exc_info=True)

    from PyQt6.QtCore import QT_VERSION_STR
    from PyQt6.QtGui import QGuiApplication

    try:
        logger.info("Operating system: %s", platform.platform())
        logger.info("Python version: %s", sys.version)
        logger.info("Python architecture: %s", platform.architecture())
        logger.info("PyQt6 version: %s", QT_VERSION_STR)
        logger.info("Launch path: %s", sys.argv[0])
        logger.info("Working directory: %s", os.getcwd())
        logger.info("Process PID: %s", os.getpid())
        logger.info("Command-line arguments count: %s", len(sys.argv))

        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            geometry = screen.geometry()
            logger.info(
                "Display %s: %sx%s @ %sx",
                i,
                geometry.width(),
                geometry.height(),
                screen.devicePixelRatio(),
            )
    except (OSError, RuntimeError, AttributeError) as exc:
        logger.warning("Failed to obtain system information: %s", exc)


def log_shutdown() -> None:
    """Log application shutdown."""
    logger.info("=" * 60)
    logger.info("APPLICATION SHUTDOWN")
    logger.info("=" * 60)


def run(options: StartupOptions | None = None) -> int:
    """Application runtime entry point."""
    options = options or StartupOptions()
    options = _setup_logging_and_args(options)
    SettingsManager.load()
    DatabaseManager.configure()
    WorkerManager.configure(max_threads=4)
    _register_hotkeys()

    app: QApplication | QCoreApplication | None = None
    initializer: ApplicationInitializer | None = None
    signal_manager: SignalManager | None = None
    about_to_quit_cleanup_registered = False

    try:
        # Initialize resources
        global _resources_initialized
        if not _resources_initialized:
            qInitResources()
            _resources_initialized = True

        app = _create_qt_application(options.mode)
        if app is None:
            return ExitCode.INITIALIZATION_FAILURE
        if options.mode == StartupMode.GUI:
            _install_qt_message_filter()

        initializer = ApplicationInitializer(mode=options.mode)
        about_to_quit_cleanup_registered = _register_cleanup_handler(app, initializer)
        signal_manager = _setup_signal_handlers(app, initializer, options)
        _initialize_language_service(app, options.mode)

        # Preload UI icons before window creation
        if options.mode == StartupMode.GUI:
            _preload_ui_icons()

        if not initializer.initialize_all():
            logger.critical("Failed to initialize application")
            app.quit()
            return ExitCode.INITIALIZATION_FAILURE

        _initialize_database_and_profiles(initializer)
        _schedule_auto_quit(app, options)

        exit_code = app.exec()
        return _handle_exit_code(exit_code)

    except (KeyboardInterrupt, SystemExit):
        logger.info("Application interrupted by user")
        raise
    except Exception as exc:
        logger.critical("Critical error in run(): %s", exc, exc_info=True)
        return ExitCode.RUNTIME_ERROR
    finally:
        _cleanup_resources(
            initializer, signal_manager, app, about_to_quit_cleanup_registered
        )
        try:
            WorkerManager.shutdown(timeout_ms=2000)
        except Exception as exc:
            logger.warning("WorkerManager shutdown failed: %s", exc)
        try:
            DatabaseManager.close_all()
        except Exception as exc:
            logger.warning("DatabaseManager close failed: %s", exc)
        # Cleanup resources
        if _resources_initialized:
            qCleanupResources()
            _resources_initialized = False


__all__ = ["run", "ExitCode", "StartupOptions"]
