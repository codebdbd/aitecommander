# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

import logging
from PyQt6.QtCore import QTimer
from app.interfaces import FavoritesPanelLike, RecentsPanelLike, RecentsPanelWithLimit


logger = logging.getLogger(__name__)


_DEFAULT_DEBOUNCE_MS = 150


class TopPanelsController:
    """Контроллер верхних панелей (Избранное/Недавние)."""

    def __init__(self, main_window, *, fav_widget: FavoritesPanelLike, recent_links_widget: RecentsPanelLike, links_business=None):
        self.main = main_window
        if fav_widget is None or recent_links_widget is None:
            raise ValueError(
                "TopPanelsController requires fav_widget and recent_links_widget"
            )
        # Жёсткая проверка рантайм-совместимости с Protocol
        if not isinstance(fav_widget, FavoritesPanelLike):
            raise TypeError("fav_widget must implement FavoritesPanelLike")
        if not isinstance(recent_links_widget, RecentsPanelLike):
            raise TypeError("recent_links_widget must implement RecentsPanelLike")
        self.fav_widget = fav_widget
        self.recent_links_widget = recent_links_widget
        self.links_business = links_business

        self._pending_refresh = False
        self._pending_fav_refresh = False
        self._pending_recent_refresh = False
        self._refresh_timer = QTimer()
        self._fav_refresh_timer = QTimer()
        self._recent_refresh_timer = QTimer()
        self._structure_refresh_timer = QTimer()
        self._clearing_favorites = False
        try:
            self._refresh_timer.setParent(self.main)  # type: ignore[arg-type]
            self._fav_refresh_timer.setParent(self.main)  # type: ignore[arg-type]
            self._recent_refresh_timer.setParent(self.main)  # type: ignore[arg-type]
            self._structure_refresh_timer.setParent(self.main)  # type: ignore[arg-type]
        except Exception:
            pass
        self._refresh_timer.setSingleShot(True)
        self._fav_refresh_timer.setSingleShot(True)
        self._recent_refresh_timer.setSingleShot(True)
        self._structure_refresh_timer.setSingleShot(True)
        try:
            self._structure_refresh_timer.setInterval(200)
        except Exception:
            pass
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)
        self._fav_refresh_timer.timeout.connect(self._on_fav_refresh_timeout)
        self._recent_refresh_timer.timeout.connect(self._on_recent_refresh_timeout)
        self._structure_refresh_timer.timeout.connect(self._on_structure_refresh_timeout)

    def refresh_all(self) -> None:
        """Обновить обе панели: избранное и недавние."""
        self.refresh_favorites()
        self.refresh_recent()

    def request_refresh(self, delay_ms: int | None = None, *args, **kwargs) -> None:
        """Запросить обновление верхних панелей с дебаунсом."""
        try:
            if self._pending_refresh and self._refresh_timer.isActive():
                return
            self._pending_refresh = True
            delay = self._normalize_delay(delay_ms, args, kwargs)
            self._refresh_timer.start(delay)
        except Exception:
            logger.exception("TopPanelsController.request_refresh failed")
            self._pending_refresh = False

    def request_favorites_refresh(self, delay_ms: int | None = None, *args, **kwargs) -> None:
        """Запросить обновление только панели избранного с дебаунсом."""
        try:
            if self._pending_fav_refresh and self._fav_refresh_timer.isActive():
                return
            self._pending_fav_refresh = True
            delay = self._normalize_delay(delay_ms, args, kwargs)
            self._fav_refresh_timer.start(delay)
        except Exception:
            logger.exception("TopPanelsController.request_favorites_refresh failed")
            self._pending_fav_refresh = False

    def request_recents_refresh(self, delay_ms: int | None = None, *args, **kwargs) -> None:
        """Запросить обновление только панели недавних ссылок с дебаунсом."""
        try:
            if self._pending_recent_refresh and self._recent_refresh_timer.isActive():
                return
            self._pending_recent_refresh = True
            delay = self._normalize_delay(delay_ms, args, kwargs)
            self._recent_refresh_timer.start(delay)
        except Exception:
            logger.exception("TopPanelsController.request_recents_refresh failed")
            self._pending_recent_refresh = False

    def refresh_favorites(self) -> None:
        widget = self.fav_widget
        try:
            if self.links_business is not None:
                items = self.links_business.get_favorite_links()
                widget.set_favorites(items)
        except Exception as e:
            logger.exception("TopPanelsController.refresh_favorites: ошибка при загрузке/установке избранного")

    def refresh_recent(self) -> None:
        widget = self.recent_links_widget
        # Определяем лимит через расширенный протокол, без hasattr
        limit = 10
        if isinstance(widget, RecentsPanelWithLimit):
            try:
                val = widget.get_limit()
                if isinstance(val, int) and val > 0:
                    limit = val
            except (TypeError, ValueError):
                # некорректное значение лимита — оставляем default
                pass

        items = []
        if self.links_business is not None:
            try:
                items = self.links_business.get_recent_links(limit)
            except (TypeError, ValueError):
                logger.error("TopPanelsController.refresh_recent: неверные аргументы при загрузке недавних", exc_info=True)
                return
            except Exception:
                logger.exception("TopPanelsController.refresh_recent: неожиданная ошибка при загрузке недавних")
                return

        try:
            widget.set_recent_links(items)
        except (TypeError, ValueError):
            logger.error("TopPanelsController.refresh_recent: ошибка сигнатуры при установке недавних", exc_info=True)
        except Exception:
            logger.exception("TopPanelsController.refresh_recent: неожиданная ошибка при установке недавних")

    def clear_favorites(self) -> None:
        widget = self.fav_widget
        if not widget:
            return
        if self._clearing_favorites:
            return
        self._clearing_favorites = True
        try:
            try:
                if self.links_business is not None and hasattr(self.links_business, "clear_favorites"):
                    self.links_business.clear_favorites()
            except Exception:
                logger.exception("TopPanelsController.clear_favorites: ошибка при очистке избранного в БД")

            if hasattr(widget, "clear_favorites"):
                try:
                    widget.clear_favorites()
                except Exception:
                    logger.exception("TopPanelsController.clear_favorites: ошибка при очистке избранного")
            else:
                try:
                    if hasattr(widget, "set_favorites"):
                        widget.set_favorites([])
                    try:
                        widget.setVisible(False)
                    except Exception:
                        pass
                except Exception:
                    logger.exception("TopPanelsController.clear_favorites: ошибка при программной очистке избранного")
        finally:
            self._clearing_favorites = False

    def schedule_structure_refresh(self) -> None:
        """Запланировать обновление верхних панелей по структурным событиям с фиксированным интервалом."""
        timer = self._structure_refresh_timer
        try:
            # Интервал фиксирован, задаётся в __init__ (по умолчанию 200 мс)
            if timer.isActive():
                return
            timer.start()
        except (ValueError, RuntimeError):
            # Ожидаемые ошибки — логируем, без немедленного обновления
            logger.error("TopPanelsController.schedule_structure_refresh: failed to start structure timer", exc_info=True)
        except Exception:
            # Неожиданные ошибки логируем, повторных обновлений не делаем
            logger.exception("TopPanelsController.schedule_structure_refresh: unexpected error")


    def _on_refresh_timeout(self) -> None:
        try:
            self.refresh_all()
        finally:
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

    def _on_structure_refresh_timeout(self) -> None:
        """Единый обработчик таймаута для структурных событий."""
        try:
            self.request_refresh()
        except (ValueError, RuntimeError):
            logger.error("TopPanelsController._on_structure_refresh_timeout: expected error during request_refresh", exc_info=True)
        except Exception:
            # Неожиданная ошибка — только лог, без повторного обновления
            logger.exception("TopPanelsController._on_structure_refresh_timeout: unexpected error")

    def _normalize_delay(self, delay_ms, args, kwargs) -> int:
        """Безопасно привести задержку к int; игнорирует нерелевантные payload сигналов."""
        cand = delay_ms
        if cand is None and args:
            first = args[0]
            if isinstance(first, (int, float)) or (isinstance(first, str) and first.isdigit()):
                cand = first
        try:
            val = int(cand) if cand is not None else _DEFAULT_DEBOUNCE_MS
            if val < 0:
                return _DEFAULT_DEBOUNCE_MS
            return val
        except Exception:
            return _DEFAULT_DEBOUNCE_MS

