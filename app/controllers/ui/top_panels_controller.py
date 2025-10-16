# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from app.interfaces import (
    FavoritesPanelWithClear,
    RecentsPanelWithLimit,
    TopPanelDataLike,
)

from .types import (
    LinksBusinessProtocol,
    SupportsGetLimit,
    SupportsSetFavorites,
    SupportsSetRecentLinks,
)

logger = logging.getLogger(__name__)


_DEFAULT_DEBOUNCE_MS = 150


class SetupError(Exception):
    """Configuration/setup error for TopPanelsController."""


class TopPanelsController(QObject):
    """Controller for top panels (Favorites/Recents)."""

    # FIX: Signal to notify when data loading is complete
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

        # Strict mode: on unexpected exceptions in refresh_* re-raise
        self._strict = str(os.getenv("APP_TOP_PANELS_STRICT", "").lower()) in {
            "1",
            "true",
            "yes",
            "on",
        }

    def refresh_all(self) -> None:
        """Refresh both panels: favorites and recents.

        FIX: Emits data_loaded after loading finishes.
        """
        import time
        t_start = time.perf_counter()
        logger.info("[TopPanelsDiag] refresh_all START")
        
        t_fav = time.perf_counter()
        self.refresh_favorites()
        fav_ms = (time.perf_counter() - t_fav) * 1000
        logger.info(f"[TopPanelsDiag] refresh_favorites done: {fav_ms:.1f}ms")
        
        t_rec = time.perf_counter()
        self.refresh_recent()
        rec_ms = (time.perf_counter() - t_rec) * 1000
        logger.info(f"[TopPanelsDiag] refresh_recent done: {rec_ms:.1f}ms")
        
        # Emit signal indicating data loading finished
        self.data_loaded.emit()
        
        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[TopPanelsDiag] refresh_all DONE: {total_ms:.1f}ms")

    def request_refresh(self, delay_ms: int | None = None, *args, **kwargs) -> None:
        """Request top panels refresh with debounce."""
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
        """Request refresh of favorites panel only with debounce."""
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
        """Request refresh of recent links panel only with debounce."""
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
        """Refresh favorites.

        Default — async load via LinksBusinessLogic.load_favorite_links().
        If method/signal is unavailable (mocks in tests), use synchronous fallback
        to get_favorite_links() with the previous error handling and widget update.
        """
        # 1) Try async (only if it's a real LinksBusinessLogic with signals)
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
            # Log async method call error and proceed to sync path
            # In strict mode don't fallback to reveal configuration errors
            if self._strict:
                raise

        # 2) Synchronous fallback — previous behavior (for tests and simple envs)
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

    def _get_recent_limit(self, widget):
        """Get recent links limit from widget."""
        limit = 10
        try:
            if isinstance(widget, (RecentsPanelWithLimit, SupportsGetLimit)):
                val = widget.get_limit()  # type: ignore[attr-defined]
                if isinstance(val, int) and val > 0:
                    limit = val
        except (TypeError, ValueError):
            pass
        return limit

    def _try_async_recent_load(self, limit):
        """Try to load recent links asynchronously."""
        try:
            if self._async_supported and callable(
                getattr(self.links_business, "load_recent_links", None)
            ):
                self.links_business.load_recent_links(limit)
                return True
        except (TypeError, ValueError) as exc:
            logger.error(
                "TopPanelsController.refresh_recent: invalid args for async call: %s",
                exc,
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "TopPanelsController.refresh_recent: failed to call load_recent_links"
            )
            if self._strict:
                raise
        return False

    def _load_recent_sync(self, limit):
        """Load recent links synchronously."""
        try:
            return self.links_business.get_recent_links(limit)
        except (TypeError, ValueError):
            logger.error(
                "TopPanelsController.refresh_recent: invalid args/data during recent load",
                exc_info=True,
            )
            return None
        except Exception:
            logger.exception(
                "TopPanelsController.refresh_recent failed: business layer error"
            )
            if self._strict:
                raise
            return None

    def _update_recent_widget(self, widget, items):
        """Update recent widget with items."""
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

    def refresh_recent(self) -> None:
        """Refresh recent links.

        Default — async load via LinksBusinessLogic.load_recent_links(limit).
        If method/signal is unavailable (mocks in tests), use synchronous fallback
        to get_recent_links(limit) with the previous error handling and widget update.
        """
        widget = self.recent_links_widget
        limit = self._get_recent_limit(widget)

        if self._try_async_recent_load(limit):
            return

        items = self._load_recent_sync(limit)
        if items is None:
            return

        self._update_recent_widget(widget, items)

    def clear_favorites(self) -> None:
        """Clear favorites: business data and widget.

        No nested try/except and no temporary flags. We log errors and don't
        propagate to avoid breaking the UI event chain.
        """
        # 1) Business clear
        try:
            self.links_business.clear_favorites_async()
        except Exception:
            logger.exception(
                "TopPanelsController.clear_favorites: error in links_business.clear_favorites_async"
            )

        # 2) Update widget via controlled path without re-emitting clear_requested
        #    (direct call fav_widget.clear_favorites() triggers clearRequested/clear_requested and a loop)
        try:
            self.refresh_favorites()
        except Exception:
            logger.exception(
                "TopPanelsController.clear_favorites: widget refresh after clear failed"
            )

    def schedule_structure_refresh(self) -> None:
        """Schedule top panels refresh for structural events with fixed interval."""
        try:
            if self._structure_refresh_timer is None:
                raise SetupError("Structure refresh timer is not configured")
            # Interval is fixed, set in __init__ (200 ms by default)
            if self._structure_refresh_timer.isActive():
                return
            self._structure_refresh_timer.start()
            logger.debug(
                "TopPanelsController.schedule_structure_refresh: timer started"
            )
        except (ValueError, RuntimeError) as e:
            # Expected errors — log without immediate refresh
            logger.error(
                "TopPanelsController.schedule_structure_refresh: failed to start structure timer: %s",
                e,
                exc_info=True,
            )
            return
        except SetupError:
            raise
        except Exception:
            # Unexpected errors — don't hide exception type
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
        """Single timeout handler for structural events.

        Error behavior:
        - Any errors inside `request_refresh()` must not leave the timer active.
        - The timer is always stopped in finally to avoid repeated attempts on failure.
        Expected life cycle: schedule -> timeout -> request_refresh -> stop.
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
            # Configuration error — re-raise after logging
            logger.exception(
                "TopPanelsController._on_structure_refresh_timeout: setup error"
            )
            raise
        finally:
            try:
                # Ensure the timer is stopped to prevent repeated calls on error
                if (
                    self._structure_refresh_timer
                    and self._structure_refresh_timer.isActive()
                ):
                    self._structure_refresh_timer.stop()
            except Exception:
                # Safe best-effort stop
                logger.debug(
                    "TopPanelsController._on_structure_refresh_timeout: timer stop failed",
                    exc_info=False,
                )

    # --- Business-layer signal handlers ---
    def _on_favorite_links_loaded(self, items: list[dict[str, object]] | list) -> None:
        widget = self.fav_widget
        try:
            if callable(getattr(widget, "set_data", None)):
                widget.set_data(items)  # type: ignore[call-arg]
            elif isinstance(widget, SupportsSetFavorites):
                # legacy fallback for test stubs
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
                # legacy fallback for test stubs
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
        """Safely cast delay to int; ignores irrelevant signal payloads."""
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
        if favorite_signal is not None and hasattr(favorite_signal, "connect"):
            favorite_signal.connect(self._on_favorite_links_loaded)
        else:
            connected_all = False
            logger.debug(
                "TopPanelsController: business signal 'favorite_links_loaded' not present; falling back to sync mode"
            )
        if recent_signal is not None and hasattr(recent_signal, "connect"):
            recent_signal.connect(self._on_recent_links_loaded)
        else:
            connected_all = False
            logger.debug(
                "TopPanelsController: business signal 'recent_links_loaded' not present; falling back to sync mode"
            )
        return connected_all

    def cleanup(self) -> None:
        """Stop timers and disconnect signals upon destruction.

        FIX: Prevent memory leaks from active timers. Should be called when
        closing the main window.
        """
        # Stop all timers
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

        # Disconnect business logic signals
        try:
            if hasattr(self.links_business, "favorite_links_loaded"):
                self.links_business.favorite_links_loaded.disconnect(
                    self._on_favorite_links_loaded
                )
            if hasattr(self.links_business, "recent_links_loaded"):
                self.links_business.recent_links_loaded.disconnect(
                    self._on_recent_links_loaded
                )
        except TypeError:  # Signals already disconnected
            pass
        except Exception as e:
            logger.warning(
                "TopPanelsController cleanup: failed to disconnect signals: %s", e
            )
