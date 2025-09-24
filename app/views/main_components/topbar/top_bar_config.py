"""Конфигурация топбара с типобезопасностью и валидацией."""
from __future__ import annotations

import logging
from typing import Dict, Any

from app.config_data import app_config

logger = logging.getLogger(__name__)


class TopBarConfig:
    """Управление конфигурацией топбара с типобезопасностью."""

    # Константы по умолчанию
    DEFAULT_THROTTLE_MS = 32
    DEFAULT_LOG_INFO = False
    DEFAULT_MIN_SEARCH_WIDTH = 148
    DEFAULT_MAX_RECENT = 10
    DEFAULT_MAX_FAV = 10
    DEFAULT_MAX_QUICK = 6
    DEFAULT_MIN_RECENT = 0
    DEFAULT_MIN_FAV = 0
    DEFAULT_MIN_QUICK = 0
    DEFAULT_NARROW_THRESHOLD = 800  # Увеличено до 800px для предотвращения ложного срабатывания
    DEFAULT_BUTTON_SIZE = 32
    DEFAULT_SPACER_SIZE = 4
    DEFAULT_ANIM_DURATION_MS = 140

    def __init__(self) -> None:
        """Инициализация конфигурации с загрузкой из app_config."""
        self._load_config()

    def _load_config(self) -> None:
        """Загружает конфигурацию из app_config с валидацией."""
        # Throttle для предотвращения избыточных пересчетов
        self.throttle_ms = self._get_cfg_int(
            "ui.topbar.throttle_ms", self.DEFAULT_THROTTLE_MS
        )

        # Логирование для отладки
        self.log_info = self._get_cfg_bool(
            "ui.topbar.log_info", self.DEFAULT_LOG_INFO
        )

        # Минимальная ширина поиска
        try:
            self.min_search_width = int(
                app_config.ui.get_top_panel_search_min_width()
            )
        except (AttributeError, TypeError, ValueError):
            self.min_search_width = self.DEFAULT_MIN_SEARCH_WIDTH

        # Максимальное количество кнопок в панелях
        self.max_recent = self.DEFAULT_MAX_RECENT
        self.max_fav = self.DEFAULT_MAX_FAV
        self.max_quick = self.DEFAULT_MAX_QUICK

        # Минимальные квоты для панелей
        try:
            min_visible = app_config.get("topbar.min_visible", {}) or {}
        except (AttributeError, TypeError, ValueError):
            min_visible = {}

        def _to_nonneg_int(value: Any, default: int = 0) -> int:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return default

        self.min_recent = _to_nonneg_int(min_visible.get("recent", 0))
        self.min_fav = _to_nonneg_int(min_visible.get("fav", 0))
        self.min_quick = _to_nonneg_int(min_visible.get("quick", 0))

        # Порог узкого режима
        self.narrow_threshold = self.DEFAULT_NARROW_THRESHOLD

        # Размер кнопок
        self.button_size = self._get_cfg_int(
            "ui.top_panel_button_size", self.DEFAULT_BUTTON_SIZE
        )

        # Настройки анимации
        self.anim_duration_ms = self.DEFAULT_ANIM_DURATION_MS
        self.anim_curve = "OutCubic"

        # Размер спейсеров
        self.spacer_size = self.DEFAULT_SPACER_SIZE

        logger.debug(
            f"TopBarConfig loaded: min_visible={{{self.min_recent},{self.min_fav},{self.min_quick}}}, "
            f"throttle_ms={self.throttle_ms}, min_search_width={self.min_search_width}"
        )

    def _get_cfg_int(self, key: str, default: int) -> int:
        """Безопасное получение целочисленной конфигурации."""
        try:
            return int(app_config.get(key, default))
        except (AttributeError, TypeError, ValueError):
            return default

    def _get_cfg_bool(self, key: str, default: bool) -> bool:
        """Безопасное получение булевой конфигурации."""
        try:
            return bool(app_config.get(key, default))
        except (AttributeError, TypeError, ValueError):
            return default

    def get_min_visible_for_panel(self, panel_name: str) -> int:
        """Получить минимальную квоту для указанной панели."""
        mapping = {
            "recent": self.min_recent,
            "fav": self.min_fav,
            "quick": self.min_quick,
        }
        return mapping.get(panel_name, 0)

    def get_max_for_panel(self, panel_name: str) -> int:
        """Получить максимум для указанной панели."""
        mapping = {
            "recent": self.max_recent,
            "fav": self.max_fav,
            "quick": self.max_quick,
        }
        return mapping.get(panel_name, 0)
