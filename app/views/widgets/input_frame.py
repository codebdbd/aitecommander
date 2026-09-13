"""
Composite container frame for multiline text editors.

Wraps a `QTextEdit` (or other scroll-area editor) inside a standard `QFrame`
that adopts the theme's `QLineEdit` border and background styles, forwarding
focus state dynamically via the `focused` property.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QFrame, QTextEdit, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


class InputFrame(QFrame):
    """
    Container frame providing standard input borders and backgrounds
    for multiline editors (`QTextEdit`) across all themes.
    """

    def __init__(self, editor: QTextEdit, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("inputFrame")
        self.setProperty("input_frame", "true")

        self._editor = editor

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        editor.setFrameShape(QFrame.Shape.NoFrame)
        editor.setStyleSheet("QTextEdit { border: none; background: transparent; }")
        editor.installEventFilter(self)
        layout.addWidget(editor)

    @property
    def editor(self) -> QTextEdit:
        """Return the wrapped editor widget."""
        return self._editor

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._editor:
            if event.type() == QEvent.Type.FocusIn:
                self.setProperty("focused", "true")
                self.style().unpolish(self)
                self.style().polish(self)
            elif event.type() == QEvent.Type.FocusOut:
                self.setProperty("focused", "false")
                self.style().unpolish(self)
                self.style().polish(self)
        return super().eventFilter(watched, event)
