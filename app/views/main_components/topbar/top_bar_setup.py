# app/views/main_components/topbar/top_bar_setup.py - обновлен для новых компонентов
from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout

from app.views.main_components.topbar.top_bar_animator import TopBarAnimationManager
from app.views.main_components.topbar.top_bar_calculator import TopBarLayoutCalculator
from app.views.main_components.topbar.top_bar_config import TopBarConfig
from app.views.main_components.topbar.top_bar_event_handler import TopBarEventHandler
from app.views.main_components.topbar.top_bar_manager import TopBarLayoutManager

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
        logger.info("TopBarBuilder: starting build process")
        config = TopBarConfig()
        logger.info("TopBarBuilder: config created")
        calculator = TopBarLayoutCalculator(config)
        logger.info("TopBarBuilder: calculator created")
        animator = TopBarAnimationManager(config)
        logger.info("TopBarBuilder: animator created")
        event_handler = TopBarEventHandler(config)
        logger.info("TopBarBuilder: event_handler created")
        layout_manager = TopBarLayoutManager(self.window, config, calculator, animator, event_handler)
        logger.info("TopBarBuilder: layout_manager created")
        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )

        # Убираем верхний разделитель перед top bar: визуальную линию нарисует QMenuBar border-bottom

        # Create top_bar layout
        top_bar = QHBoxLayout()
        try:
            side = int(self.ui.get_top_bar_widgets_side_spacing())
        except (TypeError, ValueError, AttributeError):
            side = 8
            logger.warning("TopPanel: invalid side spacing in config; using default 8")
        top_bar.setContentsMargins(side, 0, side, 0)
        # Revert: keep spacing 0 for tight packing; separators control visual gaps
        top_bar.setSpacing(0)
        top_bar.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        logger.info("TopBarBuilder: top_bar layout created")

        # Build widgets with metrics via existing helper
        self.ui._build_top_bar_widgets_with_metrics(top_bar)
        logger.info("TopBarBuilder: widgets built")

        # Create and insert host
        top_bar_host = self.ui._create_top_bar_host(container_parent, top_bar)
        self.main_layout.addWidget(top_bar_host)
        self.window.top_bar_host = top_bar_host
        logger.info("TopBarBuilder: host created and inserted")

        # Инициализировать менеджер
        # Новый менеджер уже создан выше, просто сохраняем ссылку для очистки

        # Final metric
        self.ui._log_setup_top_panel_total(t_total_start)
