"""Password prompt dialog for encrypting and unlocking link notes."""

from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.i18n.common import tr as tr_common

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)


class NotePasswordDialog(BaseDialog):
    """Compact modal dialog for setting or entering a note encryption password."""

    _TR_CONTEXT = "NotePasswordDialog"

    def __init__(
        self,
        mode: str = "unlock",
        verify_callback: Callable[[str], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._mode = mode if mode in ("encrypt", "unlock", "decrypt") else "unlock"
        self._verify_callback = verify_callback
        self._button_box: QDialogButtonBox | None = None
        self._password_label: QLabel | None = None
        self._confirm_label: QLabel | None = None
        self._error_label: QLabel | None = None
        self.password_le: QLineEdit | None = None
        self.confirm_le: QLineEdit | None = None

        super().__init__(parent)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint
        )
        self.setFixedWidth(app_config.ui.get_entity_dialog_fixed_width())

        self._init_ui()
        self.retranslateUi()
        self.adjustSize()

    def _init_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.password_le = QLineEdit()
        self.password_le.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_le.returnPressed.connect(self._on_password_return)

        self._password_label = QLabel()
        form.addRow(self._password_label, self.password_le)

        if self._mode == "encrypt":
            self.confirm_le = QLineEdit()
            self.confirm_le.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_le.returnPressed.connect(self._on_return_pressed)
            self._confirm_label = QLabel()
            form.addRow(self._confirm_label, self.confirm_le)

        vbox.addLayout(form)

        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #e05252; font-size: 12px;")
        self._error_label.setVisible(False)
        vbox.addWidget(self._error_label)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box = bb

        ok_btn = bb.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setDefault(False)
            ok_btn.setAutoDefault(False)
            ok_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            ok_btn.setEnabled(False)

        cancel_btn = bb.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setDefault(False)
            cancel_btn.setAutoDefault(False)
            cancel_btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)

        self.equalize_button_box(bb, min_width=app_config.ui.get_fixed_button_width())

        self.password_le.textChanged.connect(self._on_input_changed)
        if self.confirm_le is not None:
            self.confirm_le.textChanged.connect(self._on_input_changed)

        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        vbox.addWidget(bb)

    def retranslateUi(self) -> None:
        if self._mode == "encrypt":
            title = QCoreApplication.translate("NotePasswordDialog", "Encrypt Note")
        elif self._mode == "decrypt":
            title = QCoreApplication.translate("NotePasswordDialog", "Decrypt Note")
        else:
            title = QCoreApplication.translate("NotePasswordDialog", "Unlock Note")
        self.setWindowTitle(title)

        if self._password_label is not None:
            self._password_label.setText(
                QCoreApplication.translate("NotePasswordDialog", "Password:")
            )
        if self._confirm_label is not None:
            self._confirm_label.setText(
                QCoreApplication.translate("NotePasswordDialog", "Confirm:")
            )

        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if ok_btn is not None:
                ok_btn.setText(
                    tr_common("Save")
                    if self._mode == "encrypt"
                    else QCoreApplication.translate("NotePasswordDialog", "OK")
                )
            if cancel_btn is not None:
                cancel_btn.setText(tr_common("Cancel"))
            self.equalize_button_box(
                self._button_box, min_width=app_config.ui.get_fixed_button_width()
            )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        try:
            if self.password_le is not None:
                self.password_le.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        except Exception:
            logger.debug("NotePasswordDialog.showEvent: setFocus failed", exc_info=True)
        try:
            self.adjustSize()
        except Exception:
            logger.debug(
                "NotePasswordDialog.showEvent: adjustSize failed", exc_info=True
            )

    def _on_input_changed(self) -> None:
        if self._error_label is not None and self._error_label.isVisible():
            self._error_label.setVisible(False)
            self.adjustSize()

        pwd = self.password_le.text() if self.password_le is not None else ""
        if self._mode == "encrypt":
            conf = self.confirm_le.text() if self.confirm_le is not None else ""
            valid = bool(pwd) and pwd == conf
            if pwd and conf and pwd != conf and self._error_label is not None:
                self._error_label.setText(
                    QCoreApplication.translate(
                        "NotePasswordDialog", "Passwords do not match"
                    )
                )
                self._error_label.setVisible(True)
                self.adjustSize()
        else:
            valid = bool(pwd)

        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_btn is not None:
                ok_btn.setEnabled(valid)

    def _on_password_return(self) -> None:
        if self._mode == "encrypt" and self.confirm_le is not None:
            if not self.confirm_le.text():
                self.confirm_le.setFocus()
                return
        self._on_return_pressed()

    def _on_return_pressed(self) -> None:
        if self._button_box is not None:
            ok_btn = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_btn is not None and ok_btn.isEnabled():
                self._on_accept()

    def _on_accept(self) -> None:
        pwd = self.get_password()
        if not pwd:
            return
        if self._mode == "encrypt" and self.confirm_le is not None:
            if pwd != self.confirm_le.text():
                return

        if self._verify_callback is not None:
            if not self._verify_callback(pwd):
                if self._error_label is not None:
                    self._error_label.setText(
                        QCoreApplication.translate(
                            "NotePasswordDialog", "Incorrect password"
                        )
                    )
                    self._error_label.setVisible(True)
                    self.adjustSize()
                if self.password_le is not None:
                    self.password_le.selectAll()
                    self.password_le.setFocus()
                return

        self.accept()

    def get_password(self) -> str:
        """Return the entered password."""
        return self.password_le.text() if self.password_le is not None else ""
