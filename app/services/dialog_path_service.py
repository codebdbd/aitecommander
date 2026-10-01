"""Service for resolving initial directories and remembering user choices in file dialogs."""

import os
from pathlib import Path
from PyQt6.QtCore import QSettings, QStandardPaths

from app.config_data import app_config


class DialogPathService:
    """Centralized service for managing start directories in QFileDialog."""

    @classmethod
    def _get_settings(cls) -> QSettings:
        """Return properly scoped QSettings instance matching application settings."""
        return QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            app_config.get_org_name(),
            app_config.get_app_name(),
        )

    @classmethod
    def get_programs_dir(cls) -> str:
        """Return last used programs directory or fallback to system Program Files."""
        settings = cls._get_settings()
        saved = settings.value("FilePicker/LastDir_Programs", "", type=str)
        if saved and Path(saved).is_dir():
            return os.path.normpath(saved)
        prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        if Path(prog_files).is_dir():
            return os.path.normpath(prog_files)
        app_loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.ApplicationsLocation)
        return os.path.normpath(app_loc) if app_loc and Path(app_loc).is_dir() else str(Path.home())

    @classmethod
    def get_downloads_dir(cls, context: str = "General") -> str:
        """Return last used directory for given context or fallback to Downloads folder."""
        settings = cls._get_settings()
        saved = settings.value(f"FilePicker/LastDir_{context}", "", type=str)
        if saved and Path(saved).is_dir():
            return os.path.normpath(saved)
        dl = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if dl and Path(dl).is_dir():
            return os.path.normpath(dl)
        return str(Path.home())

    @classmethod
    def remember_dir(cls, context: str, chosen_path: str | Path | None) -> None:
        """Save folder of chosen file in QSettings for the given context."""
        if not chosen_path:
            return
        p = Path(chosen_path)
        folder = os.path.normpath(str(p if p.is_dir() else p.parent))
        if folder and Path(folder).is_dir():
            cls._get_settings().setValue(f"FilePicker/LastDir_{context}", folder)
