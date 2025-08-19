# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

from typing import Optional


class TopPanelsController:
    """Контроллер верхних панелей (Избранное/Недавние).
    Инкапсулирует обновление и очистку панелей, чтобы View (MainWindow) не знал деталей.
    """

    def __init__(self, main_window):
        self.main = main_window

    # Публичные методы -----------------------------------------------------
    def refresh_all(self) -> None:
        """Обновить обе панели: избранное и недавние."""
        self.refresh_favorites()
        self.refresh_recent()

    def refresh_favorites(self) -> None:
        widget = getattr(self.main, 'fav_widget', None)
        if widget and hasattr(widget, 'update_favorites'):
            try:
                widget.update_favorites()
            except Exception:
                pass

    def refresh_recent(self) -> None:
        widget = getattr(self.main, 'recent_links_widget', None)
        if widget and hasattr(widget, 'update_recent_links'):
            try:
                widget.update_recent_links()
            except Exception:
                pass

    def clear_favorites(self) -> None:
        widget = getattr(self.main, 'fav_widget', None)
        if widget and hasattr(widget, 'clear_favorites'):
            try:
                widget.clear_favorites()
            except Exception:
                pass
