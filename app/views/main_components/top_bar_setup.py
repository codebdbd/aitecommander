# app/views/main_components/top_bar_setup.py
from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from app.config_data import app_config

logger = logging.getLogger(__name__)


class TopBarBuilder:
    """Собирает верхнюю панель, используя хелперы WindowUISetup (без изменения поведения)."""

    def __init__(self, ui: Any) -> None:
        # ui is WindowUISetup; typed as Any to avoid circular imports
        self.ui = ui
        self.window = ui.window
        self.main_layout = ui.main_layout

    def build(self) -> None:
        """Собирает и подключает верхнюю панель (top bar).

        Обязанности:
        - Вставить верхний разделитель в основной layout
        - Создать и настроить layout верхней панели (отступы, spacing, выравнивание)
        - Заполнить верхнюю панель виджетами через существующие хелперы (Quick/Favorites/Recent/Search)
        - Создать хост‑виджет, добавить его в `self.main_layout`, установить `window.top_bar_host`
        - Инициализировать `TopBarLayoutManager` и запланировать post‑shown корректировки

        Примечание: метод полностью сохраняет текущее поведение (метрики, тайминги, правила видимости).
        """
        t_total_start = __import__("time").perf_counter()
        # Determine parent for helper widgets
        container_parent = getattr(self.main_layout, "parentWidget", lambda: None)() or self.window.centralWidget()

        # Top separator
        self.ui._add_top_separator(container_parent)

        # Create top_bar layout
        top_bar = QHBoxLayout()
        try:
            side = int(app_config.ui.get_top_bar_widgets_side_spacing())
        except (TypeError, ValueError):
            side = 8
            logger.warning("TopPanel: invalid side spacing in config; using default 8")
        top_bar.setContentsMargins(side, 0, side, 0)
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
