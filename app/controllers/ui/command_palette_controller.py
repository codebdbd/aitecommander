"""Controller for the Global Command Palette (Alt + ~ / Alt + `)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QWidget

from app.config_data.runtime_config import runtime_app_config as app_config
from app.services.command_palette_service import CommandPaletteService
from app.services.global_hotkey_service import GlobalHotkeyService

if TYPE_CHECKING:
    from app.views.windows.dialogs.command_palette_dialog import CommandPaletteDialog

logger = logging.getLogger(__name__)


class CommandPaletteController(QObject):
    """Coordinates global hotkey registration, search service, and palette dialog."""

    _TOGGLE_DEBOUNCE_SEC = 0.15

    def __init__(
        self,
        main_window: QWidget,
        db: Any = None,
        *,
        register_native_hotkey: bool = True,
    ) -> None:
        super().__init__(parent=main_window)
        self.main_window: Any = main_window
        self.db = db if db is not None else getattr(main_window, "db", None)

        cfg = self._get_palette_config()
        self._enabled: bool = bool(cfg.get("enabled", True))
        self._hotkey_str: str = str(cfg.get("hotkey", "Alt+`") or "Alt+`")
        self._max_results: int = max(1, int(cfg.get("max_results", 10) or 10))

        self._service = CommandPaletteService(self.db)
        self._hotkey_service = GlobalHotkeyService(self)
        self._hotkey_service.activated.connect(self._on_hotkey_triggered)

        self._dialog: CommandPaletteDialog | None = None
        self._shortcuts: list[QShortcut] = []
        self._last_toggle_ts: float = 0.0
        self._cleaned_up: bool = False

        if self._enabled:
            self._setup_in_app_shortcuts()
            if register_native_hotkey:
                shown_sig = getattr(main_window, "shown", None)
                if shown_sig is not None and hasattr(shown_sig, "connect"):
                    shown_sig.connect(self._schedule_native_hotkey_registration)
                else:
                    self._register_native_hotkey_safe()

    def _schedule_native_hotkey_registration(self) -> None:
        if self._cleaned_up or not self._enabled:
            return
        QTimer.singleShot(600, self._register_native_hotkey_safe)

    def _register_native_hotkey_safe(self) -> None:
        if self._cleaned_up or not self._enabled:
            return
        app = QApplication.instance()
        if app is None or app.closingDown():
            return
        if hasattr(self.main_window, "isVisible") and not self.main_window.isVisible():
            return
        self._hotkey_service.register_hotkey(self._hotkey_str)

    @staticmethod
    def _get_palette_config() -> dict[str, Any]:
        try:
            raw = getattr(app_config, "_raw_data", None)
            if isinstance(raw, dict):
                settings = raw.get("settings")
                if isinstance(settings, dict):
                    cp = settings.get("command_palette")
                    if isinstance(cp, dict):
                        return cp
        except Exception:
            logger.debug("CommandPaletteController: failed to read config", exc_info=True)
        return {"enabled": True, "hotkey": "Alt+`", "max_results": 10}

    def _setup_in_app_shortcuts(self) -> None:
        """Bind application-level Qt shortcuts for physical grave/tilde keys across layouts."""
        sequences = [self._hotkey_str, "Alt+`", "Alt+~", "Alt+Ё", "Alt+ё"]
        seen: set[str] = set()
        for seq in sequences:
            norm = seq.strip()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            try:
                sc = QShortcut(QKeySequence(norm), self.main_window)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(self._on_hotkey_triggered)
                self._shortcuts.append(sc)
            except Exception:
                logger.debug(
                    "CommandPaletteController: failed to bind shortcut %s",
                    norm,
                    exc_info=True,
                )

    def _ensure_dialog(self) -> CommandPaletteDialog:
        if self._dialog is None:
            from app.views.windows.dialogs.command_palette_dialog import (
                CommandPaletteDialog,
            )

            self._dialog = CommandPaletteDialog(parent=self.main_window)
            self._dialog.query_changed.connect(self._on_query_changed)
            self._dialog.link_activated.connect(self._on_link_activated)
            self._dialog.link_reveal_requested.connect(self._on_link_reveal_requested)
        return self._dialog

    def _on_hotkey_triggered(self) -> None:
        now = time.monotonic()
        if (now - self._last_toggle_ts) < self._TOGGLE_DEBOUNCE_SEC:
            return
        self._last_toggle_ts = now
        self.toggle_palette()

    def toggle_palette(self) -> bool:
        """Toggle the Command Palette visibility safely."""
        if self._cleaned_up or not self._enabled:
            return False

        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.hide()
            return False

        return self.show_palette()

    def show_palette(self) -> bool:
        """Open the Command Palette if no modal dialog blocks interaction."""
        if self._cleaned_up or not self._enabled:
            return False

        # Guard against opening over active modal dialogs (LinkDialog, SettingsDialog, QMessageBox)
        active_modal = QApplication.activeModalWidget()
        if active_modal is not None and active_modal is not self._dialog:
            logger.debug(
                "CommandPaletteController: blocked opening while modal widget %s is active",
                type(active_modal).__name__,
            )
            return False

        if self.db is None:
            self.db = getattr(self.main_window, "db", None)
            self._service.set_db(self.db)

        self._service.refresh_snapshot()
        dlg = self._ensure_dialog()
        initial_results = self._service.search("", limit=self._max_results)
        dlg.set_results(initial_results)
        dlg.open_palette()
        return True

    def hide_palette(self) -> None:
        if self._dialog is not None and self._dialog.isVisible():
            self._dialog.hide()

    def _on_query_changed(self, query: str) -> None:
        if self._dialog is None:
            return
        results = self._service.search(query, limit=self._max_results)
        self._dialog.set_results(results)

    def _on_link_activated(self, link_dict: dict[str, Any]) -> None:
        """Launch the selected link through standard LinksActions pipeline."""
        if not isinstance(link_dict, dict):
            return
        la = getattr(self.main_window, "links_actions", None)
        if la is not None and hasattr(la, "open_link"):
            la.open_link(link_dict)
            return
        links = getattr(self.main_window, "links", None)
        if links is not None and hasattr(links, "open_link"):
            links.open_link(link_dict)

    def _on_link_reveal_requested(self, link_dict: dict[str, Any]) -> None:
        """Reveal the selected link in the main window (Ctrl + Enter)."""
        if not isinstance(link_dict, dict):
            return

        self._restore_main_window()

        category_id = link_dict.get("category_id")
        sphere_id = link_dict.get("sphere_id")
        link_id = link_dict.get("id")

        if not isinstance(category_id, int) or category_id <= 0:
            return

        sb = getattr(self.main_window, "structure_business", None)
        current_sphere = getattr(sb, "current_sphere_id", None) if sb is not None else None
        structure = getattr(self.main_window, "structure", None)
        ui_state = getattr(self.main_window, "ui_state", None)

        if (
            isinstance(sphere_id, int)
            and sphere_id > 0
            and current_sphere != sphere_id
            and structure is not None
            and hasattr(structure, "switch_sphere")
        ):
            structure.switch_sphere(sphere_id, item_to_select=("category", category_id))
            if ui_state is not None and hasattr(ui_state, "load_category"):
                ui_state.load_category(category_id, source="CommandPalette")
        else:
            sel_handler = getattr(structure, "selection_handler", None) if structure else None
            if sel_handler is not None and hasattr(sel_handler, "_restore_category_selection"):
                try:
                    sel_handler._restore_category_selection(category_id)
                except Exception:
                    logger.debug(
                        "CommandPaletteController: _restore_category_selection failed",
                        exc_info=True,
                    )
            if ui_state is not None and hasattr(ui_state, "load_category"):
                ui_state.load_category(category_id, source="CommandPalette")

        if isinstance(link_id, int) and link_id > 0:
            la = getattr(self.main_window, "links_actions", None)
            if la is not None and hasattr(la, "schedule_restore_selection"):
                la.schedule_restore_selection(link_id)
                QTimer.singleShot(
                    120,
                    lambda lid=link_id: la.restore_selection(lid)
                    if hasattr(la, "restore_selection")
                    else None,
                )

    def _restore_main_window(self) -> None:
        mw = self.main_window
        if mw is None:
            return
        try:
            if hasattr(mw, "isMinimized") and mw.isMinimized():
                mw.showNormal()
            elif hasattr(mw, "isVisible") and not mw.isVisible():
                mw.show()
            if hasattr(mw, "raise_"):
                mw.raise_()
            if hasattr(mw, "activateWindow"):
                mw.activateWindow()
        except Exception:
            logger.debug("CommandPaletteController: failed to restore main window", exc_info=True)

    def refresh_theme(self) -> None:
        """Update Command Palette styling when the application theme changes."""
        if self._dialog is not None:
            self._dialog.refresh_theme()

    def cleanup(self, *_args: Any) -> bool:
        """Unregister global hotkeys and release dialog resources."""
        if self._cleaned_up:
            return True
        self._cleaned_up = True

        try:
            self._hotkey_service.cleanup()
        except Exception:
            logger.debug("CommandPaletteController: hotkey cleanup error", exc_info=True)

        for sc in self._shortcuts:
            try:
                sc.setEnabled(False)
                sc.deleteLater()
            except Exception:
                pass
        self._shortcuts.clear()

        if self._dialog is not None:
            try:
                self._dialog.hide()
                self._dialog.close()
                self._dialog.deleteLater()
            except Exception:
                pass
            self._dialog = None

        return True

    def shutdown(self, *_args: Any) -> bool:
        """Alias for AppShutdownController compatibility."""
        return self.cleanup()
