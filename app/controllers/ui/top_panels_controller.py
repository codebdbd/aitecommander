# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


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

    # Публичные методы -----------------------------------------------------
    def refresh_all(self) -> None:
        """Обновить обе панели: избранное и недавние."""
        self.refresh_favorites()
        self.refresh_recent()

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
