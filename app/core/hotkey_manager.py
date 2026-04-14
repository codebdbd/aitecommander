"""Centralized registry and binding for application hotkeys."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget

from app.core.log_manager import LogManager
from app.core.settings_manager import SettingsManager


class HotkeyManager:
    """Static API for registering and binding keyboard shortcuts."""

    _registry: dict[str, str] = {}
    _contexts: dict[str, Qt.ShortcutContext] = {}

    @staticmethod
    def _infer_context(action_id: str) -> Qt.ShortcutContext | None:
        if action_id.startswith("global."):
            return Qt.ShortcutContext.WindowShortcut
        if action_id.startswith("table."):
            return Qt.ShortcutContext.WidgetWithChildrenShortcut
        if action_id.startswith("edit."):
            return Qt.ShortcutContext.WidgetShortcut
        return None

    @classmethod
    def register(
        cls,
        action_id: str,
        default: str,
        *,
        context: Qt.ShortcutContext | None = None,
    ) -> None:
        if not action_id:
            return
        key = SettingsManager.get(f"hotkeys.{action_id}", default)
        cls._registry[str(action_id)] = str(key)
        if context is None:
            context = cls._infer_context(str(action_id))
        if context is not None:
            cls._contexts[str(action_id)] = context

    @classmethod
    def bind(
        cls,
        action_id: str,
        target: QWidget,
        callback: Callable[[], None],
        *,
        context: Qt.ShortcutContext = Qt.ShortcutContext.WidgetWithChildrenShortcut,
    ) -> QShortcut:
        key = cls._registry.get(action_id)
        if not key:
            raise ValueError(f"Unknown action_id: {action_id}")
        shortcut = QShortcut(QKeySequence(key), target)
        shortcut.setContext(context)
        shortcut.activated.connect(callback)
        return shortcut

    @classmethod
    def get_sequence(cls, action_id: str) -> QKeySequence:
        key = cls._registry.get(action_id, "")
        return QKeySequence(key)

    @classmethod
    def detect_conflicts(cls) -> list[tuple[str, str]]:
        seen: dict[tuple[str, Qt.ShortcutContext | None], str] = {}
        conflicts: list[tuple[str, str]] = []
        for action_id, key in cls._registry.items():
            context = cls._contexts.get(action_id)
            if context is None:
                context = cls._infer_context(action_id)
            signature = (key, context)
            other = seen.get(signature)
            if other and other != action_id:
                conflicts.append((other, action_id))
            seen[signature] = action_id

        if conflicts:
            logger = LogManager.get_logger("app.hotkeys")
            for first, second in conflicts:
                logger.warning(
                    "Hotkey conflict: %s and %s share %s",
                    first,
                    second,
                    cls._registry.get(first),
                )
        return conflicts
