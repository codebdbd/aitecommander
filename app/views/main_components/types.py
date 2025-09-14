# app/views/main_components/types.py
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget


@runtime_checkable
class WindowUISetupProtocol(Protocol):
    """Протокол для объектов, предоставляющих API сборщикам панелей.

    Минимальный контракт, используемый текущими сборщиками:
    - атрибуты `window` и `main_layout`
    - хелперы верхней панели: `_build_top_bar_widgets_with_metrics`, `_create_top_bar_host`,
      `_init_and_schedule_topbar_manager`, `_log_setup_top_panel_total`
    - хелпер правой панели: `_setup_auto_hide_tree_filter`
    """

    # Атрибуты, используемые сборщиками
    # Оставляем окно как Any, т.к. у него большая поверхность API, используемая сборщиками
    window: Any
    main_layout: QVBoxLayout

    # --- Верхняя панель ---
    def _build_top_bar_widgets_with_metrics(self, top_bar: QHBoxLayout) -> None: ...

    def _create_top_bar_host(self, container_parent: QWidget, top_bar: QHBoxLayout) -> QWidget: ...

    def _init_and_schedule_topbar_manager(self) -> None: ...

    def _log_setup_top_panel_total(self, t_total_start: float) -> None: ...

    # --- Правая панель / общие хелперы ---
    def _setup_auto_hide_tree_filter(self, splitter_sizes: list[int]) -> None: ...
