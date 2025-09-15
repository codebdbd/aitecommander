# app/views/main_components/window_ui_setup.py

from __future__ import annotations

import logging
import os
import sys
import time
from functools import partial
from typing import Any, Optional

from PyQt6.QtCore import QEvent, QObject, QSize, QTimer
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.controllers.ui.undo.stack import UndoManager
from app.controllers.ui.menu_controller import MenuController
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.views.custom_widgets import StructureTreeView
from app.views.favorites_panel_widget import FavoritesPanelWidget
from app.views.main_components.top_bar_layout_manager import TopBarLayoutManager
from app.views.models.structure_tree_model import StructureTreeModel
from app.views.quick_add_panel_widget import QuickAddPanelWidget
from app.views.recent_panel_widget import RecentPanelWidget
from app.views.status_bar import setup_status_bar as init_status_bar

logger = logging.getLogger(__name__)


class _AutoHideTreeFilter(QObject):
    """Фильтр событий адаптации UI при узком окне.
    При ширине окна <= threshold:
      - сворачивает левую панель (splitter: left=0)
      - скрывает панели топ-бара (QuickAdd, Favorites, Recent), оставляя только поиск
      - переключает правую область на таблицу (table-only)
    При расширении окна восстанавливает предыдущее состояние.
    """

    def __init__(
        self,
        window,
        threshold_width: int,
        default_sizes: list[int],
        logger_: logging.Logger = logger,
    ):
        super().__init__(window)
        self.window = window
        self.threshold = int(threshold_width)
        self.default_sizes = (
            default_sizes[:] if isinstance(default_sizes, (list, tuple)) else [250, 750]
        )
        self._is_collapsed = False
        self._saved_splitter_sizes = None
        self._prev_stack_index = None
        self._logger = logger_
        # Сохраняем исходное состояние collapsible(0), чтобы корректно восстановить при расширении окна
        self._saved_splitter_collapsible0 = None

    def _apply(self):
        w = self.window.width()
        splitter = getattr(self.window, "splitter", None)
        stack = getattr(self.window, "stack", None)
        table = getattr(self.window, "table", None)

        if w <= self.threshold:
            # Если ещё не сворачивали — сохранить состояние и свернуть левую панель, переключить стек на таблицу
            if not self._is_collapsed:
                try:
                    if splitter is not None:
                        self._saved_splitter_sizes = splitter.sizes()
                except (AttributeError, RuntimeError):
                    self._saved_splitter_sizes = None
                    self._logger.debug(
                        "AutoHideTree: failed to read splitter sizes", exc_info=True
                    )
                try:
                    if stack is not None:
                        self._prev_stack_index = stack.currentIndex()
                except (AttributeError, RuntimeError):
                    self._prev_stack_index = None
                    self._logger.debug(
                        "AutoHideTree: failed to read current stack index",
                        exc_info=True,
                    )

                if splitter is not None:
                    try:
                        # Сохраняем исходное состояние collapsible(0) перед принудительным включением
                        try:
                            self._saved_splitter_collapsible0 = splitter.isCollapsible(0)
                        except (AttributeError, RuntimeError):
                            self._saved_splitter_collapsible0 = None
                            self._logger.debug(
                                "AutoHideTree: failed to read splitter collapsible(0)",
                                exc_info=True,
                            )
                        splitter.setCollapsible(0, True)
                        splitter.setSizes([0, max(1, w)])
                    except (RuntimeError, TypeError):
                        self._logger.debug(
                            "AutoHideTree: failed to collapse left panel on narrow window",
                            exc_info=True,
                        )

                # Переключение правой области на таблицу делаем опциональным (по умолчанию — выключено),
                # чтобы не скрывать плитки категорий при сжатии.
                try:
                    switch_to_table = bool(app_config.ui.get_auto_hide_switch_to_table())
                except Exception:
                    switch_to_table = False
                if switch_to_table and stack is not None and table is not None:
                    try:
                        # Совместимость: таблица может быть добавлена как сам виджет или как контейнер
                        table_container = getattr(self.window, "table_container", None)
                        for i in range(stack.count()):
                            wgt = stack.widget(i)
                            if wgt is table or (
                                table_container is not None and wgt is table_container
                            ):
                                stack.setCurrentIndex(i)
                                break
                    except (AttributeError, RuntimeError):
                        self._logger.debug(
                            "AutoHideTree: failed to switch stack to table",
                            exc_info=True,
                        )
                self._is_collapsed = True

            # Независимо от состояния — скрыть панели топ-бара на каждом вызове (на случай добавления новых)
            for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
                try:
                    panel = getattr(self.window, attr, None)
                    if panel is not None:
                        panel.setVisible(False)
                except (AttributeError, RuntimeError):
                    self._logger.debug(
                        "AutoHideTree: failed to hide top bar panel '%s'",
                        attr,
                        exc_info=True,
                    )

        elif w > self.threshold and self._is_collapsed:
            # Восстановить размеры сплиттера
            if splitter is not None:
                try:
                    if (
                        self._saved_splitter_sizes
                        and len(self._saved_splitter_sizes) == 2
                    ):
                        splitter.setSizes(self._saved_splitter_sizes)
                    else:
                        sizes = [int(x) for x in self.default_sizes]
                        splitter.setSizes(sizes)
                    # Восстановить исходный флаг collapsible(0), если он был сохранён
                    try:
                        if self._saved_splitter_collapsible0 is not None:
                            splitter.setCollapsible(0, bool(self._saved_splitter_collapsible0))
                    except (RuntimeError, TypeError, AttributeError):
                        self._logger.debug(
                            "AutoHideTree: failed to restore splitter collapsible(0)",
                            exc_info=True,
                        )
                except (RuntimeError, TypeError, ValueError):
                    self._logger.debug(
                        "AutoHideTree: failed to restore splitter sizes", exc_info=True
                    )

            # Показать панели топ-бара обратно
            for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
                try:
                    panel = getattr(self.window, attr, None)
                    if panel is not None:
                        panel.setVisible(True)
                except (AttributeError, RuntimeError):
                    self._logger.debug(
                        "AutoHideTree: failed to re-show top bar panel '%s'",
                        attr,
                        exc_info=True,
                    )

            # Восстановить предыдущий вид правой области (если был сохранён)
            if stack is not None and self._prev_stack_index is not None:
                try:
                    if 0 <= self._prev_stack_index < stack.count():
                        stack.setCurrentIndex(self._prev_stack_index)
                except (RuntimeError, ValueError, TypeError, AttributeError):
                    self._logger.debug(
                        "AutoHideTree: failed to restore previous stack index",
                        exc_info=True,
                    )

            self._is_collapsed = False
            # Сбрасываем сохранённые значения после восстановления
            self._saved_splitter_sizes = None
            self._saved_splitter_collapsible0 = None

    def eventFilter(self, obj, event):
        if obj is self.window and event.type() == QEvent.Type.Resize:
            self._apply()
        return super().eventFilter(obj, event)


class WindowUISetup:
    """Компонент для настройки UI-элементов главного окна."""

    def __init__(self, window_initializer: Any) -> None:
        self.window_initializer = window_initializer
        self.window = window_initializer.window
        self.settings = window_initializer.settings
        self.theme_ctrl = window_initializer.theme_ctrl

        # main_layout будет установлен позже
        self.main_layout = None

    def setup_basic_attributes(self) -> None:
        """Настройка базовых атрибутов окна."""
        self.window.settings = self.window_initializer.settings
        self.window.theme_ctrl = self.window_initializer.theme_ctrl
        self.window.current_category_id = None
        # Используем единый глобальный пул потоков из TaskScheduler
        self.window.thread_pool = get_task_scheduler().get_thread_pool()
        self.window.undo_stack = UndoManager(self.window)
        self.window.sphere_buttons = {}

    def setup_menu(self) -> None:
        """Настройка меню."""
        self.window.menu_controller = MenuController(self.window)
        self.window.setMenuBar(self.window.menu_controller.create_main_menu())

    def setup_central_widget(self) -> None:
        """Настройка центрального виджета."""
        central = QFrame()
        # Заполняем фон сразу, чтобы избежать белой вспышки до применения содержимого
        try:
            central.setAutoFillBackground(True)
        except Exception:
            logger.debug(
                "WindowUISetup: setAutoFillBackground failed on central frame",
                exc_info=True,
            )
        central.setFrameShape(
            getattr(QFrame.Shape, app_config.ui.get_central_frame_shape())
        )
        self.window.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(*app_config.ui.get_main_layout_margins())
        # Возвращаем spacing из конфигурации
        self.main_layout.setSpacing(app_config.ui.get_main_layout_spacing())
        # Убираем зазор между QMenuBar и верхним разделителем: верхний margin = 0
        try:
            left, _top, r, b = self.main_layout.getContentsMargins()
        except Exception:
            left, _top, r, b = (0, 0, 0, 0)
        try:
            self.main_layout.setContentsMargins(left, 0, r, b)
        except Exception:
            logger.debug(
                "WindowUISetup: failed to force top margin=0 for main_layout",
                exc_info=True,
            )

    def setup_top_panel(self) -> None:
        """Настройка верхней панели."""
        from .top_bar_setup import TopBarBuilder

        TopBarBuilder(self).build()

    def _add_top_separator(self, container_parent: QWidget) -> None:
        """Добавляет верхний горизонтальный разделитель в основной layout."""
        h_line_top = QWidget(container_parent)
        h_line_top.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_top)

    def _build_top_bar_widgets_with_metrics(self, top_bar: QHBoxLayout) -> None:
        """Строит виджеты верхней панели и логирует длительность."""
        t_widgets_start = time.perf_counter()
        self.setup_top_bar_widgets(top_bar)
        t_widgets_dur = (time.perf_counter() - t_widgets_start) * 1000.0
        try:
            logger.info(
                "TopPanelMetrics: setup_top_bar_widgets: %.1f ms", t_widgets_dur
            )
        except Exception:
            logger.debug(
                "TopPanelMetrics: failed to log setup_top_bar_widgets duration",
                exc_info=True,
            )

    def _create_top_bar_host(
        self, container_parent: QWidget, top_bar: QHBoxLayout
    ) -> QWidget:
        """Создаёт хост-виджет для top_bar и применяет базовые параметры."""
        top_bar_host = QWidget(container_parent)
        top_bar_host.setObjectName("topBarHost")
        top_bar_host.setLayout(top_bar)
        try:
            top_bar_host.setFixedHeight(app_config.ui.get_top_bar_height())
            top_bar_host.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
        except (RuntimeError, TypeError, AttributeError):
            logger.warning(
                "TopPanel: failed to set top bar host size policy/height", exc_info=True
            )
        # Изначально скрываем top_bar_host, чтобы исключить растягивание/дерганье отступов до первого adjust()
        try:
            top_bar_host.setVisible(False)
        except Exception:
            logger.debug(
                "TopPanel: failed to initially hide top_bar_host", exc_info=True
            )
        return top_bar_host

    def _init_and_schedule_topbar_manager(self) -> None:
        """Создаёт TopBarLayoutManager и планирует post-shown обработчики."""
        try:
            self.window._topbar_manager = TopBarLayoutManager(self.window)
        except (RuntimeError, TypeError):
            # Не блокируем инициализацию UI при ошибке менеджера
            self.window._topbar_manager = None
            logger.exception("TopPanel: failed to initialize TopBarLayoutManager")
            return
        try:
            mgr = getattr(self.window, "_topbar_manager", None)
            if not mgr:
                return
            if hasattr(self.window, "shown"):
                # type: ignore[attr-defined]
                # Пересчитать и показать атомарно: сначала adjust, затем показать хост
                self.window.shown.connect(
                    partial(self._post_shown_adjust_and_show_host, mgr)
                )
                # Повторный проход через ~1 кадр для страховки
                self.window.shown.connect(partial(self._post_shown_second_adjust, mgr))
            else:
                # Фолбэк: если сигнала shown нет, пересчитать в следующий тик дважды
                self._fallback_schedule_adjusts(mgr)
        except Exception:
            logger.debug(
                "TopPanel: failed to schedule post-shown topbar adjusts", exc_info=True
            )

    def _post_shown_adjust_and_show_host(self, mgr: TopBarLayoutManager) -> None:  # type: ignore[name-defined]
        """В первый тик после shown: adjust и показать host атомарно."""
        try:
            from functools import partial

            QTimer.singleShot(0, partial(self._invoke_adjust_and_show_host, mgr))
        except Exception:
            logger.debug(
                "TopPanel: failed in _post_shown_adjust_and_show_host", exc_info=True
            )

    def _post_shown_second_adjust(self, mgr: TopBarLayoutManager) -> None:  # type: ignore[name-defined]
        """Во второй тик после shown: повторный adjust для устойчивости."""
        try:
            # Завершим прогрев и покажем топ-бар только после «боевого» adjust
            QTimer.singleShot(16, lambda: self._finalize_topbar_show(mgr))
        except Exception:
            logger.debug("TopPanel: failed in _post_shown_second_adjust", exc_info=True)

    def _fallback_schedule_adjusts(self, mgr: TopBarLayoutManager) -> None:  # type: ignore[name-defined]
        """Фолбэк при отсутствии сигнала shown: два последовательных планирования."""
        try:
            from functools import partial

            QTimer.singleShot(0, partial(self._invoke_adjust_and_show_host, mgr))
            QTimer.singleShot(16, partial(self._invoke_adjust, mgr))
        except Exception:
            logger.debug(
                "TopPanel: failed in _fallback_schedule_adjusts", exc_info=True
            )

    def _invoke_adjust_and_show_host(self, mgr: TopBarLayoutManager) -> None:  # type: ignore[name-defined]
        """Выполняет пересчёт лэйаута и показывает host-виджет безопасно."""
        try:
            mgr.adjust()
        except Exception:
            logger.debug(
                "TopPanel: adjust() failed in _invoke_adjust_and_show_host",
                exc_info=True,
            )

    def _invoke_adjust(self, mgr: TopBarLayoutManager) -> None:  # type: ignore[name-defined]
        """Безопасно вызывает mgr.adjust()."""
        try:
            mgr.adjust()
        except Exception:
            logger.debug("TopPanel: adjust() failed in _invoke_adjust", exc_info=True)

    def _finalize_topbar_show(self, mgr: TopBarLayoutManager) -> None:  # type: ignore[name-defined]
        """Сбрасывает warmup, выполняет боевой adjust, затем показывает host и делает финальный adjust."""
        try:
            # Импортируем лениво, чтобы избежать циклов
            from app.utils.ui.updates import suspend_updates
        except Exception:
            suspend_updates = None  # type: ignore

        try:
            if suspend_updates is not None:
                with suspend_updates(self.window):
                    # Сбросить прогрев, чтобы следующий adjust был боевым
                    try:
                        if hasattr(mgr, "_warmup_adjusts_remaining"):
                            setattr(mgr, "_warmup_adjusts_remaining", 0)
                    except Exception:
                        logger.debug("TopBar: failed to reset warmup flag", exc_info=True)
                    # Боевой adjust на скрытом host (контейнер уже создан)
                    try:
                        mgr.adjust()
                    except Exception:
                        logger.debug("TopBar: adjust() failed before host show", exc_info=True)
                    # Перед показом top_bar_host инициируем первичную загрузку данных панелей,
                    # чтобы лэйаут пересчитался уже с учётом видимых кнопок
                    try:
                        tpc = getattr(self.window, "top_panels_controller", None)
                        if tpc and hasattr(tpc, "refresh_all"):
                            tpc.refresh_all()
                    except Exception:
                        logger.debug("TopBar: top_panels_controller.refresh_all() failed", exc_info=True)
                    # Показать host
                    try:
                        self.window.top_bar_host.setVisible(True)
                    except Exception:
                        logger.debug("TopBar: failed to show top_bar_host in finalize", exc_info=True)
                    # Финальный adjust уже на видимом контейнере
                    try:
                        mgr.adjust()
                    except Exception:
                        logger.debug("TopBar: final adjust() failed after host show", exc_info=True)
            else:
                # Fallback без приостановки обновлений
                try:
                    if hasattr(mgr, "_warmup_adjusts_remaining"):
                        setattr(mgr, "_warmup_adjusts_remaining", 0)
                except Exception:
                    logger.debug("TopBar: failed to reset warmup flag (no suspend)", exc_info=True)
                try:
                    mgr.adjust()
                except Exception:
                    logger.debug("TopBar: adjust() failed before host show (no suspend)", exc_info=True)
                # Перед показом инициируем загрузку панелей
                try:
                    tpc = getattr(self.window, "top_panels_controller", None)
                    if tpc and hasattr(tpc, "refresh_all"):
                        tpc.refresh_all()
                except Exception:
                    logger.debug("TopBar: top_panels_controller.refresh_all() failed (no suspend)", exc_info=True)
                try:
                    self.window.top_bar_host.setVisible(True)
                except Exception:
                    logger.debug("TopBar: failed to show top_bar_host (no suspend)", exc_info=True)
                try:
                    mgr.adjust()
                except Exception:
                    logger.debug("TopBar: final adjust() failed after host show (no suspend)", exc_info=True)
        except Exception:
            logger.debug("TopBar: finalize_topbar_show unexpected error", exc_info=True)

    def _log_setup_top_panel_total(self, t_total_start: float) -> None:
        """Логирует итоговую длительность настройки верхней панели."""
        try:
            t_total_dur = (time.perf_counter() - t_total_start) * 1000.0
            logger.info("TopPanelMetrics: setup_top_panel total: %.1f ms", t_total_dur)
        except Exception:
            logger.debug(
                "TopPanelMetrics: failed to log setup_top_panel total", exc_info=True
            )

    def _create_top_panel_widget(
        self,
        top_bar: QHBoxLayout,
        mode: str,
        attr_name: str,
        object_name: Optional[str],
        log_label: str,
    ) -> None:
        """Фабрика для создания и добавления виджета верхней панели с обработкой ошибок."""
        t_start = time.perf_counter()
        try:
            if mode == "quick":
                widget = QuickAddPanelWidget(self.window, category_provider=self.window)
            elif mode == "favorites":
                widget = FavoritesPanelWidget(self.window)
            elif mode == "recent":
                widget = RecentPanelWidget(self.window)
            else:
                raise ValueError(f"Unknown panel mode: {mode}")
            if object_name:
                widget.setObjectName(object_name)
            widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            # Изначально скрываем панель до первого пересчёта TopBarLayoutManager,
            # чтобы исключить стартовое перекрытие до применения видимых количеств
            try:
                widget.setVisible(False)
                # Жёстко ограничиваем стартовую ширину в 0, до момента первого пересчёта
                widget.setMaximumWidth(0)
            except Exception:
                logger.debug(
                    "TopPanel: failed to set initial invisible state on %s widget",
                    log_label,
                    exc_info=True,
                )
            # Жестко фиксируем высоту панелей топ-бара, чтобы исключить изменение высоты
            # после показа окна при отложенных перерисовках/обновлениях данных и тем.
            try:
                try:
                    search_h = int(app_config.ui.get_top_panel_search_height())
                except (TypeError, ValueError):
                    search_h = 32
                try:
                    btn_h = int(app_config.ui.get_top_panel_button_size())
                except (TypeError, ValueError):
                    btn_h = 32
                fixed_h = max(search_h, btn_h)
            except Exception:
                fixed_h = 32
            try:
                widget.setFixedHeight(fixed_h)
            except Exception:
                logger.debug(
                    "TopPanel: failed to set fixed height on %s widget",
                    log_label,
                    exc_info=True,
                )
            # Разрешаем горизонтальное сжатие ниже sizeHint, чтобы убирать мерцание при нехватке ширины
            try:
                widget.setMinimumWidth(0)
            except Exception:
                logger.debug(
                    "TopPanel: failed to set minimum width on %s widget",
                    log_label,
                    exc_info=True,
                )
            setattr(self.window, attr_name, widget)
            top_bar.addWidget(widget)
            # Reduce spacing between buttons by 1px only for top-bar panels to gain a tiny width budget
            try:
                lay = getattr(widget, "panel_layout", None)
                if lay is not None and hasattr(lay, "spacing") and hasattr(lay, "setSpacing"):
                    cur = int(lay.spacing())
                    lay.setSpacing(max(0, cur - 1))
            except Exception:
                logger.debug(
                    "TopPanel: failed to reduce panel button spacing by 1px for %s",
                    log_label,
                    exc_info=True,
                )
            try:
                dur = (time.perf_counter() - t_start) * 1000.0
                logger.info(
                    "TopPanelMetrics: create_widget[%s]: %.1f ms", log_label, dur
                )
            except Exception:
                logger.debug(
                    "TopPanelMetrics: failed to log create_widget[%s] duration",
                    log_label,
                    exc_info=True,
                )
        except Exception:
            setattr(self.window, attr_name, None)
            logger.exception("TopPanel: failed to create %s widget", log_label)

    def setup_top_bar_widgets(self, top_bar: QHBoxLayout) -> None:
        """Настройка виджетов верхней панели.
        Создаём и добавляем все панели сразу, без отложенных прослоек:
        Порядок: QuickAdd → Favorites → Recent → Search
        """
        # Параметризованное создание QuickAdd, Favorites, Recent
        widgets_params = [
            ("quick", "quick_add_widget", None, "QuickAdd"),
            ("favorites", "fav_widget", "favoritesWidget", "Favorites"),
            ("recent", "recent_links_widget", "recentLinksWidget", "Recent"),
        ]
        for idx, (mode, attr_name, obj_name, label) in enumerate(widgets_params):
            self._create_top_panel_widget(top_bar, mode, attr_name, obj_name, label)
            # Вставляем вертикальный разделитель между соседними панелями
            if idx < len(widgets_params) - 1:
                try:
                    top_bar.addSpacing(4)
                    top_bar.addWidget(self._create_vertical_separator())
                    top_bar.addSpacing(4)
                except Exception:
                    logger.debug(
                        "TopPanel: failed to insert vertical separator between panels",
                        exc_info=True,
                    )

        # Разделитель перед поиском
        try:
            top_bar.addSpacing(4)
            top_bar.addWidget(self._create_vertical_separator())
            top_bar.addSpacing(4)
        except Exception:
            logger.debug(
                "TopPanel: failed to insert vertical separator before search",
                exc_info=True,
            )

        # Поиск (в конце)
        self.setup_search_widget(top_bar)

    def _create_vertical_separator(self) -> QWidget:
        """Создаёт вертикальный разделитель по аналогии с горизонтальными.
        Толщина берётся из ui.get_separator_width(), цвет/стиль — из QSS по классу 'separator'.
        """
        sep = QWidget()
        sep.setObjectName("vSeparator")
        # Используем отдельный класс, чтобы не конфликтовать со стилем горизонтальных разделителей
        sep.setProperty("class", "vertical_separator")
        try:
            w = int(app_config.ui.get_separator_width())
        except (TypeError, ValueError):
            w = 1
        try:
            sep.setFixedWidth(max(1, w))
        except Exception:
            logger.debug(
                "TopPanel: failed to set fixed width on vertical separator",
                exc_info=True,
            )
        try:
            sep.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        except Exception:
            logger.debug(
                "TopPanel: failed to set size policy on vertical separator",
                exc_info=True,
            )
        return sep

    def setup_search_widget(self, top_bar: QHBoxLayout) -> None:
        """Настройка поля поиска."""
        t_start = time.perf_counter()
        self.window.search = QLineEdit()
        self.window.search.setPlaceholderText(app_config.ui.get_search_placeholder())
        self.window.search.setClearButtonEnabled(True)
        # Высота поля поиска берётся из конфигурации
        try:
            self.window.search.setFixedHeight(
                int(app_config.ui.get_top_panel_search_height())
            )
        except (TypeError, ValueError, RuntimeError):
            self.window.search.setFixedHeight(32)
            logger.warning("SearchWidget: invalid search height in config; using 32")
        # Политика размеров и минимальная ширина — задаются один раз при инициализации
        # Разрешаем горизонтальное сжатие/растяжение
        self.window.search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        try:
            min_search_w = int(app_config.ui.get_top_panel_search_min_width())
        except (TypeError, ValueError):
            min_search_w = 140
            logger.warning(
                "SearchWidget: invalid top_panel_search_min_width in config; using 140"
            )
        try:
            self.window.search.setMinimumWidth(min_search_w)
        except Exception:
            logger.debug("SearchWidget: failed to set minimum width", exc_info=True)
        self.window.search.setObjectName("mainSearch")

        # Размер шрифта поля поиска берётся из глобального шрифта приложения (без локальной установки)
        # Безопасное подключение обработчика поиска: on_search может отсутствовать
        handler = getattr(self.window, "on_search", None)
        if callable(handler):
            try:
                self.window.search.textChanged.connect(handler)
            except (TypeError, RuntimeError):
                logger.warning(
                    "SearchWidget: failed to connect on_search handler", exc_info=True
                )
        else:
            logger.warning(
                "SearchWidget: window.on_search handler not found; textChanged not connected"
            )
        # Добавляем БЕЗ stretch на этапе сборки (растягивание задаст TopBarLayoutManager после финального adjust)
        top_bar.addWidget(self.window.search)
        try:
            dur = (time.perf_counter() - t_start) * 1000.0
            logger.info("TopPanelMetrics: setup_search_widget: %.1f ms", dur)
        except Exception:
            pass

    def _normalize_top_bar_stretches(self, top_bar: QHBoxLayout) -> None:
        """Делает stretch=0 для всех элементов, кроме поля поиска (stretch=1)."""
        try:
            count = top_bar.count()
            search_widget = getattr(self.window, "search", None)
            search_index = -1
            for i in range(count):
                it = top_bar.itemAt(i)
                w = it.widget()
                if w is search_widget:
                    search_index = i
                # обнулим всех на всякий случай
                try:
                    top_bar.setStretch(i, 0)
                except Exception:
                    logger.debug(
                        "TopPanel: failed to setStretch(0) at index %s",
                        i,
                        exc_info=True,
                    )
            if search_index >= 0:
                try:
                    top_bar.setStretch(search_index, 1)
                except Exception:
                    logger.debug(
                        "TopPanel: failed to setStretch(1) for search at index %s",
                        search_index,
                        exc_info=True,
                    )
        except Exception:
            # не критично
            logger.debug("TopPanel: _normalize_top_bar_stretches failed", exc_info=True)

    def setup_main_content(self) -> None:
        """Настройка основного содержимого."""
        # Горизонтальный разделитель
        container_parent = (
            getattr(self.main_layout, "parentWidget", lambda: None)()
            or self.window.centralWidget()
        )
        h_line_top = QWidget(container_parent)
        h_line_top.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_top)

        mid = QHBoxLayout()
        mid.setContentsMargins(*app_config.ui.get_layout_margins("mid"))

        # Левая панель
        self.setup_left_panel(mid)

        # Правая панель с плитками и таблицей
        self.setup_right_panel(mid)

        self.main_layout.addLayout(mid)

        # Разделитель после основного содержимого
        h_line_2 = QWidget(container_parent)
        h_line_2.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_2)

    def setup_left_panel(self, mid: QHBoxLayout) -> None:
        """Настройка левой панели."""
        left_panel = QWidget()
        self.window.left_panel = left_panel
        left_panel.setObjectName("LeftPanel")
        left_panel.setAutoFillBackground(True)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(*app_config.ui.get_layout_margins("left"))
        # Убираем зазор между деревом и панелью сфер
        left_layout.setSpacing(0)

        # Дерево структуры: используем QTreeView + QAbstractItemModel
        self.window.tree = StructureTreeView()
        # Пустая модель, будет заполняться контроллерами позже
        self.window.tree_model = StructureTreeModel(self.window.tree)
        self.window.tree.setModel(self.window.tree_model)

        # Размер шрифта для дерева устанавливается централизованно через MainWindow.apply_font_size_to_content()
        left_layout.addWidget(self.window.tree)

        # Панель сфер
        self.setup_spheres_bar(left_layout)

    def setup_spheres_bar(self, left_layout: QVBoxLayout) -> None:
        """Настройка панели сфер."""
        self.window.spheres_bar = QWidget()
        self.window.spheres_bar.setObjectName("spheres_bar")
        # Фиксированная высота берется из конфигурации (spheres_bar_height)
        self.window.spheres_bar.setFixedHeight(app_config.ui.get_spheres_bar_height())

        s_layout = QHBoxLayout(self.window.spheres_bar)
        # Отступы панели сфер: поддержка левого/правого через ui.spheres_bar_margin_left/right
        s_layout.setContentsMargins(*app_config.ui.get_spheres_bar_margins())
        # Расстояние между элементами панели сфер
        s_layout.setSpacing(app_config.ui.get_spheres_bar_spacing())
        self.window.sphere_group = QButtonGroup(self.window)

        left_layout.addWidget(self.window.spheres_bar)

    def setup_right_panel(self, mid: QHBoxLayout) -> None:
        """Настройка правой панели."""
        from .right_panel_setup import RightPanelBuilder

        RightPanelBuilder(self).build(mid)

    def _setup_auto_hide_tree_filter(self, splitter_sizes: list[int]) -> None:
        """Инициализирует и запускает фильтр авто‑скрытия дерева для узких окон."""
        try:
            try:
                min_w = int(app_config.ui.get_window_min_width())
            except (TypeError, ValueError):
                min_w = 280
                logger.warning(
                    "RightPanel: invalid window_min_width in config; using 280"
                )
            self.window._auto_hide_tree_filter = _AutoHideTreeFilter(
                self.window, threshold_width=min_w, default_sizes=splitter_sizes
            )
            self.window.installEventFilter(self.window._auto_hide_tree_filter)
            # Применим после показа окна, чтобы корректно получить ширину и не уйти в ложное сужение
            try:
                if hasattr(self.window, "shown"):
                    # type: ignore[attr-defined]
                    self.window.shown.connect(self.window._auto_hide_tree_filter._apply)
                else:
                    QTimer.singleShot(0, self.window._auto_hide_tree_filter._apply)
            except Exception:
                logger.exception(
                    "RightPanel: failed to schedule AutoHideTree initial apply"
                )
        except (RuntimeError, TypeError, AttributeError):
            # Не блокируем UI, если что-то пойдёт не так
            logger.exception("RightPanel: failed to initialize AutoHideTree filter")

    def setup_bottom_panel(self) -> None:
        """Настройка нижней панели."""
        from .bottom_panel_setup import BottomPanelBuilder

        BottomPanelBuilder(self).build()

    def setup_status_bar(self) -> None:
        """Настройка статус-бара."""
        init_status_bar(self.window)

    def setup_window_properties(self) -> None:
        """Настройка базовых свойств окна."""
        self.window.setWindowTitle(app_config.ui.get_main_window_title())
        self.window.resize(*app_config.ui.get_main_window_size())
        # Применяем минимальные размеры окна из конфига, чтобы окно могло сжиматься
        try:
            min_w = int(app_config.ui.get_window_min_width())
            min_h = int(app_config.ui.get_window_min_height())
            self.window.setMinimumSize(min_w, min_h)
        except (TypeError, ValueError):
            # В случае некорректных значений не блокируем инициализацию
            logger.warning(
                "WindowProps: failed to set minimum size from config", exc_info=True
            )

        # Настройка иконки
        # Путь к логотипу приложения может отличаться в dev и в сборке (PyInstaller)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            # 1) Реальное расположение в исходниках: app/views/resources/logo/logo.png
            os.path.normpath(
                os.path.join(base_dir, "..", "resources", "logo", "logo.png")
            ),
            # 2) На случай, если структура изменится и ресурс окажется рядом
            os.path.normpath(os.path.join(base_dir, "resources", "logo", "logo.png")),
        ]
        # 3) Варианты путей в упакованной версии
        if hasattr(sys, "_MEIPASS"):
            candidates.extend(
                [
                    os.path.join(
                        sys._MEIPASS, "app", "views", "resources", "logo", "logo.png"
                    ),
                    os.path.join(sys._MEIPASS, "resources", "logo", "logo.png"),
                ]
            )

        logo_path = next((p for p in candidates if os.path.exists(p)), None)
        if logo_path:
            self.window.setWindowIcon(create_icon_from_path(logo_path))
        else:
            logger.warning("Logo icon not found in expected locations: %s", candidates)
