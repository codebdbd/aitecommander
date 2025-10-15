"""Cross-platform signal handling helpers for the Qt event loop."""

from __future__ import annotations

import logging
import os
import platform
import signal
import sys
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, QSocketNotifier
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

SIGNAL_EXIT_CODE_BASE = 128
_unix_signal_pipe: tuple[int, int] | None = None

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from app.startup.initializer import ApplicationInitializer


def signal_handler(
    signum: int, frame: Any, initializer: ApplicationInitializer | None = None
) -> None:
    """Handle SIGINT/SIGTERM signals by requesting a graceful shutdown."""
    signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
    logger.info(
        "Received %s signal, initiating graceful shutdown...",
        signal_name,
    )
    exit_code = (
        SIGNAL_EXIT_CODE_BASE + signum
        if signum in (signal.SIGINT, signal.SIGTERM)
        else 1
    )
    QCoreApplication.exit(exit_code)


def safe_signal_handler(
    signum: int, frame: Any, initializer: ApplicationInitializer | None
) -> None:
    """Wrapper for signal handler with exception protection."""
    try:
        signal_handler(signum, frame, initializer)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error in signal handler: %s", exc, exc_info=True)
        os._exit(1)  # noqa: SLF001 - failsafe exit


def should_install_signal_handlers() -> bool:
    """Determine if signal handlers should be installed for console/headless mode."""
    if platform.system() == "Windows":
        return not sys.stdin.isatty() or not sys.stdout.isatty()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return True
    display_empty = os.environ.get("DISPLAY") in (None, "")
    wayland_empty = os.environ.get("WAYLAND_DISPLAY") in (None, "")
    return display_empty and wayland_empty


def setup_signal_handling(
    app: QApplication, initializer: ApplicationInitializer | None
) -> list[QSocketNotifier]:
    """Install signal handlers compatible with the Qt event loop."""
    notifiers: list[QSocketNotifier] = []
    if platform.system() != "Windows":
        global _unix_signal_pipe
        if _unix_signal_pipe:
            close_signal_pipe()

        unix_signal_pipe_read, unix_signal_pipe_write = os.pipe()
        _unix_signal_pipe = (unix_signal_pipe_read, unix_signal_pipe_write)

        def qt_safe_signal_handler(signum: int, frame: Any) -> None:
            try:
                os.write(unix_signal_pipe_write, bytes([signum]))
            except OSError as exc:
                logger.warning("Could not write to signal pipe: %s", exc)

        signal.signal(signal.SIGINT, qt_safe_signal_handler)
        signal.signal(signal.SIGTERM, qt_safe_signal_handler)

        notifier = QSocketNotifier(
            unix_signal_pipe_read, QSocketNotifier.Type.Read, app
        )

        def handle_qt_signal(sock: int) -> None:
            try:
                data = os.read(sock, 1)
            except OSError as exc:
                logger.warning("Could not read from signal pipe: %s", exc)
                return

            if not data:
                logger.warning("Signal pipe returned no data; defaulting to SIGTERM")
                signum = signal.SIGTERM
            else:
                signum = data[0]

            signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
            logger.info(
                "Received %s signal via QSocketNotifier, initiating graceful shutdown...",
                signal_name,
            )
            QCoreApplication.exit(SIGNAL_EXIT_CODE_BASE + signum)

        notifier.activated.connect(handle_qt_signal)
        notifiers.append(notifier)
    else:

        def signal_wrapper(signum: int, frame: Any) -> None:
            safe_signal_handler(signum, frame, initializer)

        signal.signal(signal.SIGINT, signal_wrapper)
        signal.signal(signal.SIGTERM, signal_wrapper)

    return notifiers


def restore_default_signal_handlers() -> None:
    """Restore default signal handlers."""
    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.warning("Failed to restore signal handlers: %s", exc)


def close_signal_pipe() -> None:
    """Close the Unix signal pipe if it was created."""
    global _unix_signal_pipe
    if not _unix_signal_pipe:
        return
    read_fd, write_fd = _unix_signal_pipe
    for fd in (read_fd, write_fd):
        try:
            os.close(fd)
        except OSError as exc:
            logger.warning("Failed to close signal pipe fd %s: %s", fd, exc)
    _unix_signal_pipe = None


class SignalManager:
    """Manage installation and teardown of cross-platform signal handlers."""

    def __init__(
        self,
        app: QApplication,
        initializer: ApplicationInitializer | None,
    ) -> None:
        self._app = app
        self._initializer = initializer
        self._notifiers: list[QSocketNotifier] = []
        self._installed = False

    @property
    def installed(self) -> bool:
        return self._installed

    def install(self) -> None:
        if self._installed:
            return
        self._notifiers = setup_signal_handling(self._app, self._initializer)
        self._installed = bool(self._notifiers or platform.system() == "Windows")

    def notifiers(self) -> list[QSocketNotifier]:
        return list(self._notifiers)

    def restore(self) -> None:
        if not self._installed:
            return
        restore_default_signal_handlers()

    def close(self) -> None:
        close_signal_pipe()

    def reset(self) -> None:
        self._notifiers.clear()
        self._installed = False


__all__ = [
    "SIGNAL_EXIT_CODE_BASE",
    "should_install_signal_handlers",
    "setup_signal_handling",
    "restore_default_signal_handlers",
    "close_signal_pipe",
    "SignalManager",
]
