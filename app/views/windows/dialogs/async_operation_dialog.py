"""Dialog showing progress for asynchronous database operations.

✅ FIX: All slots now use Qt.QueuedConnection for thread-safe updates.
"""

import logging
from typing import Optional

from PyQt6.QtCore import QCoreApplication, Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.i18n.common import tr as tr_common
from app.views.windows.dialogs.base_dialog import BaseDialog

_TR_CONTEXT = "AsyncOperationDialog"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


_DEFAULT_TITLE = None
_DEFAULT_MESSAGE = None
logger = logging.getLogger(__name__)


class AsyncOperationDialog(BaseDialog):
    """Progress dialog for asynchronous database operations.

    Features:
    - Progress bar with percentage information
    - Text description for the current stage
    - Optional cancel button
    - Automatic close on success
    """

    def __init__(
        self,
        title: str | None = _DEFAULT_TITLE,
        message: str | None = _DEFAULT_MESSAGE,
        cancelable: bool = False,
        parent: Optional[QWidget] = None,
    ):
        """
        Args:
            title: Dialog window title
            message: Initial status text
            cancelable: Whether to show the cancel button
            parent: Parent widget
        """
        # Ensure literals are extractable by lupdate: translate only string literals here
        # and also translate custom titles/messages if provided.
        # Remember source strings to support runtime retranslate
        self._title_source: str = "Operation" if title is None else title
        self._message_source: str = "Processing…" if message is None else message
        self._message_is_initial: bool = True  # becomes False after runtime updates

        self._cancelled = False
        self._auto_close = True
        self.cancel_button: Optional[QPushButton] = None
        self._last_progress: tuple[int, int] | None = None  # ensure ready before BaseDialog init

        super().__init__(parent)

        effective_title = _tr(self._title_source)
        effective_message = _tr(self._message_source)

        self.setWindowTitle(effective_title)
        self.setModal(True)
        self.setMinimumWidth(app_config.ui.get_async_operation_dialog_min_width())

        # Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(app_config.ui.get_async_operation_dialog_spacing())

        # Main status message
        self.message_label = QLabel(effective_message)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # Details of the current stage
        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.detail_label)

        # Cancel button
        if cancelable:
            self.cancel_button = QPushButton(tr_common("Cancel"))
            self.cancel_button.clicked.connect(self._on_cancel)
            layout.addWidget(self.cancel_button)
        else:
            self.cancel_button = None

        layout.addStretch()

    def retranslateUi(self) -> None:
        """Apply runtime translations when language changes."""
        # Защита от вызова до полной инициализации
        if not hasattr(self, '_title_source'):
            return
        
        # Window title from source literal/custom value
        self.setWindowTitle(_tr(self._title_source))

        # Initial message is updated only if still in initial state
        try:
            if self._message_is_initial:
                self.message_label.setText(_tr(self._message_source))
        except Exception:
            pass

        # Cancel button text (if present)
        if self.cancel_button is not None:
            self.cancel_button.setText(tr_common("Cancel"))

        # Re-format progress string using last known values
        if self._last_progress is not None:
            current, total = self._last_progress
            if total > 0:
                percentage = int((current / total) * 100)
                try:
                    self.progress_bar.setFormat(
                        self.tr("{percentage}% ({current}/{total})").format(
                            percentage=percentage, current=current, total=total
                        )
                    )
                except Exception:
                    pass

    def set_auto_close(self, auto_close: bool):
        """Toggle auto-close on successful completion."""
        self._auto_close = auto_close

    @pyqtSlot(int, int, str)
    def update_progress(self, current: int, total: int, message: str = ""):
        """Update operation progress.

        Args:
            current: Current progress value
            total: Total value for completion
            message: Message describing the current stage
        """
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
            self.progress_bar.setFormat(
                self.tr("{percentage}% ({current}/{total})").format(
                    percentage=percentage, current=current, total=total
                )
            )
            self._last_progress = (current, total)

        if message:
            self.detail_label.setText(self.tr(message))
            self._message_is_initial = False

    @pyqtSlot(object)
    def on_finished(self, result):
        """Handle successful completion.

        Args:
            result: Operation result payload
        """
        self.progress_bar.setValue(100)
        self.message_label.setText(self.tr("✅ Operation completed successfully"))
        self.detail_label.setText("")
        self._message_is_initial = False

        if self.cancel_button:
            self.cancel_button.setEnabled(False)

        if self._auto_close:
            self.accept()
        else:
            # Swap the cancel button to a close button
            if self.cancel_button:
                self.cancel_button.setText(self.tr("Close"))
                self.cancel_button.setEnabled(True)
                self.cancel_button.clicked.disconnect()
                self.cancel_button.clicked.connect(self.accept)

    @pyqtSlot(Exception, str)
    def on_error(self, exception: Exception, traceback: str):
        """Handle an operation error.

        Args:
            exception: Raised exception instance
            traceback: Exception traceback string
        """
        self.progress_bar.setValue(0)
        self.message_label.setText(
            self.tr("❌ Error: {error}").format(error=str(exception))
        )
        self.detail_label.setText("")
        self._message_is_initial = False

        if self.cancel_button:
            self.cancel_button.setText(self.tr("Close"))
            self.cancel_button.clicked.disconnect()
            self.cancel_button.clicked.connect(self.reject)

        logger.error("Asynchronous operation error: %s\n%s", exception, traceback)

    @pyqtSlot()
    def on_cancelled(self):
        """Handle the cancellation event."""
        self.message_label.setText(self.tr("⚠️ Operation cancelled"))
        self.detail_label.setText("")
        self.reject()
        self._message_is_initial = False

    def _on_cancel(self):
        """Cancel button handler."""
        self._cancelled = True
        self.message_label.setText(self.tr("Cancelling operation…"))
        if self.cancel_button:
            self.cancel_button.setEnabled(False)
        self._message_is_initial = False

    def is_cancelled(self) -> bool:
        """Return whether the operation has been cancelled."""
        return self._cancelled

    def connect_worker_signals(self, worker_signals) -> None:
        """Connect worker signals with thread-safe QueuedConnection.
        
        ✅ FIX: Uses Qt.QueuedConnection to ensure thread safety when
        signals are emitted from background threads.
        
        Args:
            worker_signals: Worker signals object with progress, finished, error, cancelled
        """
        try:
            # Connect with QueuedConnection for cross-thread safety
            if hasattr(worker_signals, "progress"):
                worker_signals.progress.connect(
                    self.update_progress,
                    Qt.ConnectionType.QueuedConnection
                )
            if hasattr(worker_signals, "finished"):
                worker_signals.finished.connect(
                    self.on_finished,
                    Qt.ConnectionType.QueuedConnection
                )
            if hasattr(worker_signals, "error"):
                worker_signals.error.connect(
                    self.on_error,
                    Qt.ConnectionType.QueuedConnection
                )
            if hasattr(worker_signals, "cancelled"):
                worker_signals.cancelled.connect(
                    self.on_cancelled,
                    Qt.ConnectionType.QueuedConnection
                )
            logger.debug("Worker signals connected with QueuedConnection")
        except Exception as exc:
            logger.error("Failed to connect worker signals: %s", exc, exc_info=True)
