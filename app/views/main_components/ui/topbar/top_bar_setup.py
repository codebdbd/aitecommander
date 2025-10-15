# app/views/main_components/top_bar_setup.py
from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout

from app.config_data import app_config

logger = logging.getLogger(__name__)


class TopBarBuilder:
    """Assemble the top bar using ``WindowUISetup`` helpers.

    Does not alter existing behavior.
    """

    def __init__(self, ui: Any) -> None:
        # ui is WindowUISetup; typed as Any to avoid circular imports
        self.ui = ui
        self.window = ui.window
        self.main_layout = ui.main_layout

    def build(self) -> None:
        """Construct and attach the top bar.

        Responsibilities:
        - Insert the top separator into the main layout.
        - Create and configure the top-bar layout (margins, spacing, alignment).
        - Populate the top bar via existing helpers
          (Quick/Favorites/Recent/Search).
        - Create the host widget, add it to ``self.main_layout``,
          set ``window.top_bar_host``.
        - Initialize ``TopBarLayoutManager`` and schedule post-shown
          adjustments.

        Note: the method preserves existing behavior
        (metrics, timing, visibility rules).
        """
        t_total_start = __import__("time").perf_counter()
        # Determine parent for helper widgets
        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )

        # Remove the previous top separator;
        # QMenuBar border-bottom draws the visual line

        # Create top_bar layout
        top_bar = QHBoxLayout()
        try:
            side = int(app_config.ui.get_top_bar_widgets_side_spacing())
        except (TypeError, ValueError):
            side = 8
            logger.warning("TopPanel: invalid side spacing in config; using default 8")
        top_bar.setContentsMargins(side, 0, side, 0)
        # Revert: keep spacing 0 for tight packing; separators control visual gaps
        top_bar.setSpacing(0)
        top_bar.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Build widgets with metrics via existing helper
        self.ui._build_top_bar_widgets_with_metrics(top_bar)

        # Create and insert host
        top_bar_host = self.ui._create_top_bar_host(container_parent, top_bar)
        self.main_layout.addWidget(top_bar_host)
        self.window.top_bar_host = top_bar_host

        # Init and schedule layout manager post-shown tasks
        self.ui._init_and_schedule_topbar_manager()

        # Final metric
        self.ui._log_setup_top_panel_total(t_total_start)
