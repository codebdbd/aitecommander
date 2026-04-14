"""Сервис инициализации TopBarLayoutManager."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

from ..models.config_protocol import AppConfigAdapter, TopBarConfigProtocol
from ..models.panel_state import PanelDefinition
from ..models.topbar_constants import TOPBAR_CONSTANTS as C
from ..models.types import ButtonObjectName, PanelLabel
from .panel_visibility_manager import PanelVisibilityManager
from .visibility_solver import VisibilitySolver
from .width_calculator import WidthCalculator

if TYPE_CHECKING:
    from ...common.resource_manager import ResourceManager
    from ..models.types import TopBarWindow

logger = logging.getLogger(__name__)


class TopBarInitializationService:
    """Отвечает за инициализацию компонентов TopBarLayoutManager."""

    def __init__(
        self,
        window: TopBarWindow,
        config: TopBarConfigProtocol | None,
        resource_manager: ResourceManager,
    ) -> None:
        self.window = window
        self._resource_manager = resource_manager
        self._config = self._init_config(config)

    def _init_config(
        self, config: TopBarConfigProtocol | None
    ) -> TopBarConfigProtocol:
        """Инициализация конфигурации."""
        if config is None:
            from app.config_data.runtime_config import runtime_app_config as app_config

            config = AppConfigAdapter(app_config)
        return config

    def init_settings(self) -> dict[str, Any]:
        """Инициализация настроек из конфига."""
        return {
            "throttle_interval_ms": self._config.get_throttle_ms(),
            "log_info": self._config.get_log_info(),
            "min_search_width": self._config.get_search_min_width(),
            "narrow_threshold": C.DEFAULT_NARROW_THRESHOLD,
        }

    def init_panel_bounds(self) -> dict[str, int]:
        """Инициализация границ панелей (min/max visible)."""
        return {
            "max_recent": self._get_panel_max("recent", C.DEFAULT_MAX_RECENT),
            "max_fav": self._get_panel_max("fav", C.DEFAULT_MAX_FAV),
            "max_quick": self._get_panel_max("quick", C.DEFAULT_MAX_QUICK),
            "min_recent": self._get_panel_min("recent", C.DEFAULT_MIN_RECENT),
            "min_fav": self._get_panel_min("fav", C.DEFAULT_MIN_FAV),
            "min_quick": self._get_panel_min("quick", C.DEFAULT_MIN_QUICK),
        }

    def _get_panel_max(self, panel: str, default: int) -> int:
        """Получить максимальное количество видимых кнопок для панели."""
        return self._validate_config_int(
            self._config.get_max_visible(panel),
            default,
            C.MIN_VISIBLE_BUTTONS,
            C.MAX_VISIBLE_BUTTONS,
            f"topbar.max_visible.{panel}",
        )

    def _get_panel_min(self, panel: str, default: int) -> int:
        """Получить минимальное количество видимых кнопок для панели."""
        return self._validate_config_int(
            self._config.get_min_visible(panel),
            default,
            C.MIN_VISIBLE_BUTTONS,
            C.MAX_VISIBLE_BUTTONS,
            f"topbar.min_visible.{panel}",
        )

    def create_panel_definitions(
        self, bounds: dict[str, int]
    ) -> tuple[PanelDefinition, ...]:
        """Create panel definitions with resolved visibility bounds."""
        return (
            PanelDefinition(
                label=PanelLabel.RECENT.value,
                attr_name="recent_links_widget",
                button_object_name=ButtonObjectName.RECENT.value,
                min_visible=bounds["min_recent"],
                max_visible=bounds["max_recent"],
            ),
            PanelDefinition(
                label=PanelLabel.FAVORITES.value,
                attr_name="fav_widget",
                button_object_name=ButtonObjectName.FAVORITE.value,
                min_visible=bounds["min_fav"],
                max_visible=bounds["max_fav"],
            ),
            PanelDefinition(
                label=PanelLabel.QUICK.value,
                attr_name="quick_add_widget",
                button_object_name=ButtonObjectName.QUICK.value,
                min_visible=bounds["min_quick"],
                max_visible=bounds["max_quick"],
            ),
        )

    def init_services(
        self,
    ) -> dict[str, Any]:
        """Инициализация сервисов."""
        from .search_manager import SearchWidgetManager
        from .separator_service import SeparatorVisibilityService

        btn_size = self._config.get_button_size()
        width_calculator = WidthCalculator(button_size=btn_size)
        parent_widget = self.window if isinstance(self.window, QWidget) else None
        visibility_manager = PanelVisibilityManager(width_calculator, parent_widget)
        visibility_solver = VisibilitySolver(width_calculator)
        search_manager = SearchWidgetManager(width_calculator)
        separator_service = SeparatorVisibilityService(self._config)

        return {
            "width_calculator": width_calculator,
            "visibility_manager": visibility_manager,
            "visibility_solver": visibility_solver,
            "search_manager": search_manager,
            "separator_service": separator_service,
        }

    def init_timer(self, parent: QWidget, callback: Any) -> QTimer:
        """Инициализация throttle таймера."""
        timer = QTimer(parent)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        self._resource_manager.register_resource(timer)
        return timer

    def _validate_config_int(
        self,
        value: Any,
        default: int,
        min_val: int,
        max_val: int,
        config_key: str = "",
    ) -> int:
        """Валидация целочисленного значения из конфига."""
        try:
            int_value = int(value)
            if not min_val <= int_value <= max_val:
                logger.warning(
                    "Config %s=%s out of range [%s, %s], using default=%s",
                    config_key or "value",
                    int_value,
                    min_val,
                    max_val,
                    default,
                )
                return default
            return int_value
        except (ValueError, TypeError, AttributeError) as e:
            logger.debug("Failed to parse config %s: %s", config_key or "value", e)
            return default
        except Exception as e:
            logger.warning(
                "Unexpected error parsing config %s: %s", config_key or "value", e
            )
            return default

    def get_config(self) -> TopBarConfigProtocol:
        """Получить конфигурацию."""
        return self._config
