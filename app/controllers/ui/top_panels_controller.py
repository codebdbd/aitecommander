# app/controllers/ui/top_panels_controller.py

from __future__ import annotations

import logging
import os
from typing import Any

from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal, pyqtSlot

from app.config_data.runtime_config import get_favorites_panel_limit
from app.interfaces import (
    FavoritesPanelWithClear,
    RecentsPanelWithLimit,
    TopPanelDataLike,
)

from .types import (
    LinksBusinessProtocol,
    SupportsCancelUpdate,
    SupportsGetLimit,
    SupportsSetFavorites,
    SupportsSetRecentLinks,
    SupportsUpdateData,
)

logger = logging.getLogger(__name__)
_DIAG_TOP_PANELS = str(os.getenv("APP_TOP_PANELS_DIAG", "")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}


_DEFAULT_DEBOUNCE_MS = 150
_MIN_REFRESH_INTERVAL_S = 0.25
_DATA_LOADED_TIMEOUT_MS = 5000
_DEFAULT_FAVORITES_LIMIT = 16
_FAVORITES_WARMUP_RETRY_MS = 120
_FAVORITES_WARMUP_MAX_DELAY_MS = 2500


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
                "fav_widget must provide update_data(items) or set_data(items) or legacy set_favorites(items)"
            )
        if not self._supports_recent_widget(recent_links_widget):
            raise TypeError(
                "recent_links_widget must provide update_data(items) or set_data(items) or legacy set_recent_links(items)"
            )
        self.fav_widget = fav_widget
        self.recent_links_widget = recent_links_widget
        if links_business is None:
            raise ValueError("TopPanelsController requires links_business")
        self.links_business: LinksBusinessProtocol = links_business

        self._pending_refresh = False
        self._pending_fav_refresh = False
        self._pending_recent_refresh = False
        self._last_refresh_ts = 0.0
        self._last_fav_refresh_ts = 0.0
        self._last_recent_refresh_ts = 0.0
        self._refresh_timer = QTimer(self)
        self._fav_refresh_timer = QTimer(self)
        self._recent_refresh_timer = QTimer(self)
        self._structure_refresh_timer = QTimer(self)
        self._data_loaded_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._fav_refresh_timer.setSingleShot(True)
        self._recent_refresh_timer.setSingleShot(True)
        self._structure_refresh_timer.setSingleShot(True)
        self._data_loaded_timer.setSingleShot(True)
        self._structure_refresh_timer.setInterval(200)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)
        self._fav_refresh_timer.timeout.connect(self._on_fav_refresh_timeout)
        self._recent_refresh_timer.timeout.connect(self._on_recent_refresh_timeout)
        self._structure_refresh_timer.timeout.connect(
            self._on_structure_refresh_timeout
        )
        self._data_loaded_timer.timeout.connect(self._on_data_loaded_timeout)

        self._async_fav_supported = False
        self._async_recent_supported = False
        self._has_favorites_cleared_signal = False
        self._connect_business_signals()

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
        self._favorites_pending_token: int | None = None
        self._recents_pending_token: int | None = None
        self._startup_favorites_stagger_pending = True
        self._startup_refresh_stagger_pending = True
        self._favorites_warmup_wait_started_ts = 0.0

    def refresh_all(self) -> None:
        """Refresh both panels: favorites and recents."""
        import time

        self._last_refresh_ts = time.perf_counter()
        token = self._begin_refresh_cycle()
        t_start = time.perf_counter()
        if _DIAG_TOP_PANELS:
            logger.info("[TopPanelsDiag] refresh_all START")

        self._startup_favorites_stagger_pending = False
        self._startup_refresh_stagger_pending = False

        t_fav = time.perf_counter()
        self.refresh_favorites(_refresh_token=token)
        fav_ms = (time.perf_counter() - t_fav) * 1000
        if _DIAG_TOP_PANELS:
            logger.info(
                f"[TopPanelsDiag] refresh_favorites scheduled: {fav_ms:.1f}ms"
            )

        t_rec = time.perf_counter()
        self.refresh_recent(_refresh_token=token)
        rec_ms = (time.perf_counter() - t_rec) * 1000
        if _DIAG_TOP_PANELS:
            logger.info(f"[TopPanelsDiag] refresh_recent scheduled: {rec_ms:.1f}ms")
        self._maybe_emit_data_loaded()

        total_ms = (time.perf_counter() - t_start) * 1000
        if _DIAG_TOP_PANELS:
            logger.info(
                f"[TopPanelsDiag] refresh_all DONE (initial phase): {total_ms:.1f}ms"
            )

    def request_refresh(self, delay_ms: int | None = None, *args, **kwargs) -> None:
        """Request top panels refresh with debounce."""
        try:
            import time

            if self._data_loaded_token is not None and (
                self._pending_sections.get("favorites")
                or self._pending_sections.get("recents")
            ):
                return
            if (time.perf_counter() - self._last_refresh_ts) < _MIN_REFRESH_INTERVAL_S:
                return
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
            import time

            if (time.perf_counter() - self._last_fav_refresh_ts) < _MIN_REFRESH_INTERVAL_S:
                return
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
            import time

            if (time.perf_counter() - self._last_recent_refresh_ts) < _MIN_REFRESH_INTERVAL_S:
                return
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
        import time

        self._last_fav_refresh_ts = time.perf_counter()
        tracking_enabled = (
            _refresh_token is not None and _refresh_token == self._data_loaded_token
        )
        if not self._is_locked_db_warmup_ready():
            now = time.perf_counter()
            if self._favorites_warmup_wait_started_ts <= 0.0:
                self._favorites_warmup_wait_started_ts = now
            waited_ms = (now - self._favorites_warmup_wait_started_ts) * 1000.0
            if waited_ms < _FAVORITES_WARMUP_MAX_DELAY_MS:
                QTimer.singleShot(
                    _FAVORITES_WARMUP_RETRY_MS,
                    lambda tok=_refresh_token: self.refresh_favorites(
                        _refresh_token=tok
                    ),
                )
                return
        self._favorites_warmup_wait_started_ts = 0.0

        fav_limit = self._get_favorites_limit()
        async_started = False
        async_error: Exception | None = None
        if self._async_fav_supported and callable(
            getattr(self.links_business, "load_favorite_links", None)
        ):
            try:
                self.links_business.load_favorite_links(fav_limit)
                async_started = True
            except (TypeError, ValueError) as exc:
                async_error = exc
                logger.error(
                    "TopPanelsController.refresh_favorites: invalid args for async call: %s",
                    exc,
                    exc_info=True,
                )
            except Exception:
                async_error = RuntimeError(
                    "TopPanelsController.refresh_favorites: failed to call load_favorite_links"
                )
                logger.exception(
                    "TopPanelsController.refresh_favorites: failed to call load_favorite_links"
                )
                if self._strict:
                    raise
            # In strict mode, only raise if async was not started
            if self._strict and not async_started:
                if async_error is not None:
                    raise async_error
                raise RuntimeError(
                    "TopPanelsController.refresh_favorites: async refresh did not start"
                )

        if async_started:
            if tracking_enabled and _refresh_token is not None:
                self._favorites_pending_token = _refresh_token
            return

        # 2) Synchronous fallback - previous behavior (for tests and simple envs)
        widget = self.fav_widget
        items: list = []
        try:
            items = self.links_business.get_favorite_links(fav_limit)
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

    def _is_locked_db_warmup_ready(self) -> bool:
        try:
            app = QCoreApplication.instance()
            if app is None:
                return True
            return bool(app.property("locked_db_warmup_ready"))
        except Exception:
            return True

    def _get_favorites_limit(self) -> int:
        """Return a safe startup/display limit for favorites top panel."""
        try:
            # Optional config knob for release tuning.
            value = get_favorites_panel_limit(_DEFAULT_FAVORITES_LIMIT)
            return value if value > 0 else _DEFAULT_FAVORITES_LIMIT
        except Exception:
            return _DEFAULT_FAVORITES_LIMIT

    def _update_favorites_widget(
        self, widget, items, *, enforce_strict: bool = True
    ) -> None:
        """Update favorites widget with prepared items."""
        try:
            self._cancel_widget_update(widget)
            current = self._collect_widget_items(widget)
            if current == items:
                return
            if callable(getattr(widget, "update_data", None)):
                ok = widget.update_data(items)  # type: ignore[call-arg]
                if ok is False:
                    raise RuntimeError("favorites widget rejected update_data")
            elif callable(getattr(widget, "set_data", None)):
                widget.set_data(items)  # type: ignore[call-arg]
            elif callable(getattr(widget, "set_favorites", None)) or isinstance(
                widget, SupportsSetFavorites
            ):
                widget.set_favorites(items)  # type: ignore[attr-defined]
            else:
                raise AttributeError("favorites widget lacks set_data/set_favorites")
            try:
                widget._last_items = list(items)
            except Exception:
                pass
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
            if self._async_recent_supported and callable(
                getattr(self.links_business, "load_recent_links", None)
            ):
                self.links_business.load_recent_links(limit)
                if (
                    refresh_token is not None
                    and refresh_token == self._data_loaded_token
                ):
                    self._recents_pending_token = refresh_token
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
            self._cancel_widget_update(widget)
            current = self._collect_widget_items(widget)
            if current == items:
                return
            if callable(getattr(widget, "update_data", None)):
                ok = widget.update_data(items)  # type: ignore[call-arg]
                if ok is False:
                    raise RuntimeError("recent widget rejected update_data")
            elif callable(getattr(widget, "set_data", None)):
                widget.set_data(items)  # type: ignore[call-arg]
            elif callable(getattr(widget, "set_recent_links", None)):
                widget.set_recent_links(items)  # type: ignore[attr-defined]
            else:
                raise AttributeError("recent widget lacks set_data/set_recent_links")
            try:
                widget._last_items = list(items)
            except Exception:
                pass
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
                if callable(getattr(self.fav_widget, "set_data", None)):
                    try:
                        self.fav_widget.set_data(  # type: ignore[call-arg]
                            fav_items,
                            fast_icons=True,
                        )
                    except TypeError:
                        self._update_favorites_widget(
                            self.fav_widget,
                            fav_items,
                            enforce_strict=False,
                        )
                else:
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
                if callable(getattr(self.recent_links_widget, "set_data", None)):
                    try:
                        self.recent_links_widget.set_data(  # type: ignore[call-arg]
                            rec_items,
                            fast_icons=True,
                        )
                    except TypeError:
                        self._update_recent_widget(
                            self.recent_links_widget,
                            rec_items,
                            enforce_strict=False,
                        )
                else:
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
        self._favorites_pending_token = None
        self._recents_pending_token = None
        if self._data_loaded_timer.isActive():
            self._data_loaded_timer.stop()
        self._data_loaded_timer.start(_DATA_LOADED_TIMEOUT_MS)
        return token

    def _mark_section_ready(self, section: str, token: int | None) -> None:
        if token is None:
            return
        if self._data_loaded_token is None or token != self._data_loaded_token:
            return
        self._pending_sections[section] = False
        self._maybe_emit_data_loaded()

    def _run_delayed_startup_favorites_refresh(
        self, token: int | None = None
    ) -> None:
        if token is not None and token != self._data_loaded_token:
            return
        self.refresh_favorites(_refresh_token=token)

    def _complete_async_section(self, section: str) -> None:
        token = (
            self._favorites_pending_token
            if section == "favorites"
            else self._recents_pending_token
        )
        if section == "favorites":
            self._favorites_pending_token = None
        else:
            self._recents_pending_token = None
        self._mark_section_ready(section, token)

    def _maybe_emit_data_loaded(self) -> None:
        if self._data_loaded_token is None:
            return
        if any(self._pending_sections.values()):
            return
        self.data_loaded.emit()
        self._data_loaded_token = None
        if self._data_loaded_timer.isActive():
            self._data_loaded_timer.stop()

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

        # 2) UI refresh will be triggered by favorites_cleared signal if available.
        #    Fallback to a direct refresh when the signal is absent.
        if not self._has_favorites_cleared_signal:
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
            import time

            self._last_fav_refresh_ts = time.perf_counter()
            self.refresh_favorites()
        finally:
            self._pending_fav_refresh = False

    @pyqtSlot()
    def _on_recent_refresh_timeout(self) -> None:
        try:
            import time

            self._last_recent_refresh_ts = time.perf_counter()
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

    @pyqtSlot()
    def _on_data_loaded_timeout(self) -> None:
        """Fail-safe to avoid blocking refresh if async never returns."""
        if self._data_loaded_token is None:
            return
        self._pending_sections["favorites"] = False
        self._pending_sections["recents"] = False
        self._favorites_pending_token = None
        self._recents_pending_token = None
        try:
            self.data_loaded.emit()
        finally:
            self._data_loaded_token = None

    # --- Business-layer signal handlers ---
    def _on_favorite_links_loaded(self, items: list[dict[str, object]] | list) -> None:
        widget = self.fav_widget
        self._update_favorites_widget(widget, items)
        self._complete_async_section("favorites")

    def _on_link_updated_for_favorites(self, updated_link: dict[str, object] | dict) -> None:
        try:
            if not isinstance(updated_link, dict):
                return
            if "is_favorite" not in updated_link:
                return
            self.request_favorites_refresh()
        except Exception:
            logger.debug(
                "TopPanelsController: failed to schedule favorites refresh after link_updated",
                exc_info=True,
            )

    def _on_link_deleted_for_favorites(self, _link_id: int | object) -> None:
        try:
            self.request_favorites_refresh()
        except Exception:
            logger.debug(
                "TopPanelsController: failed to schedule favorites refresh after link_deleted",
                exc_info=True,
            )

    def _on_items_batch_deleted_for_favorites(
        self, item_type: str | object, _ids: list[object] | list | object
    ) -> None:
        try:
            if item_type != "link":
                return
            self.request_favorites_refresh()
        except Exception:
            logger.debug(
                "TopPanelsController: failed to schedule favorites refresh after items_batch_deleted",
                exc_info=True,
            )

    def _on_batch_updated_for_favorites(self, _result: bool | object = None) -> None:
        try:
            self.request_favorites_refresh()
        except Exception:
            logger.debug(
                "TopPanelsController: failed to schedule favorites refresh after batch_updated",
                exc_info=True,
            )

    def _on_recent_links_loaded(self, items: list[dict[str, object]] | list) -> None:
        import time

        self._last_recent_refresh_ts = time.perf_counter()
        widget = self.recent_links_widget
        try:
            self._update_recent_widget(widget, items)
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

    @staticmethod
    def _cancel_widget_update(widget: Any) -> None:
        """Best-effort cancellation for widgets supporting lifecycle API."""
        if widget is None:
            return
        cancel = getattr(widget, "cancel_update", None)
        if callable(cancel) or isinstance(widget, SupportsCancelUpdate):
            try:
                cancel()
            except Exception:
                logger.debug(
                    "TopPanelsController: widget cancel_update failed on %s",
                    type(widget).__name__,
                    exc_info=True,
                )

    def _on_favorites_cleared(self, _result: bool | None = None) -> None:
        try:
            self.refresh_favorites()
        except Exception:
            logger.exception(
                "TopPanelsController: refresh after favorites_cleared failed"
            )

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
        return callable(getattr(widget, "update_data", None)) or callable(
            getattr(widget, "set_data", None)
        ) or isinstance(
            widget, (SupportsUpdateData, SupportsSetFavorites, FavoritesPanelWithClear)
        )

    def _supports_recent_widget(self, widget: object) -> bool:
        return callable(getattr(widget, "update_data", None)) or callable(
            getattr(widget, "set_data", None)
        ) or isinstance(
            widget, (SupportsUpdateData, SupportsSetRecentLinks, RecentsPanelWithLimit)
        )

    def _connect_business_signals(self) -> bool:
        favorite_signal = getattr(self.links_business, "favorite_links_loaded", None)
        recent_signal = getattr(self.links_business, "recent_links_loaded", None)
        connected_all = True
        if favorite_signal is not None and hasattr(favorite_signal, "connect"):
            favorite_signal.connect(self._on_favorite_links_loaded)
            self._async_fav_supported = True
        else:
            connected_all = False
            self._async_fav_supported = False
            logger.debug(
                "TopPanelsController: business signal 'favorite_links_loaded' not present; falling back to sync mode"
            )
        if recent_signal is not None and hasattr(recent_signal, "connect"):
            recent_signal.connect(self._on_recent_links_loaded)
            self._async_recent_supported = True
        else:
            connected_all = False
            self._async_recent_supported = False
            logger.debug(
                "TopPanelsController: business signal 'recent_links_loaded' not present; falling back to sync mode"
            )
        favorites_cleared = getattr(self.links_business, "favorites_cleared", None)
        if favorites_cleared is not None and hasattr(favorites_cleared, "connect"):
            try:
                favorites_cleared.connect(self._on_favorites_cleared)
                self._has_favorites_cleared_signal = True
            except Exception:
                self._has_favorites_cleared_signal = False
        link_updated = getattr(self.links_business, "link_updated", None)
        if link_updated is not None and hasattr(link_updated, "connect"):
            try:
                link_updated.connect(self._on_link_updated_for_favorites)
            except Exception:
                logger.debug(
                    "TopPanelsController: failed to connect link_updated favorites refresh",
                    exc_info=True,
                )
        link_deleted = getattr(self.links_business, "link_deleted", None)
        if link_deleted is not None and hasattr(link_deleted, "connect"):
            try:
                link_deleted.connect(self._on_link_deleted_for_favorites)
            except Exception:
                logger.debug(
                    "TopPanelsController: failed to connect link_deleted favorites refresh",
                    exc_info=True,
                )
        items_batch_deleted = getattr(self.links_business, "items_batch_deleted", None)
        if items_batch_deleted is not None and hasattr(items_batch_deleted, "connect"):
            try:
                items_batch_deleted.connect(self._on_items_batch_deleted_for_favorites)
            except Exception:
                logger.debug(
                    "TopPanelsController: failed to connect items_batch_deleted favorites refresh",
                    exc_info=True,
                )
        batch_updated = getattr(self.links_business, "batch_updated", None)
        if batch_updated is not None and hasattr(batch_updated, "connect"):
            try:
                batch_updated.connect(self._on_batch_updated_for_favorites)
            except Exception:
                logger.debug(
                    "TopPanelsController: failed to connect batch_updated favorites refresh",
                    exc_info=True,
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
            self._data_loaded_timer,
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
            if hasattr(self.links_business, "favorites_cleared"):
                self.links_business.favorites_cleared.disconnect(
                    self._on_favorites_cleared
                )
            if hasattr(self.links_business, "link_updated"):
                self.links_business.link_updated.disconnect(
                    self._on_link_updated_for_favorites
                )
            if hasattr(self.links_business, "link_deleted"):
                self.links_business.link_deleted.disconnect(
                    self._on_link_deleted_for_favorites
                )
            if hasattr(self.links_business, "items_batch_deleted"):
                self.links_business.items_batch_deleted.disconnect(
                    self._on_items_batch_deleted_for_favorites
                )
            if hasattr(self.links_business, "batch_updated"):
                self.links_business.batch_updated.disconnect(
                    self._on_batch_updated_for_favorites
                )
        except TypeError:  # Signals already disconnected
            pass
        except Exception as e:
            logger.warning(
                "TopPanelsController cleanup: failed to disconnect signals: %s", e
            )
