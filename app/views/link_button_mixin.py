"""Mixin с общей логикой создания кнопок ссылок и поиска иконок.

Использование:
- Хост-класс должен предоставлять метод `_get_default_icon_path()`
  который возвращает pathlib.Path к иконке по умолчанию (с кэшированием).
- Миксин добавляет методы `_find_icon` и `_create_link_button`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Protocol, runtime_checkable

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import (
    resolve_icon_for_link,
    resolve_icon_path,
)

logger = logging.getLogger(__name__)


class LinkButtonMixin:
    @runtime_checkable
    class _HasDefaultIconPath(Protocol):
        def _get_default_icon_path(self) -> "Any":
            ...

    @runtime_checkable
    class _SupportsIconOps(Protocol):
        def _get_default_icon_path(self) -> "Any":
            ...

        def _find_icon(self, icon_path: str) -> str:
            ...

    def _find_icon(self: _HasDefaultIconPath, icon_path: str) -> str:
        """Возвращает путь к иконке через общий резолвер с fallback."""
        if not icon_path:
            return str(self._get_default_icon_path())
        try:
            resolved = resolve_icon_path(icon_path)
            return resolved or str(self._get_default_icon_path())
        except (OSError, FileNotFoundError, PermissionError) as e:
            logger.warning("Не удалось разрешить путь к иконке '%s': %s", icon_path, e)
            return str(self._get_default_icon_path())
        except Exception as e:
            logger.exception(
                "Неожиданная ошибка при разрешении иконки '%s': %s", icon_path, e
            )
            return str(self._get_default_icon_path())

    def _create_link_button(self: _SupportsIconOps, link_data: Dict[str, Any]) -> QToolButton:
        """Создаёт кнопку ссылки с иконкой, синхронизированной с таблицей."""
        button = QToolButton()

        button_size = app_config.ui.get_top_panel_button_size()
        icon_size = app_config.ui.get_top_panel_icon_size()
        button.setFixedSize(button_size, button_size)
        button.setIconSize(QSize(icon_size[0], icon_size[1]))
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        try:
            resolved_path = self._find_icon(resolve_icon_for_link(link_data))
            icon = create_icon_from_path(resolved_path)
            # Фолбэк: если иконка не создана или пуста — используем дефолтную
            if not icon or getattr(icon, "isNull", lambda: True)():
                fallback_path = str(self._get_default_icon_path())
                logger.warning(
                    "Иконка не создана/пустая для ссылки %r (path=%s). Используем дефолтную: %s",
                    link_data.get("name"),
                    resolved_path,
                    fallback_path,
                )
                icon = create_icon_from_path(fallback_path)
            button.setIcon(icon)
            # Диагностика фактических размеров и DPR
            try:
                from PyQt6.QtCore import QSize as _QSize
                from PyQt6.QtGui import QGuiApplication

                req_size = _QSize(icon_size[0], icon_size[1])
                actual = icon.actualSize(req_size)
                screen = QGuiApplication.primaryScreen()
                dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
                logger.debug(
                    "[TopBarIconDiag] name=%r path=%s req=%sx%s actual=%sx%s btn=%sx%s DPR=%.2f",
                    link_data.get("name"),
                    resolved_path,
                    req_size.width(),
                    req_size.height(),
                    actual.width(),
                    actual.height(),
                    button.size().width(),
                    button.size().height(),
                    dpr,
                )
            except Exception as diag_exc:
                logging.debug("[TopBarIconDiag] failed to log diagnostics: %s", diag_exc)
        except Exception as e:
            logger.warning(
                "Не удалось создать иконку для ссылки '%s': %s",
                link_data.get("name", "Unknown"),
                e,
            )
            # Гарантируем визуальный отклик — ставим иконку по умолчанию
            try:
                fallback_path = str(self._get_default_icon_path())
                button.setIcon(create_icon_from_path(fallback_path))
            except Exception:
                pass

        button.setToolTip(link_data.get("name", "Неизвестная ссылка"))
        return button
