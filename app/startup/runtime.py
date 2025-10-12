"""Runtime orchestration for launching the Qt application."""

from __future__ import annotations

import functools
import logging
import sys
from dataclasses import dataclass
from enum import IntEnum

from PyQt6.QtCore import QCoreApplication, Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from app.config_data import app_config
from app.controllers.system.db_init import DatabaseInitializer
from app.startup.app_factory import create_application
from app.startup.argument_parser import determine_log_level, parse_arguments
from app.startup.browser_profiles_loader import BrowserProfilesLoader
from app.startup.initializer import ApplicationInitializer, StartupMode
from app.startup.logging_setup import log_shutdown, log_system_info, setup_logging
from app.startup.signal_handling import SignalManager, should_install_signal_handlers
from i18n.language_service import LanguageService

logger = logging.getLogger(__name__)


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


def run(options: StartupOptions | None = None) -> int:
    """Application runtime entry point."""
    args = parse_arguments()
    options = options or StartupOptions()
    if args.no_gui and options.mode == StartupMode.GUI:
        options.mode = StartupMode.HEADLESS
    log_level = determine_log_level(args)
    setup_logging(log_level)
    if options.log_system_details:
        log_system_info()

    app: QApplication | QCoreApplication | None = None
    initializer: ApplicationInitializer | None = None
    signal_manager: SignalManager | None = None
    about_to_quit_cleanup_registered = False

    try:
        if options.mode == StartupMode.GUI:
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
                    return ExitCode.INITIALIZATION_FAILURE
            else:
                logger.info("Using existing QApplication instance")
            app = qt_app
        else:
            core_app = QCoreApplication.instance()
            if core_app is None:
                logger.info("Creating new QCoreApplication instance for headless mode")
                core_app = QCoreApplication(sys.argv)
            else:
                logger.info("Using existing QCoreApplication instance")
            app = core_app

        initializer = ApplicationInitializer(mode=options.mode)
        about_to_quit_cleanup = functools.partial(
            initializer.cleanup,
            async_cleanup=False,
        )
        try:
            app.aboutToQuit.connect(about_to_quit_cleanup)
            about_to_quit_cleanup_registered = True
        except Exception as exc:
            logger.debug("Failed to bind aboutToQuit cleanup handler: %s", exc)

        if should_install_signal_handlers():
            logger.info("Installing signal handlers for console/headless mode")
            signal_manager = SignalManager(app, initializer)
            signal_manager.install()
            initializer.attach_signal_notifiers(signal_manager.notifiers())
        else:
            logger.info(
                "Running in GUI mode, signal handlers disabled for natural Ctrl+C behavior"
            )

        language_service = None
        if options.mode == StartupMode.GUI:
            try:
                language_service = LanguageService.instance()
                logger.info(
                    "Language service initialized, current language: %s",
                    language_service.current_language(),
                )
            except Exception as exc:
                logger.warning("Failed to initialize language service: %s", exc)
                language_service = None

            quit_on_last_window = app_config.get("ui.quit_on_last_window_closed", True)
            if isinstance(app, QApplication):
                app.setQuitOnLastWindowClosed(quit_on_last_window)
                logger.info("Set quit on last window closed: %s", quit_on_last_window)

            if language_service:
                try:
                    language_service.install_translator(app)
                except Exception as exc:
                    logger.warning("Failed to install translator: %s", exc)

        if not initializer.initialize_all():
            logger.critical("Failed to initialize application")
            if app:
                app.quit()
            return ExitCode.INITIALIZATION_FAILURE

        db_initializer = DatabaseInitializer(
            initializer.database, initializer.main_window
        )
        db_initializer.initialize_async()

        if initializer.main_window is not None:
            profiles_loader = BrowserProfilesLoader(initializer.main_window)
            profiles_loader.setup_lazy_loading()

        if options.auto_quit:
            QTimer.singleShot(max(0, options.quit_after_ms), app.quit)

        if options.mode == StartupMode.GUI:
            startup_delay = app_config.get("startup.app_ready_delay_ms", 100)
            QTimer.singleShot(
                startup_delay, lambda: logger.info("Application started successfully")
            )

        exit_code = app.exec()

        if exit_code == -1:
            logger.critical("QApplication exec() failed with error code -1")
            return ExitCode.RUNTIME_ERROR
        if exit_code < 0:
            logger.error(
                "QApplication returned unexpected negative code: %d", exit_code
            )
            return ExitCode.RUNTIME_ERROR

        logger.info("Application exited with code: %d", exit_code)
        return ExitCode.SUCCESS if exit_code == 0 else ExitCode.INITIALIZATION_FAILURE

    except (KeyboardInterrupt, SystemExit):
        logger.info("Application interrupted by user")
        raise
    except Exception as exc:
        logger.critical("Critical error in run(): %s", exc, exc_info=True)
        return ExitCode.RUNTIME_ERROR
    finally:
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
                app.aboutToQuit.disconnect(about_to_quit_cleanup)  # type: ignore[attr-defined]
            except Exception:
                pass

        log_shutdown()


__all__ = ["run", "ExitCode", "StartupOptions"]
