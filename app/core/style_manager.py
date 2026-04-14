"""Centralized stylesheet loader and applier."""

from __future__ import annotations

from pathlib import Path

from app.core.log_manager import LogManager
from app.core.paths.path_manager import PathManager


class StyleManager:
    """Static API for loading and applying QSS themes."""

    @staticmethod
    def apply_theme(qss_content: str) -> bool:
        """Apply a raw QSS string to QApplication."""
        return StyleManager.apply_qss_string(qss_content)

    @staticmethod
    def apply_qss_string(qss_content: str) -> bool:
        """Apply a QSS string to QApplication."""
        if not qss_content or not str(qss_content).strip():
            StyleManager._safe_log("QSS content is empty")
            return False

        try:
            from PyQt6.QtWidgets import QApplication
        except Exception:
            StyleManager._safe_log("PyQt6 not available for style application")
            return False

        app = QApplication.instance()
        if app is None:
            StyleManager._safe_log("QApplication instance not found")
            return False

        try:
            app.setStyleSheet(qss_content)
            return True
        except Exception as exc:
            StyleManager._safe_log(f"Failed to apply QSS: {exc}")
            return False

    @staticmethod
    def _resolve_qss_path(theme_name: str) -> Path:
        filename = (
            theme_name if theme_name.lower().endswith(".qss") else f"{theme_name}.qss"
        )
        return PathManager.get_resource_path(Path("qss") / filename)

    @staticmethod
    def load_qss_file(theme_name: str) -> str | None:
        """Load QSS content by theme name from resources."""
        if not theme_name or not str(theme_name).strip():
            StyleManager._safe_log("Theme name is empty")
            return None

        qss_path = StyleManager._resolve_qss_path(str(theme_name).strip())
        if not qss_path.exists() or not qss_path.is_file():
            StyleManager._safe_log(f"QSS file not found: {qss_path}")
            return None

        try:
            return qss_path.read_text(encoding="utf-8")
        except OSError as exc:
            StyleManager._safe_log(f"Failed to read QSS {qss_path}: {exc}")
            return None

    @staticmethod
    def _safe_log(message: str) -> None:
        try:
            LogManager.get_logger("app.style_manager").warning(message)
        except Exception:
            pass
