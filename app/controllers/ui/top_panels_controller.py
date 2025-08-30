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

    def __init__(self, main_window, *, fav_widget, recent_links_widget, links_business=None):
        self.main = main_window
        # Жесткая проверка зависимостей: упасть рано, чем тихо игнорировать обновления
        if fav_widget is None or recent_links_widget is None:
            raise ValueError(
                "TopPanelsController requires fav_widget and recent_links_widget"
            )
        self.fav_widget = fav_widget
        self.recent_links_widget = recent_links_widget
        # links_business может быть None в юнит-тестах; в проде передаётся явно через setup
        self.links_business = links_business

        # Дебаунс-таймер обновления верхних панелей
        self._pending_refresh = False
        self._pending_fav_refresh = False
        self._pending_recent_refresh = False
        # Не завязываемся жёстко на QObject-родителя (в тестах может быть SimpleNamespace)
        self._refresh_timer = QTimer()
        self._fav_refresh_timer = QTimer()
        self._recent_refresh_timer = QTimer()
        try:
            # Назначаем родителя, если это QObject
            self._refresh_timer.setParent(self.main)  # type: ignore[arg-type]
            self._fav_refresh_timer.setParent(self.main)  # type: ignore[arg-type]
            self._recent_refresh_timer.setParent(self.main)  # type: ignore[arg-type]
        except Exception:
            pass
        self._refresh_timer.setSingleShot(True)
        self._fav_refresh_timer.setSingleShot(True)
        self._recent_refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)
        self._fav_refresh_timer.timeout.connect(self._on_fav_refresh_timeout)
        self._recent_refresh_timer.timeout.connect(self._on_recent_refresh_timeout)

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

    def request_favorites_refresh(self, delay_ms: int | None = None) -> None:
        """Запросить обновление только панели избранного с дебаунсом."""
        try:
            if self._pending_fav_refresh and self._fav_refresh_timer.isActive():
                return
            self._pending_fav_refresh = True
            delay = int(delay_ms or _DEFAULT_DEBOUNCE_MS)
            self._fav_refresh_timer.start(delay)
        except Exception:
            logger.exception("TopPanelsController.request_favorites_refresh: unexpected error; running immediate refresh")
            self._pending_fav_refresh = False
            self.refresh_favorites()

    def request_recents_refresh(self, delay_ms: int | None = None) -> None:
        """Запросить обновление только панели недавних ссылок с дебаунсом."""
        try:
            if self._pending_recent_refresh and self._recent_refresh_timer.isActive():
                return
            self._pending_recent_refresh = True
            delay = int(delay_ms or _DEFAULT_DEBOUNCE_MS)
            self._recent_refresh_timer.start(delay)
        except Exception:
            logger.exception("TopPanelsController.request_recents_refresh: unexpected error; running immediate refresh")
            self._pending_recent_refresh = False
            self.refresh_recent()

    def refresh_favorites(self) -> None:
        widget = self.fav_widget
        try:
            if self.links_business is not None:
                items = self.links_business.get_favorite_links()
                if widget and hasattr(widget, "set_favorites"):
                    widget.set_favorites(items)
            # Back-compat: вызывать update_favorites(), чтобы сторонние хуки и тесты сработали
            if widget and hasattr(widget, "update_favorites"):
                try:
                    widget.update_favorites()
                except Exception:
                    # Сообщение должно содержать имя метода для ожиданий тестов
                    logger.exception("TopPanelsController.refresh_favorites: ошибка при update_favorites")
        except Exception:
            logger.exception("TopPanelsController.refresh_favorites: ошибка при загрузке/установке избранного")

    def refresh_recent(self) -> None:
        widget = self.recent_links_widget
        try:
            # Пытаемся определить лимит из виджета, иначе берём дефолт
            limit = None
            try:
                if widget is not None:
                    if hasattr(widget, "limit"):
                        limit = int(getattr(widget, "limit"))
                    elif hasattr(widget, "max_items"):
                        limit = int(getattr(widget, "max_items"))
            except Exception:
                limit = None
            if limit is None:
                limit = 20
            if self.links_business is not None:
                items = self.links_business.get_recent_links(limit)
                if widget and hasattr(widget, "set_recent_links"):
                    widget.set_recent_links(items)
            # Back-compat: вызвать update_recent_links() для внешних слушателей/тестов
            if widget and hasattr(widget, "update_recent_links"):
                try:
                    widget.update_recent_links()
                except Exception:
                    logger.exception("TopPanelsController.refresh_recent: ошибка при update_recent_links")
        except Exception:
            logger.exception("TopPanelsController.refresh_recent: ошибка при загрузке/установке недавних")

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

    def _on_fav_refresh_timeout(self) -> None:
        try:
            self.refresh_favorites()
        finally:
            self._pending_fav_refresh = False

    def _on_recent_refresh_timeout(self) -> None:
        try:
            self.refresh_recent()
        finally:
            self._pending_recent_refresh = False

    # Обработчики refresh_requested удалены — контроллер сам получает данные в refresh_* и не вызывает widget.update_*
