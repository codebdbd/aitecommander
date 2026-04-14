from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.config_data.runtime_config import runtime_app_config as app_config

from ....common.constants import Timeout
from ..models.config_protocol import AppConfigAdapter, TopBarConfigProtocol
from ..models.topbar_constants import TOPBAR_CONSTANTS as C
from ..models.types import PanelLabel


@dataclass(frozen=True)
class PanelBounds:
    """Configuration bounds for a single panel."""

    minimum: int
    maximum: int


@dataclass(frozen=True)
class TopBarSettings:
    """Consolidated configuration for the top bar layout."""

    throttle_interval_ms: int
    log_info: bool
    min_search_width: int
    narrow_threshold: int
    button_size: int
    side_spacing: int
    data_ready_timeout_ms: int
    panel_bounds: Mapping[str, PanelBounds]


class TopBarConfigService:
    """Load and validate configuration related to the top-bar layout."""

    # Use centralized constants
    DEFAULT_LOG_INFO = C.DEFAULT_LOG_INFO
    DEFAULT_MIN_SEARCH_WIDTH = C.DEFAULT_MIN_SEARCH_WIDTH
    DEFAULT_MAX_RECENT = C.DEFAULT_MAX_RECENT
    DEFAULT_MAX_FAV = C.DEFAULT_MAX_FAV
    DEFAULT_MAX_QUICK = C.DEFAULT_MAX_QUICK
    DEFAULT_MIN_RECENT = C.DEFAULT_MIN_RECENT
    DEFAULT_MIN_FAV = C.DEFAULT_MIN_FAV
    DEFAULT_MIN_QUICK = C.DEFAULT_MIN_QUICK

    def __init__(self, config: TopBarConfigProtocol | None = None) -> None:
        if config is None:
            config = AppConfigAdapter(app_config)
        self._config = config
        self._ui = app_config.ui

    def load(self) -> TopBarSettings:
        throttle_ms = self._config.get_throttle_ms() or Timeout.THROTTLE_RESIZE
        log_info = self._config.get_log_info() if hasattr(self._config, "get_log_info") else self.DEFAULT_LOG_INFO
        min_search_width = self._config.get_search_min_width() or self.DEFAULT_MIN_SEARCH_WIDTH
        narrow_threshold = self._ui.get_topbar_narrow_threshold()
        button_size = self._config.get_button_size()
        side_spacing = self._config.get_side_spacing()
        data_ready_timeout_ms = Timeout.DATA_READY_FALLBACK

        panel_bounds = {
            PanelLabel.RECENT.value: self._build_bounds(
                minimum_key="topbar.min_visible.recent",
                maximum_key="topbar.max_visible.recent",
                minimum=self._config.get_min_visible("recent"),
                maximum=self._config.get_max_visible("recent"),
                default_min=self.DEFAULT_MIN_RECENT,
                default_max=self.DEFAULT_MAX_RECENT,
            ),
            PanelLabel.FAVORITES.value: self._build_bounds(
                minimum_key="topbar.min_visible.fav",
                maximum_key="topbar.max_visible.fav",
                minimum=self._config.get_min_visible("fav"),
                maximum=self._config.get_max_visible("fav"),
                default_min=self.DEFAULT_MIN_FAV,
                default_max=self.DEFAULT_MAX_FAV,
            ),
            PanelLabel.QUICK.value: self._build_bounds(
                minimum_key="topbar.min_visible.quick",
                maximum_key="topbar.max_visible.quick",
                minimum=self._config.get_min_visible("quick"),
                maximum=self._config.get_max_visible("quick"),
                default_min=self.DEFAULT_MIN_QUICK,
                default_max=self.DEFAULT_MAX_QUICK,
            ),
        }

        return TopBarSettings(
            throttle_interval_ms=throttle_ms,
            log_info=bool(log_info),
            min_search_width=int(min_search_width),
            narrow_threshold=int(narrow_threshold),
            button_size=int(button_size),
            side_spacing=int(side_spacing),
            data_ready_timeout_ms=int(data_ready_timeout_ms),
            panel_bounds=panel_bounds,
        )

    def _build_bounds(
        self,
        *,
        minimum_key: str,
        maximum_key: str,
        minimum: int | None,
        maximum: int | None,
        default_min: int,
        default_max: int,
    ) -> PanelBounds:
        min_value = self._validate_config_int(
            value=minimum,
            default=default_min,
            min_val=default_min,
            max_val=self._ui.get_topbar_max_visible_buttons(),
            config_key=minimum_key,
        )
        max_value = self._validate_config_int(
            value=maximum,
            default=default_max,
            min_val=default_min,
            max_val=self._ui.get_topbar_max_visible_buttons(),
            config_key=maximum_key,
        )

        # Ensure minimum does not exceed maximum
        if min_value > max_value:
            min_value = max_value

        return PanelBounds(minimum=min_value, maximum=max_value)

    @staticmethod
    def _validate_config_int(
        *,
        value: int | None,
        default: int,
        min_val: int,
        max_val: int,
        config_key: str,
    ) -> int:
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            return default

        if not min_val <= int_value <= max_val:
            return default
        return int_value
