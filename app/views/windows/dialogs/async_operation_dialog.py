"""Dialog showing progress for asynchronous database operations."""
import logging
from typing import Optional

from PyQt6.QtCore import QCoreApplication, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_TR_CONTEXT = "AsyncOperationDialog"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


_DEFAULT_TITLE = "Operation"
_DEFAULT_MESSAGE = "Processing…"
logger = logging.getLogger(__name__)


class AsyncOperationDialog(QDialog):
    """Progress dialog for asynchronous database operations.

    Features:
    - Progress bar with percentage information
    - Text description for the current stage
    - Optional cancel button
    - Automatic close on success
    """

    def __init__(
        self,
        title: str = _DEFAULT_TITLE,
        message: str = _DEFAULT_MESSAGE,
        cancelable: bool = False,
        parent: Optional[QWidget] = None
    ):
        """
        Args:
            title: Dialog window title
            message: Initial status text
            cancelable: Whether to show the cancel button
            parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle(_tr(title))
        self.setModal(True)
        self.setMinimumWidth(400)

        self._cancelled = False
        self._auto_close = True
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Main status message
        self.message_label = QLabel(_tr(message))
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
            self.cancel_button = QPushButton(self.tr("Cancel"))
            self.cancel_button.clicked.connect(self._on_cancel)
            layout.addWidget(self.cancel_button)
        else:
            self.cancel_button = None

        layout.addStretch()

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

        if message:
            self.detail_label.setText(self.tr(message))

    @pyqtSlot(object)
    def on_finished(self, result):
        """Handle successful completion.

        Args:
            result: Operation result payload
        """
        self.progress_bar.setValue(100)
        self.message_label.setText(self.tr("✅ Operation completed successfully"))
        self.detail_label.setText("")

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

    def _on_cancel(self):
        """Cancel button handler."""
        self._cancelled = True
        self.message_label.setText(self.tr("Cancelling operation…"))
        if self.cancel_button:
            self.cancel_button.setEnabled(False)

    def is_cancelled(self) -> bool:
        """Return whether the operation has been cancelled."""
        return self._cancelled
