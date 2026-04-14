"""Сервис безопасного доступа к виджетам с проверкой SIP."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QLayout, QSizePolicy, QWidget

from ..utils.qt_utils import is_deleted as _sip_isdeleted

if TYPE_CHECKING:
    from ..models.types import TopBarWindow


class WidgetAccessor:
    """Безопасный доступ к виджетам с проверкой на удаление через SIP."""

    def __init__(self, window: TopBarWindow) -> None:
        self.window = window
        self._container_widget: QWidget | None = None

    def safe_get(self, obj: Any | None, name: str) -> Any | None:
        """Безопасно получить атрибут объекта с проверкой SIP."""
        if obj is None or (isinstance(obj, QObject) and _sip_isdeleted(obj)):
            return None
        try:
            return getattr(obj, name, None)
        except RuntimeError:
            return None

    def get_top_bar(self) -> QLayout | None:
        """Получить layout топ-бара."""
        for attr in ["top_bar_host", "content_container"]:
            host = self.safe_get(self.window, attr)
            if isinstance(host, QWidget):
                layout = host.layout()
                if layout:
                    return layout
        return None

    def get_container_widget(self) -> QWidget | None:
        """Получить контейнер топ-бара с кэшированием."""
        if self._container_widget and not _sip_isdeleted(self._container_widget):
            return self._container_widget
        self._container_widget = self.safe_get(
            self.window, "top_bar_host"
        ) or self.safe_get(self.window, "content_container")
        return self._container_widget

    def clear_cache(self) -> None:
        """Очистить кэш виджетов."""
        self._container_widget = None

    def ensure_fixed_heights(self) -> None:
        """Принудительно зафиксировать высоту top-bar контейнера."""
        try:
            from app.config_data.runtime_config import runtime_app_config as app_config
            self._fix_top_bar_height(app_config)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to fix top bar height: {e}")

    def _fix_top_bar_height(self, app_config) -> None:
        """Фиксируем высоту топбара."""
        container = self.get_container_widget()
        if isinstance(container, QWidget) and not _sip_isdeleted(container):
            try:
                # Получаем высоту из конфигурации или используем безопасное значение
                try:
                    height = int(app_config.ui.get_top_bar_height())
                except (AttributeError, ValueError, TypeError):
                    height = 40  # Безопасное значение по умолчанию

                # Устанавливаем фиксированную высоту
                container.setFixedHeight(height)
                container.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to fix top bar height: {e}")
