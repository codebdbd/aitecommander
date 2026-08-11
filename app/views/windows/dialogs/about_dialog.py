from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.config_data.runtime_config import runtime_app_config as app_config
from app.core.paths.path_manager import PathManager

from .base_dialog import BaseDialog

logger = logging.getLogger(__name__)

_TR_CONTEXT = "AboutDialog"
_SUPPORT_URL = "https://codebdbd.github.io/"
_REPOSITORY_URL = "https://github.com/codebdbd/aitecommander"


def _tr(text: str) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text)


class AboutDialog(BaseDialog):
    """Application About dialog aligned with the AiteBar information structure."""

    def __init__(self, parent=None) -> None:
        self.title_label = None
        self.description_label = None
        self.info_group = None
        self.version_label = None
        self.developer_label = None
        self.license_label = None
        self.tech_value_label = None
        self.paths_group = None
        self.data_title_label = None
        self.data_path_label = None
        self.data_button = None
        self.program_title_label = None
        self.program_path_label = None
        self.program_button = None
        self.resources_group = None
        self.support_button = None
        self.repo_button = None
        self.license_button = None
        self.button_box = None
        super().__init__(parent)
        self._program_dir = self._resolve_program_dir()
        self._data_dir = PathManager.user_data_root(
            app_config.settings.get_org_name(),
            app_config.settings.get_app_name(),
        )
        self._license_path = self._resolve_license_path()

        self.setModal(True)
        self.resize(560, 420)

        self._setup_ui()
        self.retranslateUi()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.title_label = QLabel(self)
        self.title_label.setObjectName("aboutTitleLabel")
        title_font = self.title_label.font()
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        self.description_label = QLabel(self)
        self.description_label.setWordWrap(True)
        self.description_label.setObjectName("aboutDescriptionLabel")
        layout.addWidget(self.description_label)

        self.info_group = QGroupBox(self)
        self.info_layout = QGridLayout(self.info_group)
        self.info_layout.setContentsMargins(12, 12, 12, 12)
        self.info_layout.setHorizontalSpacing(10)
        self.info_layout.setVerticalSpacing(6)
        layout.addWidget(self.info_group)

        self.version_label = QLabel(self.info_group)
        self.developer_label = QLabel(self.info_group)
        self.license_label = QLabel(self.info_group)
        self.tech_value_label = QLabel(self.info_group)
        for row, widget in enumerate(
            (
                self.version_label,
                self.developer_label,
                self.license_label,
                self.tech_value_label,
            )
        ):
            widget.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.info_layout.addWidget(widget, row, 0)

        self.paths_group = QGroupBox(self)
        self.paths_layout = QGridLayout(self.paths_group)
        self.paths_layout.setContentsMargins(12, 12, 12, 12)
        self.paths_layout.setHorizontalSpacing(10)
        self.paths_layout.setVerticalSpacing(8)
        layout.addWidget(self.paths_group)

        self.data_title_label = QLabel(self.paths_group)
        self.data_path_label = QLabel(self.paths_group)
        self.data_path_label.setWordWrap(True)
        self.data_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.data_button = QPushButton(self.paths_group)

        self.program_title_label = QLabel(self.paths_group)
        self.program_path_label = QLabel(self.paths_group)
        self.program_path_label.setWordWrap(True)
        self.program_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.program_button = QPushButton(self.paths_group)

        self.paths_layout.addWidget(self.data_title_label, 0, 0)
        self.paths_layout.addWidget(self.data_path_label, 1, 0)
        self.paths_layout.addWidget(self.data_button, 1, 1)
        self.paths_layout.addWidget(self.program_title_label, 2, 0)
        self.paths_layout.addWidget(self.program_path_label, 3, 0)
        self.paths_layout.addWidget(self.program_button, 3, 1)
        self.paths_layout.setColumnStretch(0, 1)
        layout.addWidget(self.paths_group)

        self.resources_group = QGroupBox(self)
        self.resources_layout = QGridLayout(self.resources_group)
        self.resources_layout.setContentsMargins(12, 12, 12, 12)
        self.resources_layout.setHorizontalSpacing(8)
        self.resources_layout.setVerticalSpacing(8)
        layout.addWidget(self.resources_group)

        self.support_button = QPushButton(self.resources_group)
        self.repo_button = QPushButton(self.resources_group)
        self.license_button = QPushButton(self.resources_group)
        self.resources_layout.addWidget(self.support_button, 0, 0)
        self.resources_layout.addWidget(self.repo_button, 1, 0)
        self.resources_layout.addWidget(self.license_button, 2, 0)

        layout.addStretch(1)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok, parent=self
        )
        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self.accept)
        self.support_button.clicked.connect(
            lambda: self._open_url(_SUPPORT_URL, self.support_button.text())
        )
        self.repo_button.clicked.connect(
            lambda: self._open_url(_REPOSITORY_URL, self.repo_button.text())
        )
        self.license_button.clicked.connect(
            lambda: self._open_local_path(self._license_path, self.license_button.text())
        )
        self.data_button.clicked.connect(
            lambda: self._open_local_path(self._data_dir, self.data_button.text())
        )
        self.program_button.clicked.connect(
            lambda: self._open_local_path(
                self._program_dir, self.program_button.text()
            )
        )

    def retranslateUi(self) -> None:
        if self.title_label is None:
            return

        app_name = app_config.settings.get_app_name()
        version = app_config.settings.get_app_version()

        self.setWindowTitle(_tr("About"))
        self.title_label.setText(app_name)
        self.description_label.setText(
            _tr(
                "Hierarchical bookmark and link manager for Windows. Organizes links across spheres, sections, and categories with themes, icons, and import/export tools."
            )
        )

        self.info_group.setTitle(_tr("Information"))
        self.version_label.setText(_tr("Version {0}").format(version))
        self.developer_label.setText(_tr("Developer: Codebdbd"))
        self.license_label.setText(_tr("License: MIT"))
        self.tech_value_label.setText(_tr("Python 3.12+ · PyQt6 · SQLite"))

        self.paths_group.setTitle(_tr("Application data"))
        self.data_title_label.setText(_tr("Data folder"))
        self.data_path_label.setText(str(self._data_dir))
        self.data_button.setText(_tr("Open data folder"))
        self.program_title_label.setText(_tr("Program folder"))
        self.program_path_label.setText(str(self._program_dir))
        self.program_button.setText(_tr("Open program folder"))

        self.resources_group.setTitle(_tr("Resources"))
        self.support_button.setText(_tr("Support the project"))
        self.repo_button.setText(_tr("GitHub repository"))
        self.license_button.setText(_tr("Open license"))

    def _open_url(self, url: str, action_name: str) -> None:
        try:
            if QDesktopServices.openUrl(QUrl(url)):
                return
        except Exception:
            logger.exception("Failed to open URL: %s", url)
        self.show_error(
            _tr("Could not open target."),
            title=action_name,
            informative_text=url,
        )

    def _open_local_path(self, path: Path, action_name: str) -> None:
        try:
            if not path.exists():
                self.show_error(
                    _tr("Missing target: {0}").format(str(path)),
                    title=action_name,
                )
                return
            if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                return
        except Exception:
            logger.exception("Failed to open local path: %s", path)
        self.show_error(
            _tr("Could not open target."),
            title=action_name,
            informative_text=str(path),
        )

    @staticmethod
    def _resolve_program_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return PathManager.base_root()

    @staticmethod
    def _resolve_license_path() -> Path:
        root = PathManager.base_root()
        direct = root / "LICENSE"
        if direct.exists():
            return direct
        fallback = root / "THIRD_PARTY_NOTICES.txt"
        return fallback


__all__ = ["AboutDialog"]
