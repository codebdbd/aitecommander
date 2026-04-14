"""Quick add panel widget for top bar."""

import logging
from typing import Any, Optional

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data.runtime_config import runtime_app_config as app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service
from app.views.widgets.base.base_panel_widgets import BaseTopPanelWidget
from app.views.widgets.protocols import WidgetConfigProtocol

logger = logging.getLogger(__name__)


class QuickAddPanelWidget(BaseTopPanelWidget):
    """Dedicated widget for quick add panel functionality."""

    def __init__(
        self,
        main_window=None,
        *,
        category_provider: Any | None = None,
        config: Optional[WidgetConfigProtocol] = None,
        batch_size: int = 0,
    ):
        """Initialize quick add panel.

        Args:
            main_window: Reference to main window
            config: Configuration provider (uses app_config if None)
            batch_size: Batch size for async population (0 = synchronous)
        """
        super().__init__(main_window, config=config, batch_size=batch_size)

        # Store category provider for quick add payloads
        # We'll get the category dynamically when needed, not during initialization
        self.category_provider = category_provider or main_window

        # Set object names for styling
        self.setObjectName("quickAddPanel")
        self.bg_frame.setObjectName("quickAddPanelBg")
        # Setup quick add buttons immediately
        self._setup_quick_buttons()

    def set_data(self, items: list) -> None:
        """Apply the common panel contract by rebuilding quick buttons."""
        _ = items  # Contract compatibility: external payload is ignored by design.
        self.refresh_buttons()
        self._sync_topbar_layout()

    def refresh_buttons(self) -> None:
        """Rebuild quick-add buttons (e.g., after theme change)."""
        try:
            self._clear_layout()
            self._setup_quick_buttons()
        except Exception:
            logger.debug("QuickAddPanelWidget: failed to refresh buttons", exc_info=True)

    def _setup_quick_buttons(self) -> None:
        """Creates quick add buttons based on application configuration."""
        quick_types = app_config.settings.get_quick_types()
        try:
            q_wh = app_config.ui.get_quick_add_button_size()
            bw = (
                int(q_wh[0])
                if isinstance(q_wh, (list, tuple)) and len(q_wh) >= 2
                else None
            )
            bh = (
                int(q_wh[1])
                if isinstance(q_wh, (list, tuple)) and len(q_wh) >= 2
                else None
            )
        except Exception:
            bw = bh = None
        if not bw or bw <= 0 or not bh or bh <= 0:
            fallback_btn = int(app_config.ui.get_top_panel_button_size())
            bw = bh = max(1, fallback_btn)

        try:
            icon_wh = app_config.ui.get_top_panel_icon_size()
            iw = (
                int(icon_wh[0])
                if isinstance(icon_wh, (list, tuple)) and len(icon_wh) >= 2
                else bw
            )
            ih = (
                int(icon_wh[1])
                if isinstance(icon_wh, (list, tuple)) and len(icon_wh) >= 2
                else bh
            )
        except Exception:
            iw, ih = bw, bh
        iw = max(1, min(iw, bw))
        ih = max(1, min(ih, bh))
        quick_type_tooltips = app_config.settings.get_quick_type_tooltips()

        for code, icon_name, tooltip in quick_types:
            btn = QToolButton()
            btn.setObjectName("quickButton")
            btn.setFixedSize(bw, bh)
            btn.setIconSize(QSize(iw, ih))
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

            # Set icon
            icon_path = icon_path_service.get_ui_icons_dir() / icon_name
            if icon_path.exists():
                btn.setIcon(create_icon_from_path(str(icon_path)))

            # Set tooltip
            btn.setToolTip(quick_type_tooltips.get(code, tooltip))

            # Connect click handler
            btn.clicked.connect(lambda _, ct=code: self._handle_quick_add(ct))

            # Add to layout
            self.panel_layout.addWidget(btn)

    def _handle_quick_add(self, link_type: str) -> None:
        """Handles quick add button click."""
        # Get current category dynamically when the button is clicked
        # This ensures we get the most up-to-date category selection
        category_id = self._get_current_category_id()

        payload = {
            "type": "quick_add",
            "link_type": link_type,
            "category_id": category_id,
        }

        # Emit unified signal
        self._emit_action_safely(payload)

    def _get_current_category_id(self) -> Optional[int]:
        """Get the current category ID dynamically."""
        if not self.category_provider:
            logger.debug("QuickAddPanelWidget: no category provider available")
            return None

        if hasattr(self.category_provider, "get_current_category_id"):
            try:
                category_id = self.category_provider.get_current_category_id()
                if category_id is not None:
                    logger.debug("QuickAddPanelWidget: got category_id=%s", category_id)
                    return category_id
                else:
                    logger.debug(
                        "QuickAddPanelWidget: get_current_category_id() returned None"
                    )
            except Exception as exc:
                logger.warning(
                    "QuickAddPanelWidget: failed to get current category: %s",
                    exc,
                )

        # Fallback: try to get category from facade if category_provider has one
        if hasattr(self.category_provider, "facade") and self.category_provider.facade:
            try:
                category_id = self.category_provider.facade.get_current_category_id()
                if category_id is not None:
                    logger.debug(
                        "QuickAddPanelWidget: got category_id from facade=%s",
                        category_id,
                    )
                    return category_id
            except Exception as exc:
                logger.debug(
                    "QuickAddPanelWidget: failed to get category from facade: %s", exc
                )

        logger.debug("QuickAddPanelWidget: no category_id available, using None")
        return None
