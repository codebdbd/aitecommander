# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

import logging
from PyQt6.QtCore import QTimer


logger = logging.getLogger(__name__)


_DEFAULT_DEBOUNCE_MS = 150


class TopPanelsController:
    """Контроллер верхних панелей (Избранное/Недавние).
    Инкапсулирует обновление и очистку панелей, чтобы View (MainWindow) не знал деталей.
    """

    def __init__(self, main_window, *, fav_widget, recent_links_widget):
        self.main = main_window
        # Жесткая проверка зависимостей: упасть рано, чем тихо игнорировать обновления
        if fav_widget is None or recent_links_widget is None:
            raise ValueError(
                "TopPanelsController requires both fav_widget and recent_links_widget"
            )
        self.fav_widget = fav_widget
        self.recent_links_widget = recent_links_widget

        # Дебаунс-таймер обновления верхних панелей
        self._pending_refresh = False
        # Не завязываемся жёстко на QObject-родителя (в тестах может быть SimpleNamespace)
        self._refresh_timer = QTimer()
        try:
            # Назначаем родителя, если это QObject
            self._refresh_timer.setParent(self.main)  # type: ignore[arg-type]
        except Exception:
            pass
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)

    # Публичные методы -----------------------------------------------------
    def refresh_all(self) -> None:
        """Обновить обе панели: избранное и недавние."""
        self.refresh_favorites()
        self.refresh_recent()

    def request_refresh(self, delay_ms: int | None = None) -> None:
        """Запросить обновление верхних панелей с дебаунсом."""
        try:
            if self._pending_refresh and self._refresh_timer.isActive():
                return
            self._pending_refresh = True
            delay = int(delay_ms or _DEFAULT_DEBOUNCE_MS)
            self._refresh_timer.start(delay)
        except Exception:
            # В случае неожиданных проблем с таймером выполняем немедленное обновление
            logger.exception("TopPanelsController.request_refresh: unexpected error; running immediate refresh")
            self._pending_refresh = False
            self.refresh_all()

    def refresh_favorites(self) -> None:
        widget = self.fav_widget
        if widget:
            try:
                widget.update_favorites()
            except Exception:
                logger.exception("TopPanelsController.refresh_favorites: ошибка при обновлении избранного")

    def refresh_recent(self) -> None:
        widget = self.recent_links_widget
        if widget:
            try:
                widget.update_recent_links()
            except Exception:
                logger.exception("TopPanelsController.refresh_recent: ошибка при обновлении недавних ссылок")

    def clear_favorites(self) -> None:
        widget = self.fav_widget
        if widget:
            try:
                widget.clear_favorites()
            except Exception:
                logger.exception("TopPanelsController.clear_favorites: ошибка при очистке избранного")

    # --- internals ---
    def _on_refresh_timeout(self) -> None:
        try:
            self.refresh_all()
        finally:
            # Гарантированно сбрасываем флаг, даже если refresh_all упал
            self._pending_refresh = False
