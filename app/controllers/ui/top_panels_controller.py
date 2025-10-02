# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from app.interfaces import TopPanelDataLike, FavoritesPanelWithClear, RecentsPanelWithLimit

from .types import (
    LinksBusinessProtocol,
    SupportsGetLimit,
    SupportsSetFavorites,
    SupportsSetRecentLinks,
)

logger = logging.getLogger(__name__)


_DEFAULT_DEBOUNCE_MS = 150


class SetupError(Exception):
    """Ошибка конфигурации/настройки TopPanelsController."""


class TopPanelsController(QObject):
    """Контроллер верхних панелей (Избранное/Недавние)."""
    
    # ИСПРАВЛЕНИЕ: Сигнал для уведомления о завершении загрузки данных
    data_loaded = pyqtSignal()

    def __init__(
        self,
        main_window,
        *,
        fav_widget: TopPanelDataLike,
        recent_links_widget: TopPanelDataLike,
        links_business: LinksBusinessProtocol,
    ):
        parent_obj = main_window if isinstance(main_window, QObject) else None
        super().__init__(parent=parent_obj)
        self.main = main_window
        if fav_widget is None or recent_links_widget is None:
            raise ValueError(
                "TopPanelsController requires fav_widget and recent_links_widget"
            )
        if not self._supports_favorites_widget(fav_widget):
            raise TypeError(
                "fav_widget must provide set_data(items) or legacy set_favorites(items)"
            )
        if not self._supports_recent_widget(recent_links_widget):
            raise TypeError(
                "recent_links_widget must provide set_data(items) or legacy set_recent_links(items)"
            )
        self.fav_widget = fav_widget
        self.recent_links_widget = recent_links_widget
        if links_business is None:
            raise ValueError("TopPanelsController requires links_business")
        self.links_business: LinksBusinessProtocol = links_business

        self._pending_refresh = False
        self._pending_fav_refresh = False
        self._pending_recent_refresh = False
        self._refresh_timer = QTimer(self)
        self._fav_refresh_timer = QTimer(self)
        self._recent_refresh_timer = QTimer(self)
        self._structure_refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._fav_refresh_timer.setSingleShot(True)
        self._recent_refresh_timer.setSingleShot(True)
        self._structure_refresh_timer.setSingleShot(True)
        self._structure_refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)
        self._fav_refresh_timer.timeout.connect(self._on_fav_refresh_timeout)
        self._recent_refresh_timer.timeout.connect(self._on_recent_refresh_timeout)
        self._structure_refresh_timer.timeout.connect(
            self._on_structure_refresh_timeout
        )

        self._async_supported = self._connect_business_signals()

        # Strict-режим: при неожиданных исключениях в refresh_* повторно выбрасывать
        self._strict = str(os.getenv("APP_TOP_PANELS_STRICT", "").lower()) in {
            "1",
            "true",
            "yes",
            "on",
        }

    def refresh_all(self) -> None:
        """Обновить обе панели: избранное и недавние.
        
        ИСПРАВЛЕНИЕ: Испускает сигнал data_loaded после завершения загрузки.
        """
        self.refresh_favorites()
        self.refresh_recent()
        # Испускаем сигнал о завершении загрузки данных
        self.data_loaded.emit()

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

    def request_favorites_refresh(
        self, delay_ms: int | None = None, *args, **kwargs
    ) -> None:
        """Запросить обновление только панели избранного с дебаунсом."""
        try:
            if self._pending_fav_refresh and self._fav_refresh_timer.isActive():
                return
            self._pending_fav_refresh = True
            delay = self._normalize_delay(delay_ms, args, kwargs)
            self._fav_refresh_timer.start(delay)
        except (TypeError, ValueError) as e:
            logger.error(
                "TopPanelsController.request_favorites_refresh: invalid args: %s", e
            )
            self._pending_fav_refresh = False
        except Exception:
            logger.exception(
                "TopPanelsController.request_favorites_refresh: unexpected failure"
            )
            self._pending_fav_refresh = False
            raise

    def request_recents_refresh(
        self, delay_ms: int | None = None, *args, **kwargs
    ) -> None:
        """Запросить обновление только панели недавних ссылок с дебаунсом."""
        try:
            if self._pending_recent_refresh and self._recent_refresh_timer.isActive():
                return
            self._pending_recent_refresh = True
            delay = self._normalize_delay(delay_ms, args, kwargs)
            self._recent_refresh_timer.start(delay)
        except (TypeError, ValueError) as e:
            logger.error(
                "TopPanelsController.request_recents_refresh: invalid args: %s", e
            )
            self._pending_recent_refresh = False
        except Exception:
            logger.exception(
                "TopPanelsController.request_recents_refresh: unexpected failure"
            )
            self._pending_recent_refresh = False
            raise

    def refresh_favorites(self) -> None:
        """Обновление избранного.

        По умолчанию — асинхронная загрузка через LinksBusinessLogic.load_favorite_links().
        Если метод/сигнал недоступен (моки в тестах), используем синхронный fallback
        к get_favorite_links() с прежней обработкой ошибок и обновлением виджета.
        """
        # 1) Пытаемся асинхронно (только если это реальный LinksBusinessLogic с сигналами)
        if self._async_supported and callable(
            getattr(self.links_business, "load_favorite_links", None)
        ):
            try:
                self.links_business.load_favorite_links()
                return
            except (TypeError, ValueError) as exc:
                logger.error(
                    "TopPanelsController.refresh_favorites: invalid args for async call: %s",
                    exc,
                    exc_info=True,
                )
            except Exception:
                logger.exception(
                    "TopPanelsController.refresh_favorites: failed to call load_favorite_links"
                )
                if self._strict:
                    raise
            # Логируем ошибку вызова async-метода и переходим к синхронному пути
            # В строгом режиме не выполняем fallback, чтобы выявлять ошибки конфигурации
            if self._strict:
                raise

        # 2) Синхронный fallback — поведение как раньше (для тестов и простых окружений)
        widget = self.fav_widget
        items: list = []
        try:
            items = self.links_business.get_favorite_links()
        except (TypeError, ValueError):
            logger.error(
                "TopPanelsController.refresh_favorites: invalid data from business",
                exc_info=True,
            )
            return
        except Exception:
            logger.exception(
                "TopPanelsController.refresh_favorites failed: business layer error"
            )
            if self._strict:
                raise
            return

        try:
            if callable(getattr(widget, "set_data", None)):
                widget.set_data(items)  # type: ignore[call-arg]
            elif callable(getattr(widget, "set_favorites", None)):
                widget.set_favorites(items)  # type: ignore[attr-defined]
            else:
                raise AttributeError("favorites widget lacks set_data/set_favorites")
        except (TypeError, ValueError):
            logger.error(
                "TopPanelsController.refresh_favorites: widget set_favorites signature error",
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "TopPanelsController.refresh_favorites failed: widget update error"
            )
            if self._strict:
                raise

    def refresh_recent(self) -> None:
        """Обновление недавних ссылок.

        По умолчанию — асинхронная загрузка через LinksBusinessLogic.load_recent_links(limit).
        Если метод/сигнал недоступен (моки в тестах), используем синхронный fallback
        к get_recent_links(limit) с прежней обработкой ошибок и обновлением виджета.
        """
        widget = self.recent_links_widget
        # Определяем лимит
        limit = 10
        try:
            if isinstance(widget, (RecentsPanelWithLimit, SupportsGetLimit)):
                val = widget.get_limit()  # type: ignore[attr-defined]
                if isinstance(val, int) and val > 0:
                    limit = val
        except (TypeError, ValueError):
            pass

        # 1) Пытаемся асинхронно (только если это реальный LinksBusinessLogic с сигналами)
        try:
            if self._async_supported and callable(
                getattr(self.links_business, "load_recent_links", None)
            ):
                self.links_business.load_recent_links(limit)
                return
        except (TypeError, ValueError) as exc:
            logger.error(
                "TopPanelsController.refresh_recent: invalid args for async call: %s",
                exc,
                exc_info=True,
            )
        except Exception:
            # Логируем ошибку вызова async-метода и переходим к синхронному пути
            logger.exception(
                "TopPanelsController.refresh_recent: failed to call load_recent_links"
            )
            if self._strict:
                raise

        # 2) Синхронный fallback — прежняя логика
        items: list = []
        try:
            items = self.links_business.get_recent_links(limit)
        except (TypeError, ValueError):
            logger.error(
                "TopPanelsController.refresh_recent: invalid args/data during recent load",
                exc_info=True,
            )
            return
        except Exception:
            logger.exception(
                "TopPanelsController.refresh_recent failed: business layer error"
            )
            if self._strict:
                raise
            return

        try:
            if callable(getattr(widget, "set_data", None)):
                widget.set_data(items)  # type: ignore[call-arg]
            elif callable(getattr(widget, "set_recent_links", None)):
                widget.set_recent_links(items)  # type: ignore[attr-defined]
            else:
                raise AttributeError("recent widget lacks set_data/set_recent_links")
        except (TypeError, ValueError):
            logger.error(
                "TopPanelsController.refresh_recent: widget set_recent_links signature error",
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "TopPanelsController.refresh_recent failed: widget update error"
            )
            if self._strict:
                raise

    def clear_favorites(self) -> None:
        """Очистить избранное: бизнес-данные и виджет.

        Без вложенных try/except и без временных флагов. Ошибки логируем и не
        пробрасываем наружу, чтобы не ронять UI-цепочку событий.
        """
        # 1) Бизнес-очистка
        try:
            self.links_business.clear_favorites()
        except Exception:
            logger.exception(
                "TopPanelsController.clear_favorites: error in links_business.clear_favorites"
            )

        # 2) Обновление виджета через контролируемый путь без повторной эмиссии clear_requested
        #    (прямой вызов fav_widget.clear_favorites() вызывает clearRequested/clear_requested и цикл)
        try:
            self.refresh_favorites()
        except Exception:
            logger.exception(
                "TopPanelsController.clear_favorites: widget refresh after clear failed"
            )

    def schedule_structure_refresh(self) -> None:
        """Запланировать обновление верхних панелей по структурным событиям с фиксированным интервалом."""
        try:
            if self._structure_refresh_timer is None:
                raise SetupError("Structure refresh timer is not configured")
            # Интервал фиксирован, задаётся в __init__ (по умолчанию 200 мс)
            if self._structure_refresh_timer.isActive():
                return
            self._structure_refresh_timer.start()
            logger.debug(
                "TopPanelsController.schedule_structure_refresh: timer started"
            )
        except (ValueError, RuntimeError) as e:
            # Ожидаемые ошибки — логируем, без немедленного обновления
            logger.error(
                "TopPanelsController.schedule_structure_refresh: failed to start structure timer: %s",
                e,
                exc_info=True,
            )
            return
        except SetupError:
            raise
        except Exception:
            # Неожиданные ошибки — не скрываем тип исключения
            logger.exception(
                "TopPanelsController.schedule_structure_refresh: unexpected error"
            )
            raise

    @pyqtSlot()
    def _on_refresh_timeout(self) -> None:
        try:
            self.refresh_all()
        finally:
            self._pending_refresh = False

    @pyqtSlot()
    def _on_fav_refresh_timeout(self) -> None:
        try:
            self.refresh_favorites()
        finally:
            self._pending_fav_refresh = False

    @pyqtSlot()
    def _on_recent_refresh_timeout(self) -> None:
        try:
            self.refresh_recent()
        finally:
            self._pending_recent_refresh = False

    @pyqtSlot()
    def _on_structure_refresh_timeout(self) -> None:
        """Единый обработчик таймаута для структурных событий.

        Поведение при ошибках:
        - Любые ошибки внутри `request_refresh()` не должны оставлять таймер активным.
        - Таймер всегда останавливается в finally, чтобы избежать повторных попыток при сбое.
        Ожидаемый жизненный цикл: schedule -> timeout -> request_refresh -> stop.
        """
        try:
            self.request_refresh()
        except (ValueError, RuntimeError) as e:
            logger.error(
                "TopPanelsController._on_structure_refresh_timeout: expected error during request_refresh: %s",
                e,
                exc_info=True,
            )
        except SetupError:
            # Конфигурационная ошибка — пробрасываем наверх после логирования
            logger.exception(
                "TopPanelsController._on_structure_refresh_timeout: setup error"
            )
            raise
        finally:
            try:
                # Гарантированно останавливаем таймер, чтобы не было повторных вызовов при ошибке
                if (
                    self._structure_refresh_timer
                    and self._structure_refresh_timer.isActive()
                ):
                    self._structure_refresh_timer.stop()
            except Exception:
                # Безопасный best-effort stop
                logger.debug(
                    "TopPanelsController._on_structure_refresh_timeout: timer stop failed",
                    exc_info=False,
                )

    # --- Обработчики сигналов бизнес-слоя ---
    def _on_favorite_links_loaded(self, items: list[dict[str, object]] | list) -> None:
        widget = self.fav_widget
        try:
            if callable(getattr(widget, "set_data", None)):
                widget.set_data(items)  # type: ignore[call-arg]
            elif isinstance(widget, SupportsSetFavorites):
                # legacy fallback для тестовых стабов
                widget.set_favorites(items)  # type: ignore[attr-defined]
            else:
                raise AttributeError("favorites widget lacks set_data/set_favorites")
        except (TypeError, ValueError):
            logger.error(
                "TopPanelsController._on_favorite_links_loaded: widget signature error",
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "TopPanelsController._on_favorite_links_loaded: widget update error"
            )
            if self._strict:
                raise

    def _on_recent_links_loaded(self, items: list[dict[str, object]] | list) -> None:
        widget = self.recent_links_widget
        try:
            if callable(getattr(widget, "set_data", None)):
                widget.set_data(items)  # type: ignore[call-arg]
            elif isinstance(widget, SupportsSetRecentLinks):
                # legacy fallback для тестовых стабов
                widget.set_recent_links(items)  # type: ignore[attr-defined]
            else:
                raise AttributeError("recent widget lacks set_data/set_recent_links")
        except (TypeError, ValueError):
            logger.error(
                "TopPanelsController._on_recent_links_loaded: widget signature error",
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "TopPanelsController._on_recent_links_loaded: widget update error"
            )
            if self._strict:
                raise

    def _normalize_delay(self, delay_ms, args, kwargs) -> int:
        """Безопасно привести задержку к int; игнорирует нерелевантные payload сигналов."""
        cand = delay_ms
        if cand is None and args:
            first = args[0]
            if isinstance(first, (int, float)) or (
                isinstance(first, str) and first.isdigit()
            ):
                cand = first
        try:
            val = int(cand) if cand is not None else _DEFAULT_DEBOUNCE_MS
            if val < 0:
                return _DEFAULT_DEBOUNCE_MS
            return val
        except Exception:
            return _DEFAULT_DEBOUNCE_MS

    def _supports_favorites_widget(self, widget: object) -> bool:
        return callable(getattr(widget, "set_data", None)) or isinstance(
            widget, (SupportsSetFavorites, FavoritesPanelWithClear)
        )

    def _supports_recent_widget(self, widget: object) -> bool:
        return callable(getattr(widget, "set_data", None)) or isinstance(
            widget, (SupportsSetRecentLinks, RecentsPanelWithLimit)
        )

    def _connect_business_signals(self) -> bool:
        favorite_signal = getattr(self.links_business, "favorite_links_loaded", None)
        recent_signal = getattr(self.links_business, "recent_links_loaded", None)
        connected_all = True
        if hasattr(favorite_signal, "connect"):
            favorite_signal.connect(self._on_favorite_links_loaded)
        else:
            connected_all = False
            logger.debug(
                "TopPanelsController: business signal 'favorite_links_loaded' not present; falling back to sync mode"
            )
        if hasattr(recent_signal, "connect"):
            recent_signal.connect(self._on_recent_links_loaded)
        else:
            connected_all = False
            logger.debug(
                "TopPanelsController: business signal 'recent_links_loaded' not present; falling back to sync mode"
            )
        return connected_all
    
    def cleanup(self) -> None:
        """Останавливает таймеры и отключает сигналы при уничтожении.
        
        ИСПРАВЛЕНИЕ: Предотвращает утечки памяти от активных таймеров.
        Должно вызываться при закрытии главного окна.
        """
        # Останавливаем все таймеры
        timers = [
            self._refresh_timer,
            self._fav_refresh_timer,
            self._recent_refresh_timer,
            self._structure_refresh_timer,
        ]
        
        for timer in timers:
            if timer and timer.isActive():
                timer.stop()
        
        logger.debug("TopPanelsController: all timers stopped")
        
        # Отключаем сигналы business logic
        try:
            if hasattr(self.links_business, "favorite_links_loaded"):
                self.links_business.favorite_links_loaded.disconnect(self._on_favorite_links_loaded)
            if hasattr(self.links_business, "recent_links_loaded"):
                self.links_business.recent_links_loaded.disconnect(self._on_recent_links_loaded)
        except TypeError:  # Сигналы уже отключены
            pass
        except Exception as e:
            logger.warning("TopPanelsController cleanup: failed to disconnect signals: %s", e)
