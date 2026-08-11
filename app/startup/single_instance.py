"""Single-instance guard using QLocalServer / QLocalSocket.

Usage
-----
    guard = SingleInstanceGuard(server_name, lambda: activate_my_main_window())
    if not guard.acquire():
        # Another instance is running; we already asked it to come forward
        sys.exit(0)

    # ... normal startup ...

    guard.close()  # release the server on shutdown
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Callable

from PyQt6.QtCore import QByteArray, QIODevice
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

_ACTIVATE_CMD = b"ACTIVATE\n"
_SOCKET_CONNECT_TIMEOUT_MS = 2000


def _try_force_foreground_on_windows() -> None:
    """Best-effort: unblock SetForegroundWindow for the next call (Windows).

    Windows 10/11 applies a foreground-lock that prevents background processes
    from stealing focus.  ``AllowSetForegroundWindow(ASFW_ANY)`` temporarily
    lifts that restriction for the next foreground change, which makes
    ``QWidget.activateWindow()`` reliable even when triggered from a socket
    callback (IPC from another process).
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ASFW_ANY = -1
        ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception as exc:  # pragma: no cover - platform best effort
        logger.debug("AllowSetForegroundWindow unavailable: %s", exc)


class SingleInstanceGuard:
    """Ensure only one process instance runs, and forward duplicates to it."""

    def __init__(
        self,
        server_name: str,
        activate_callback: Callable[[], None],
    ) -> None:
        self._server_name = server_name
        self._activate = activate_callback
        self._server: QLocalServer | None = None
        self._is_owner = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def is_owner(self) -> bool:
        return self._is_owner

    def acquire(self) -> bool:
        """Attempt to become the single running instance.

        Returns
        -------
        bool
            ``True`` — this process is the owner and should continue startup.
            ``False`` — another instance already owns the slot.  We notified
            it to activate its main window; caller should exit cleanly.
        """
        # Phase 1: try to connect to a running server (we are the second copy)
        if self._try_notify_running_instance():
            logger.info(
                "Single-instance guard: detected running instance, "
                "requested main window activation, exiting"
            )
            return False

        # Phase 2: become the server (first/only instance)
        if not self._start_server():
            logger.warning(
                "Single-instance guard: failed to start local server '%s'. "
                "Allowing startup anyway (no single-instance protection).",
                self._server_name,
            )
            # Fail open: we'd rather start the app than block the user.
            return True

        self._is_owner = True
        logger.info(
            "Single-instance guard: acquired ownership of '%s'",
            self._server_name,
        )
        return True

    def close(self) -> None:
        """Release the local server resources."""
        if self._server is not None:
            try:
                self._server.close()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("SingleInstanceGuard server close error: %s", exc)
            finally:
                # On Unix a leftover socket file can block next listen
                try:
                    QLocalServer.removeServer(self._server_name)
                except Exception:
                    pass
                self._server = None
                self._is_owner = False

    # ------------------------------------------------------------------
    # Internal helpers — client side (second instance)
    # ------------------------------------------------------------------
    def _try_notify_running_instance(self) -> bool:
        """Try to connect to an existing server and send ACTIVATE.

        Returns ``True`` on success (another instance is alive).
        """
        socket = QLocalSocket()
        try:
            socket.connectToServer(self._server_name, QIODevice.OpenModeFlag.WriteOnly)
            if not socket.waitForConnected(_SOCKET_CONNECT_TIMEOUT_MS):
                err = socket.error()
                # "Server not found" is the expected happy path for first run
                if err != QLocalSocket.LocalSocketError.ServerNotFoundError:
                    logger.debug(
                        "SingleInstanceGuard connect failed (%s): %s",
                        err.name if hasattr(err, "name") else err,
                        socket.errorString(),
                    )
                return False

            socket.write(QByteArray(_ACTIVATE_CMD))
            if not socket.waitForBytesWritten(1500):
                logger.debug("SingleInstanceGuard write timeout")
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("SingleInstanceGuard notify error: %s", exc)
            return False
        finally:
            try:
                socket.disconnectFromServer()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal helpers — server side (first instance)
    # ------------------------------------------------------------------
    def _start_server(self) -> bool:
        # Remove a stale socket file left by an unclean shutdown (Unix only)
        try:
            QLocalServer.removeServer(self._server_name)
        except Exception:
            pass

        server = QLocalServer()
        if not server.listen(self._server_name):
            logger.warning(
                "SingleInstanceGuard listen failed: %s",
                server.errorString(),
            )
            return False

        server.newConnection.connect(self._on_new_connection)
        self._server = server
        return True

    def _on_new_connection(self) -> None:
        if self._server is None:
            return
        # Drain all queued incoming connections
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                break
            # Read the payload (optional; we always do the same action)
            try:
                client.readyRead.connect(lambda c=client: self._drain_socket(c))
                client.disconnected.connect(client.deleteLater)
            except Exception:
                pass

        # Allow Qt's focus machinery to steal focus on Windows
        _try_force_foreground_on_windows()

        # Request the hosting layer to activate the main window
        try:
            self._activate()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("SingleInstanceGuard activate callback failed: %s", exc, exc_info=True)

    @staticmethod
    def _drain_socket(socket: QLocalSocket) -> None:
        try:
            if socket.bytesAvailable():
                socket.readAll()
        except Exception:
            pass


__all__ = ["SingleInstanceGuard"]
