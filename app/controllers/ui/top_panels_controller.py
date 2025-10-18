# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

import logging
import os
from typing import Any

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

        # Tracking for refresh_all lifecycle
        self._refresh_sequence = 0
        self._data_loaded_token: int | None = None
        self._pending_sections: dict[str, bool] = {
            "favorites": False,
            "recents": False,
        }
        self._favorites_pending_tokens: list[int] = []
        self._recents_pending_tokens: list[int] = []

    def refresh_all(self) -> None:
        """Refresh both panels: favorites and recents."""
        import time

        token = self._begin_refresh_cycle()
        t_start = time.perf_counter()
        logger.info("[TopPanelsDiag] refresh_all START")

        t_fav = time.perf_counter()
        self.refresh_favorites(_refresh_token=token)
        fav_ms = (time.perf_counter() - t_fav) * 1000
        logger.info(f"[TopPanelsDiag] refresh_favorites scheduled: {fav_ms:.1f}ms")

        t_rec = time.perf_counter()
        self.refresh_recent(_refresh_token=token)
        rec_ms = (time.perf_counter() - t_rec) * 1000
        logger.info(f"[TopPanelsDiag] refresh_recent scheduled: {rec_ms:.1f}ms")

        self._maybe_emit_data_loaded()

        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(f"[TopPanelsDiag] refresh_all DONE (initial phase): {total_ms:.1f}ms")

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

    def refresh_favorites(self, *, _refresh_token: int | None = None) -> None:
        """Refresh favorites.

        Default - async load via LinksBusinessLogic.load_favorite_links().
        If method/signal is unavailable (mocks in tests), use synchronous fallback
        to get_favorite_links() with the previous error handling and widget update.
        """
        tracking_enabled = (
            _refresh_token is not None and _refresh_token == self._data_loaded_token
        )

        async_started = False
        if self._async_supported and callable(
            getattr(self.links_business, "load_favorite_links", None)
        ):
            try:
                self.links_business.load_favorite_links()
                async_started = True
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

        if async_started:
            if tracking_enabled and _refresh_token is not None:
                self._favorites_pending_tokens.append(_refresh_token)
            return

        # 2) Synchronous fallback - previous behavior (for tests and simple envs)
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

        self._update_favorites_widget(widget, items)

        if tracking_enabled:
            self._mark_section_ready("favorites", _refresh_token)

    def _update_favorites_widget(
        self, widget, items, *, enforce_strict: bool = True
    ) -> None:
        """Update favorites widget with prepared items."""
        try:
            if callable(getattr(widget, "set_data", None)):
                widget.set_data(items)  # type: ignore[call-arg]
            elif callable(getattr(widget, "set_favorites", None)) or isinstance(
                widget, SupportsSetFavorites
            ):
                widget.set_favorites(items)  # type: ignore[attr-defined]
            else:
                raise AttributeError("favorites widget lacks set_data/set_favorites")
        except (TypeError, ValueError):
            logger.error(
                "TopPanelsController: widget set_favorites signature error",
                exc_info=True,
            )
            if enforce_strict and self._strict:
                raise
        except Exception:
            logger.exception(
                "TopPanelsController: widget update error (favorites)"
            )
            if enforce_strict and self._strict:
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

    def _try_async_recent_load(
        self, limit, refresh_token: int | None = None
    ):
        """Try to load recent links asynchronously."""
        try:
            if self._async_supported and callable(
                getattr(self.links_business, "load_recent_links", None)
            ):
                self.links_business.load_recent_links(limit)
                if (
                    refresh_token is not None
                    and refresh_token == self._data_loaded_token
                ):
                    self._recents_pending_tokens.append(refresh_token)
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

    def _update_recent_widget(
        self, widget, items, *, enforce_strict: bool = True
    ):
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
            if enforce_strict and self._strict:
                raise

    @staticmethod
    def _normalize_snapshot_items(data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, list):
            return []
        result: list[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                result.append(item)
        return result

    def _collect_widget_items(self, widget: Any) -> list[dict[str, Any]]:
        if widget is None:
            return []
        getter = getattr(widget, "get_items", None)
        if callable(getter):
            try:
                items = getter()
            except Exception:
                logger.debug(
                    "TopPanelsController: get_items() failed on %s",
                    type(widget).__name__,
                    exc_info=True,
                )
                return []
            return self._normalize_snapshot_items(items)
        raw = getattr(widget, "_last_items", None)
        return self._normalize_snapshot_items(raw)

    def apply_snapshot(
        self,
        favorites: list[dict[str, Any]] | None = None,
        recents: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Prefill widgets with cached data before live refresh."""
        fav_items = self._normalize_snapshot_items(favorites)
        rec_items = self._normalize_snapshot_items(recents)
        applied = bool(fav_items or rec_items)

        try:
            if self.fav_widget is not None:
                self._update_favorites_widget(
                    self.fav_widget,
                    fav_items,
                    enforce_strict=False,
                )
        except Exception:
            logger.debug(
                "TopPanelsController: failed to apply favorites snapshot",
                exc_info=True,
            )

        try:
            if self.recent_links_widget is not None:
                self._update_recent_widget(
                    self.recent_links_widget,
                    rec_items,
                    enforce_strict=False,
                )
        except Exception:
            logger.debug(
                "TopPanelsController: failed to apply recents snapshot",
                exc_info=True,
            )

        return applied

    def capture_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """Capture current widget data for warm start snapshot."""
        return {
            "favorites": self._collect_widget_items(self.fav_widget),
            "recents": self._collect_widget_items(self.recent_links_widget),
        }

    def _begin_refresh_cycle(self) -> int:
        """Prepare tracking state for refresh_all cycle."""
        self._refresh_sequence += 1
        token = self._refresh_sequence
        self._data_loaded_token = token
        self._pending_sections["favorites"] = True
        self._pending_sections["recents"] = True
        self._favorites_pending_tokens.clear()
        self._recents_pending_tokens.clear()
        return token

    def _mark_section_ready(self, section: str, token: int | None) -> None:
        if token is None:
            return
        if self._data_loaded_token is None or token != self._data_loaded_token:
            return
        self._pending_sections[section] = False
        self._maybe_emit_data_loaded()

    def _complete_async_section(self, section: str) -> None:
        if section == "favorites":
            pending = self._favorites_pending_tokens
        else:
            pending = self._recents_pending_tokens
        token = pending.pop(0) if pending else None
        self._mark_section_ready(section, token)

    def _maybe_emit_data_loaded(self) -> None:
        if self._data_loaded_token is None:
            return
        if any(self._pending_sections.values()):
            return
        self.data_loaded.emit()
        self._data_loaded_token = None

    def refresh_recent(self, *, _refresh_token: int | None = None) -> None:
        """Refresh recent links.

        Default - async load via LinksBusinessLogic.load_recent_links(limit).
        If method/signal is unavailable (mocks in tests), use synchronous fallback
        to get_recent_links(limit) with the previous error handling and widget update.
        """
        widget = self.recent_links_widget
        limit = self._get_recent_limit(widget)

        tracking_enabled = (
            _refresh_token is not None and _refresh_token == self._data_loaded_token
        )

        if self._try_async_recent_load(limit, _refresh_token):
            return

        items = self._load_recent_sync(limit)
        if items is None:
            return

        self._update_recent_widget(widget, items)

        if tracking_enabled:
            self._mark_section_ready("recents", _refresh_token)

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
        self._update_favorites_widget(widget, items)
        self._complete_async_section("favorites")

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
        self._complete_async_section("recents")

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
