# app/views/main_components/right_panel_setup.py
from __future__ import annotations

import logging
from typing import Any, cast
from app.views.main_components.types import WindowUISetupProtocol

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.views.tiles import CategoryTiles
from app.views.link import LinksTableView

logger = logging.getLogger(__name__)


class RightPanelBuilder:
    """Builds the right panel using existing WindowUISetup helpers (no behavior change)."""

    def __init__(self, ui: WindowUISetupProtocol) -> None:
        # ui is WindowUISetup; typed as Any to avoid circular imports
        self.ui = ui
        self.window = ui.window
        self.main_layout = ui.main_layout

    def build(self, mid: QHBoxLayout) -> None:
        """Собирает и подключает правую панель (плитки + таблица + сплиттер).

        Обязанности:
        - Создать область плиток (scroll + обёртка плиток) и область таблицы (обёртка)
        - Собрать `QStackedLayout` с плитками и таблицей, установить `window.table_container`
        - Построить контейнер правой панели с отступами/spacing из UIConfig
        - Создать и настроить `QSplitter`, добавить левую и правую панели, задать факторы/размеры
        - Инициализировать фильтр авто‑скрытия дерева и политики фокуса в соответствии с прежним поведением

        Примечание: метод сохраняет существующее поведение и проводку к UI‑состоянию и метрикам.
        """
        # Контейнер для правой панели создаём сразу, чтобы быть родителем для обёрток
        right_panel = QWidget()

        # Плитки категорий — создаём с валидной иерархией родителей
        cast(Any, self.window).tiles_scroll = QScrollArea(parent=right_panel)
        cast(Any, self.window).tiles_scroll.setWidgetResizable(True)
        cast(Any, self.window).tiles = CategoryTiles(parent=cast(Any, self.window).tiles_scroll)

        # Подключение к UIStateManager
        cast(Any, self.window).tiles.category_selected.connect(
            lambda cat_id: self.window.ui_state.load_category(
                cat_id, source="CategoryTiles"
            )
        )

        cast(Any, self.window).tiles_scroll.setWidget(cast(Any, self.window).tiles)

        tiles_wrapper = QWidget(parent=right_panel)
        tiles_layout = QVBoxLayout(tiles_wrapper)
        tiles_layout.setContentsMargins(*app_config.ui.get_layout_margins("tiles"))
        tiles_layout.setSpacing(app_config.ui.get_tiles_layout_spacing())
        tiles_layout.addWidget(self.window.tiles_scroll)

        # Таблица
        cast(Any, self.window).table = LinksTableView(self.window)

        # Обертка для таблицы
        table_wrapper = QWidget(parent=right_panel)
        table_layout = QVBoxLayout(table_wrapper)
        table_layout.setContentsMargins(*app_config.ui.get_layout_margins("table"))
        table_layout.setSpacing(app_config.ui.get_table_layout_spacing())
        table_layout.addWidget(cast(Any, self.window).table)

        # Стек
        cast(Any, self.window).stack = QStackedLayout()
        cast(Any, self.window).stack.addWidget(tiles_wrapper)
        # Совместимость с существующим API: либо сам виджет таблицы, либо её контейнер
        cast(Any, self.window).table_container = table_wrapper
        cast(Any, self.window).stack.addWidget(table_wrapper)

        # Контейнер правой панели
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(*app_config.ui.get_layout_margins("right"))
        # Строго используем UIConfig API (релиз): метод гарантирован
        spacing = int(app_config.ui.get_right_layout_spacing())
        right_layout.setSpacing(spacing)
        right_layout.addLayout(cast(Any, self.window).stack)

        # Сплиттер
        cast(Any, self.window).splitter = self._create_splitter()
        cast(Any, self.window).splitter.addWidget(cast(Any, self.window).left_panel)
        cast(Any, self.window).splitter.addWidget(right_panel)
        try:
            cast(Any, self.window).splitter.setCollapsible(0, True)
        except (RuntimeError, TypeError):
            logger.debug(
                "RightPanel: failed to set splitter collapsible(0, True)", exc_info=True
            )

        stretch_factors = app_config.ui.get_splitter_stretch_factors()
        cast(Any, self.window).splitter.setStretchFactor(0, stretch_factors[0])
        cast(Any, self.window).splitter.setStretchFactor(1, stretch_factors[1])
        mid.addWidget(cast(Any, self.window).splitter)

        splitter_sizes = app_config.ui.get_splitter_sizes()
        cast(Any, self.window).splitter.setSizes(splitter_sizes)
        cast(Any, self.window)._first_structure_load = True

        # Автоскрытие дерева
        self.ui._setup_auto_hide_tree_filter(splitter_sizes)

        # QStackedLayout ломает стандартную Tab-навигацию Qt — исключаем нижнюю панель из Tab
        if hasattr(self.window, "bottom_bar_container"):
            self.window.bottom_bar_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    # --- Internals ---
    def _create_splitter(self):
        # Импортируем здесь, чтобы избежать лишних зависимостей на уровне модуля
        from PyQt6.QtCore import Qt as _Qt
        from PyQt6.QtWidgets import QSplitter

        from app.config_data import app_config as _cfg

        splitter = QSplitter()
        try:
            handle_w = int(_cfg.ui.get_splitter_handle_width())
        except (TypeError, ValueError):
            handle_w = 1
        try:
            splitter.setHandleWidth(max(1, handle_w))
        except Exception:
            logger.debug(
                "RightPanel: failed to set splitter handle width", exc_info=True
            )
        try:
            splitter.setOrientation(_Qt.Orientation.Horizontal)
        except Exception:
            logger.debug(
                "RightPanel: failed to set splitter orientation", exc_info=True
            )
        try:
            splitter.setChildrenCollapsible(True)
        except Exception:
            logger.debug(
                "RightPanel: failed to set children collapsible", exc_info=True
            )
        return splitter
