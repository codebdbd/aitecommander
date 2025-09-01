# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

import logging
import os
from PyQt6.QtCore import QTimer
from app.interfaces import FavoritesPanelLike, FavoritesPanelWithClear, RecentsPanelLike, RecentsPanelWithLimit


logger = logging.getLogger(__name__)


_DEFAULT_DEBOUNCE_MS = 150


class TopPanelsController:
    """Контроллер верхних панелей (Избранное/Недавние)."""

    def __init__(self, main_window, *, fav_widget: FavoritesPanelLike, recent_links_widget: RecentsPanelLike, links_business):
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
        if links_business is None:
            raise ValueError("TopPanelsController requires links_business")
        self.links_business = links_business

        self._pending_refresh = False
        self._pending_fav_refresh = False
        self._pending_recent_refresh = False
        self._refresh_timer = QTimer()
        self._fav_refresh_timer = QTimer()
        self._recent_refresh_timer = QTimer()
        self._structure_refresh_timer = QTimer()
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

        # Strict-режим: при неожиданных исключениях в refresh_* повторно выбрасывать
        self._strict = str(os.getenv("APP_TOP_PANELS_STRICT", "")).lower() in {"1", "true", "yes", "on"}

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
        except (TypeError, ValueError) as e:
            logger.error("TopPanelsController.request_refresh: invalid args: %s", e)
            self._pending_refresh = False
        except Exception:
            logger.exception("TopPanelsController.request_refresh: unexpected failure")
            self._pending_refresh = False
            raise

    def request_favorites_refresh(self, delay_ms: int | None = None, *args, **kwargs) -> None:
        """Запросить обновление только панели избранного с дебаунсом."""
        try:
            if self._pending_fav_refresh and self._fav_refresh_timer.isActive():
                return
            self._pending_fav_refresh = True
            delay = self._normalize_delay(delay_ms, args, kwargs)
            self._fav_refresh_timer.start(delay)
        except (TypeError, ValueError) as e:
            logger.error("TopPanelsController.request_favorites_refresh: invalid args: %s", e)
            self._pending_fav_refresh = False
        except Exception:
            logger.exception("TopPanelsController.request_favorites_refresh: unexpected failure")
            self._pending_fav_refresh = False
            raise

    def request_recents_refresh(self, delay_ms: int | None = None, *args, **kwargs) -> None:
        """Запросить обновление только панели недавних ссылок с дебаунсом."""
        try:
            if self._pending_recent_refresh and self._recent_refresh_timer.isActive():
                return
            self._pending_recent_refresh = True
            delay = self._normalize_delay(delay_ms, args, kwargs)
            self._recent_refresh_timer.start(delay)
        except (TypeError, ValueError) as e:
            logger.error("TopPanelsController.request_recents_refresh: invalid args: %s", e)
            self._pending_recent_refresh = False
        except Exception:
            logger.exception("TopPanelsController.request_recents_refresh: unexpected failure")
            self._pending_recent_refresh = False
            raise

    def refresh_favorites(self) -> None:
        widget = self.fav_widget
        # 1) Загрузка данных из бизнес-слоя
        items: list = []
        try:
            items = self.links_business.get_favorite_links()
        except (TypeError, ValueError):
            logger.error("TopPanelsController.refresh_favorites: invalid data from business", exc_info=True)
            return
        except Exception:
            logger.exception("TopPanelsController.refresh_favorites failed: business layer error")
            if self._strict:
                raise
            return

        # 2) Обновление виджета
        try:
            widget.set_favorites(items)
        except (TypeError, ValueError):
            logger.error("TopPanelsController.refresh_favorites: widget set_favorites signature error", exc_info=True)
        except Exception:
            logger.exception("TopPanelsController.refresh_favorites failed: widget update error")
            if self._strict:
                raise

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

        # 1) Загрузка данных из бизнес-слоя
        items: list = []
        try:
            items = self.links_business.get_recent_links(limit)
        except (TypeError, ValueError):
            logger.error("TopPanelsController.refresh_recent: invalid args/data during recent load", exc_info=True)
            return
        except Exception:
            logger.exception("TopPanelsController.refresh_recent failed: business layer error")
            if self._strict:
                raise
            return

        # 2) Обновление виджета
        try:
            widget.set_recent_links(items)
        except (TypeError, ValueError):
            logger.error("TopPanelsController.refresh_recent: widget set_recent_links signature error", exc_info=True)
        except Exception:
            logger.exception("TopPanelsController.refresh_recent failed: widget update error")
            if self._strict:
                raise

    def clear_favorites(self) -> None:
        """Очистить избранное: бизнес-данные и виджет.

        Без вложенных try/except и без временных флагов. Ошибки логируем и не
        пробрасываем наружу, чтобы не ронять UI-цепочку событий.
        """
        # 1) Бизнес-очистка
        try:
            if self.links_business is not None:
                self.links_business.clear_favorites()
        except Exception:
            logger.error("TopPanelsController.clear_favorites: error in links_business.clear_favorites", exc_info=True)

        # 2) Очистка виджета
        try:
            # Предпочитаем нативный метод очистки
            if isinstance(self.fav_widget, FavoritesPanelWithClear):
                self.fav_widget.clear_favorites()
            else:
                # Фолбэк на set_favorites([]) при отсутствии расширенного протокола
                self.fav_widget.set_favorites([])
        except AttributeError:
            # Контракт сломан — пробуем мягкий откат через set_favorites([])
            try:
                self.fav_widget.set_favorites([])
            except Exception:
                logger.error("TopPanelsController.clear_favorites: widget fallback set_favorites failed", exc_info=True)
        except Exception:
            logger.error("TopPanelsController.clear_favorites: widget clear failed", exc_info=True)

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

