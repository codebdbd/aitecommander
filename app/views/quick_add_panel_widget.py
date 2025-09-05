"""Quick add panel widget for top bar."""

import logging
from typing import Optional

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QSizePolicy, QToolButton

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.path_service import icon_path_service
from app.views.base_panel_widgets import BaseTopPanelWidget


class QuickAddPanelWidget(BaseTopPanelWidget):
    """Dedicated widget for quick add panel functionality."""


    def __init__(self, main_window=None, category_provider: Optional[object] = None):
        super().__init__(main_window)
        self.category_provider = category_provider
        
        # Set object names for styling
        self.setObjectName("quickAddPanel")
        self.bg_frame.setObjectName("quickAddPanelBg")
        
        # Setup quick add buttons immediately
        self._setup_quick_buttons()

    def set_data(self, items: list) -> None:
        """Quick add panel doesn't use external data - buttons are configured from settings."""
        # Quick add panel is self-contained and doesn't need external data
        pass

    def _setup_quick_buttons(self) -> None:
        """Creates quick add buttons based on application configuration."""
        quick_types = app_config.settings.get_quick_types()
        button_size = app_config.ui.get_top_panel_button_size()
        icon_size = app_config.ui.get_top_panel_icon_size()
        quick_type_tooltips = app_config.settings.get_quick_type_tooltips()

        for code, icon_name, tooltip in quick_types:
            btn = QToolButton()
            btn.setObjectName("quickButton")
            btn.setFixedSize(button_size, button_size)
            btn.setIconSize(QSize(icon_size[0], icon_size[1]))
            # Keep buttons fixed size - panel can still shrink via layout
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
        category_id = None
        if self.category_provider and hasattr(
            self.category_provider, "get_current_category_id"
        ):
            try:
                category_id = self.category_provider.get_current_category_id()
            except Exception as exc:
                logging.warning(
                    "QuickAddPanelWidget: не удалось получить текущую категорию: %s", exc
                )
        
        payload = {
            "type": "quick_add",
            "link_type": link_type,
            "category_id": category_id,
        }
        
        # Emit unified signal
        self._emit_action_safely(payload)
