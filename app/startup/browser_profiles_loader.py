"""Module for loading browser profiles."""

import logging
from typing import Any

from PyQt6.QtCore import Qt, QTimer

# Module-level logger
logger = logging.getLogger(__name__)


class BrowserProfilesLoader:
    """Manage loading of browser profiles."""

    _INITIAL_LOAD_DELAY_MS = 250

    def __init__(self, main_window: Any):
        """Initialize the loader.

        Args:
            main_window: Application main window
        """
        self.main_window = main_window

    def setup_lazy_loading(self) -> None:
        """Configure lazy loading of browser profiles after the window is shown."""
        try:
            self.main_window.shown.connect(self._on_window_shown)
        except (AttributeError, TypeError, RuntimeError) as e:
            # Narrowly scoped Qt signal connection exceptions
            logger.debug("Failed to connect lazy profile loading: %s", e, exc_info=True)

    def _import_profile_modules(self):
        """Import browser profile modules."""
        try:
            from app.utils.browser.browser_profiles import async_profile_manager as _apm
            from app.utils.browser.browser_profiles import persistent_cache as _pc
            from app.utils.browser.browser_profiles import profile_manager as _pm

            return _apm, _pc, _pm
        except ImportError as e:
            logger.warning("Browser profile modules unavailable: %s", e, exc_info=True)
            return None, None, None

    def _disconnect_shown_signal(self):
        """Disconnect one-shot handler."""
        try:
            self.main_window.shown.disconnect(self._on_window_shown)
        except Exception:
            pass

    def _save_profiles_to_cache(self, all_profiles, _pc):
        """Save profiles to persistent cache."""
        try:
            cache = _pc.PersistentProfileCache(default_ttl=3600)
            for key, profiles in (all_profiles or {}).items():
                try:
                    cache.set(key, profiles)
                except Exception as set_err:
                    logger.warning(
                        "Failed to write profiles to cache for key '%s': %s",
                        key,
                        set_err,
                        exc_info=True,
                    )
        except Exception as cache_err:
            logger.warning(
                "Error initializing/writing profile cache: %s",
                cache_err,
                exc_info=True,
            )

    def _update_profile_manager(self, all_profiles, _pm):
        """Update profile manager with loaded profiles."""
        try:
            mgr = _pm.get_profile_manager()
            mgr.update_profiles_bulk(all_profiles or {})
        except Exception as upd_err:
            logger.warning(
                "Failed to update profile manager from cache: %s",
                upd_err,
                exc_info=True,
            )

    def _load_profiles_async(self, async_mgr, _pc, _pm):
        """Load profiles asynchronously when cache doesn't exist."""

        def _save_and_update(all_profiles: dict):
            """Save and update browser profiles."""
            self._save_profiles_to_cache(all_profiles, _pc)
            self._update_profile_manager(all_profiles, _pm)
            try:
                async_mgr.all_profiles_ready.disconnect(_save_and_update)
            except (TypeError, RuntimeError) as dis_err:
                logger.debug(
                    "Error disconnecting all_profiles_ready slot: %s",
                    dis_err,
                    exc_info=True,
                )

        try:
            async_mgr.all_profiles_ready.connect(
                _save_and_update,
                type=Qt.ConnectionType.UniqueConnection,
            )
        except (TypeError, RuntimeError) as conn_err:
            logger.debug(
                "Failed to connect all_profiles_ready slot: %s",
                conn_err,
                exc_info=True,
            )
            return

        try:
            async_mgr.load_all_profiles_async(use_cache=False)
        except Exception as load_err:
            logger.debug(
                "Failed to start async profile loading: %s",
                load_err,
                exc_info=True,
            )

    def _load_profiles_from_cache(self, _pc, _pm):
        """Load profiles from existing cache."""
        try:
            cache = _pc.PersistentProfileCache(default_ttl=3600)
            mgr = _pm.get_profile_manager()

            loaded_any = False
            profiles_by_key: dict[str, Any] = {}
            try:
                keys = list(cache.keys())
            except Exception:
                keys = []
            for key in keys:
                try:
                    profiles = cache.get(key)  # type: ignore[call-arg]
                    if profiles is not None:
                        profiles_by_key[str(key)] = profiles
                        loaded_any = True
                except Exception as get_err:
                    logger.debug(
                        "Failed to read cached profiles for key '%s': %s",
                        key,
                        get_err,
                        exc_info=True,
                    )

            if loaded_any:
                try:
                    mgr.update_profiles_bulk(profiles_by_key)
                except Exception as upd_err:
                    logger.warning(
                        "Failed to update profile manager from existing cache: %s",
                        upd_err,
                        exc_info=True,
                    )
        except Exception as cache_err:
            logger.debug(
                "Error reading existing profile cache: %s", cache_err, exc_info=True
            )

    def _on_window_shown(self) -> None:
        """Window shown handler to start profile loading."""
        self._disconnect_shown_signal()
        try:
            QTimer.singleShot(self._INITIAL_LOAD_DELAY_MS, self._start_profile_loading)
        except Exception:
            logger.debug(
                "Failed to defer browser profile loading after window shown",
                exc_info=True,
            )
            self._start_profile_loading()

    def _start_profile_loading(self) -> None:
        """Start non-critical browser profile loading after the first window paint."""
        _apm, _pc, _pm = self._import_profile_modules()
        if not _apm or not _pc or not _pm:
            return

        try:
            cache_path = _pc.get_cache_path()
        except Exception as e:
            logger.debug(
                "Failed to determine browser profiles cache path: %s", e, exc_info=True
            )
            return

        if not cache_path.exists():
            try:
                async_mgr = _apm.get_async_profile_manager()
            except Exception as e:
                logger.debug(
                    "Failed to obtain async profile manager: %s",
                    e,
                    exc_info=True,
                )
                return
            self._load_profiles_async(async_mgr, _pc, _pm)
        else:
            self._load_profiles_from_cache(_pc, _pm)
