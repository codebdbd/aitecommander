from __future__ import annotations

import logging
from typing import List, Optional, Tuple
from weakref import WeakSet

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QTimer,
)
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLayout,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from app.config_data import app_config

try:
    from sip import isdeleted as _sip_isdeleted
except ImportError:  # pragma: no cover

    def _sip_isdeleted(_obj) -> bool:
        return False


logger = logging.getLogger(__name__)


class TopBarLayoutManager(QObject):
    """Управляет иерархическим схлопыванием верхней панели при изменении размера.

    Порядок при сжатии:
      1) Поиск удерживает минимальную ширину (из конфига).
      2) Скрывать Recent по одной кнопке.
      3) Скрывать Favorites по одной кнопке.
      4) Скрывать QuickAdd по одной кнопке.
    Минимальных квот на «оставить 1 кнопку» нет — любая панель может схлопнуться до 0.
    При расширении — в обратном порядке восстанавливаем кнопки до максимумов.
    """

    # Константы по умолчанию
    DEFAULT_THROTTLE_MS = 32
    DEFAULT_LOG_INFO = False
    DEFAULT_MIN_SEARCH_WIDTH = 148
    DEFAULT_MAX_RECENT = 10
    DEFAULT_MAX_FAV = 10
    DEFAULT_MAX_QUICK = 6
    DEFAULT_MIN_RECENT = 0
    DEFAULT_MIN_FAV = 0
    DEFAULT_MIN_QUICK = 0
    DEFAULT_NARROW_THRESHOLD = 380
    DEFAULT_BUTTON_SIZE = 32
    DEFAULT_SPACER_SIZE = 4

    def __init__(self, window):
        super().__init__(window)
        self.window: QObject = window
        self._last_applied: Optional[Tuple[int, int, int, int]] = (
            None  # (width, recent, fav, quick)
        )
        self._warmup_adjusts_remaining: int = 2
        self._container_widget: Optional[QWidget] = None
        self._watched_panels: WeakSet[QObject] = WeakSet()

        # Настройки из конфига с fallback
        self._throttle_interval_ms: int = self._get_cfg_int(
            "ui.topbar.throttle_ms", self.DEFAULT_THROTTLE_MS
        )
        self._log_info: bool = self._get_cfg_bool(
            "ui.topbar.log_info", self.DEFAULT_LOG_INFO
        )
        # Минимальная ширина поиска: синхронизируем с UI-строителем через app_config.ui.get_top_panel_search_min_width()
        # Фолбэк — DEFAULT_MIN_SEARCH_WIDTH, чтобы старт был стабильным даже без конфига
        try:
            self._min_search_width: int = int(
                app_config.ui.get_top_panel_search_min_width()
            )
        except Exception:
            self._min_search_width = int(self.DEFAULT_MIN_SEARCH_WIDTH)
        self._max_recent: int = self.DEFAULT_MAX_RECENT
        self._max_fav: int = self.DEFAULT_MAX_FAV
        self._max_quick: int = self.DEFAULT_MAX_QUICK
        # Минимальные квоты: читаем из конфигурации topbar.min_visible с безопасными fallback'ами
        try:
            mv = app_config.get("topbar.min_visible", {}) or {}
        except Exception:
            mv = {}
        def _to_nonneg_int(v, default=0):
            try:
                iv = int(v)
                return max(0, iv)
            except Exception:
                return int(default)
        self._min_recent: int = _to_nonneg_int(mv.get("recent", 0))
        self._min_fav: int = _to_nonneg_int(mv.get("fav", 0))
        self._min_quick: int = _to_nonneg_int(mv.get("quick", 0))
        # Отладочная информация для проверки чтения конфигурации
        logger.debug(f"TopBarLayoutManager: min_visible config: recent={self._min_recent}, fav={self._min_fav}, quick={self._min_quick}")
        # Узкий режим: фиксированный порог (значение задаётся DEFAULT_NARROW_THRESHOLD) и не переопределяется конфигом
        self._narrow_threshold: int = self.DEFAULT_NARROW_THRESHOLD
        self._button_size: int = self._get_cfg_int(
            "ui.top_panel_button_size", self.DEFAULT_BUTTON_SIZE
        )
        # No extra safety pads: use exact computed widths to avoid clipping

        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._run_adjust)

        # Animation settings/state
        self._animating: bool = False
        self._anim_duration_ms: int = 140
        # PyQt6 requires using the enum under QEasingCurve.Type
        self._anim_curve = QEasingCurve.Type.OutCubic
        self._active_groups: list[QParallelAnimationGroup] = []

        # Подключение к контейнерам
        self._install_event_filters()

        # Инициализационный пересчет после показа окна
        if hasattr(self.window, "shown"):
            self.window.shown.connect(self.adjust)

        # Панели, которые считаются фиксированными и не участвуют в расчёте отображаемых кнопок
        self._fixed_panels: set[str] = set()

    def _install_event_filters(self) -> None:
        """Устанавливает фильтры событий на релевантные виджеты."""
        for attr_name in [
            "top_bar_host",
            "content_container",
            "quick_add_widget",
            "fav_widget",
            "recent_links_widget",
        ]:
            widget = self._safe_get(self.window, attr_name)
            if isinstance(widget, QWidget) and widget not in self._watched_panels:
                widget.installEventFilter(self)
                self._watched_panels.add(widget)
        # Окно
        if isinstance(self.window, QWidget) and not _sip_isdeleted(self.window):
            self.window.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.LayoutRequest,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        ):
            # Используем настраиваемый интервал троттлинга, чтобы уменьшить дребезг пересчётов
            self._throttle_timer.start(self._throttle_interval_ms)
        return super().eventFilter(obj, event)

    def _run_adjust(self) -> None:
        self.adjust()

    # -------------------- Публичные методы старта --------------------
    def prepare_initial_layout(self) -> None:
        """Однократно выполняет подготовку: показывает контейнер, сбрасывает warmup и стартует adjust."""
        container = self._get_container_widget()
        if container and hasattr(container, "setVisible"):
            try:
                if not container.isVisible():
                    container.setVisible(True)
            except Exception:
                logger.debug("TopBarLM.prepare_initial_layout: unable to show container", exc_info=True)
        # Сбрасываем прогрев в один проход
        self._warmup_adjusts_remaining = 0
        # Выполняем начальный пересчет один раз
        self.adjust()

    def mark_panel_fixed(self, attr_name: str) -> None:
        """Позволяет пометить панель как фиксированную (не скрываемые элементы)."""
        if attr_name:
            self._fixed_panels.add(attr_name)

    # -------------------- Основной алгоритм --------------------
    def _safe_get(self, obj: Optional[object], name: str) -> Optional[object]:
        if obj is None or (isinstance(obj, QObject) and _sip_isdeleted(obj)):
            return None
        try:
            return getattr(obj, name, None)
        except RuntimeError:
            return None

    def _iter_buttons(
        self, panel_widget: Optional[QWidget], name: str
    ) -> List[QToolButton]:
        if not panel_widget:
            return []
        bg = self._safe_get(panel_widget, "bg_frame")
        lay = (
            bg.layout()
            if isinstance(bg, QWidget) and callable(getattr(bg, "layout", None))
            else None
        )
        ordered: List[QToolButton] = []
        if lay:
            for i in range(lay.count()):
                w = lay.itemAt(i).widget()
                if isinstance(w, QToolButton) and w.objectName() == name:
                    ordered.append(w)
        # Дополнить findChildren
        for b in panel_widget.findChildren(QToolButton, name):
            if b not in ordered:
                ordered.append(b)
        return ordered

    def _set_visible_count(
        self, panel_widget: Optional[QWidget], btn_object_name: str, count: int
    ) -> int:
        buttons = self._iter_buttons(panel_widget, btn_object_name)
        if not buttons:
            if panel_widget:
                # Держим панель видимой, скрываем только кнопки
                try:
                    panel_widget.setVisible(True)
                except Exception:
                    pass
                try:
                    panel_widget.updateGeometry()
                except Exception:
                    pass
            return 0
        count = max(0, min(count, len(buttons)))
        for i, btn in enumerate(buttons):
            btn.setVisible(i < count)
        if panel_widget:
            # Панель остаётся видимой, ширина ограничивается отдельно в _apply_panel_width_bounds
            try:
                panel_widget.setVisible(True)
            except Exception:
                pass
            try:
                panel_widget.updateGeometry()
            except Exception:
                pass
        return count

    def _current_visible_count(self, btns: List[QToolButton]) -> int:
        cnt = 0
        for i, b in enumerate(btns):
            if b.isVisible():
                cnt = i + 1
        return cnt

    def _get_top_bar(self) -> Optional[QLayout]:
        for attr in ["top_bar_host", "content_container"]:
            host = self._safe_get(self.window, attr)
            if isinstance(host, QWidget):
                lay = host.layout()
                if lay:
                    return lay
        return None

    def _get_container_widget(self) -> Optional[QWidget]:
        if self._container_widget and not _sip_isdeleted(self._container_widget):
            return self._container_widget
        self._container_widget = self._safe_get(
            self.window, "top_bar_host"
        ) or self._safe_get(self.window, "content_container")
        return self._container_widget

    def adjust(self) -> None:
        container = self._get_container_widget()
        if not container:
            return
        width_hint = container.width()
        if width_hint <= 0 or not container.isVisible():
            search = self._safe_get(self.window, "search")
            if isinstance(search, QLineEdit):
                try:
                    search.setMaximumWidth(self._min_search_width)
                    search.setMinimumWidth(self._min_search_width)
                except Exception:
                    pass
            return

        width = container.width()
        # Для активации узкого режима учитываем фактическую ширину окна, если доступна
        try:
            win_w = int(getattr(self.window, "width", lambda: width)())
            effective_w = min(width, win_w) if win_w > 0 else width
        except (AttributeError, RuntimeError, TypeError, ValueError):
            effective_w = width
        logger.debug(f"TopBarLayoutManager.adjust(): width={width}, effective_w={effective_w}, threshold={self._narrow_threshold}")
        top_bar = self._get_top_bar()
        if not top_bar:
            return

        # Получить панели и поиск
        quick = self._safe_get(self.window, "quick_add_widget")
        fav = self._safe_get(self.window, "fav_widget")
        recent = self._safe_get(self.window, "recent_links_widget")
        search: Optional[QLineEdit] = self._safe_get(self.window, "search")

        # Фиксированные панели (если помечены) не подлежат регулировкам
        panel_map = {
            "recent_links_widget": recent,
            "fav_widget": fav,
            "quick_add_widget": quick,
        }
        fixed_panels = {
            name: panel
            for name, panel in panel_map.items()
            if name in self._fixed_panels
        }
        if fixed_panels:
            for panel in fixed_panels.values():
                if panel and hasattr(panel, "setMaximumWidth"):
                    try:
                        panel.setMaximumWidth(panel.sizeHint().width())
                    except Exception:
                        pass

        # Фильтры событий устанавливаются один раз в __init__; лишние переустановки не требуются

        logger.debug(f"TopBarLayoutManager.adjust(): checking narrow mode: {effective_w} <= {self._narrow_threshold} = {effective_w <= self._narrow_threshold}")
        if effective_w <= self._narrow_threshold:
            logger.debug(
                "TopBar narrow mode: width=%s <= threshold=%s",
                width,
                self._narrow_threshold,
            )
            # В узком режиме соблюдаем минимальные ограничения
            narrow_recent = max(0, self._min_recent)
            narrow_fav = max(0, self._min_fav)
            narrow_quick = max(0, self._min_quick)
            logger.debug(f"TopBar narrow mode: applying min_visible: recent={narrow_recent}, fav={narrow_fav}, quick={narrow_quick}")
            self._apply_counts(width, narrow_recent, narrow_fav, narrow_quick)
            self._update_separators_visibility(
                top_bar, narrow_recent > 0, narrow_fav > 0, narrow_quick > 0, bool(search)
            )
            # Если все минимальные значения равны 0, то применяем полный узкий режим
            if narrow_recent == 0 and narrow_fav == 0 and narrow_quick == 0:
                self._apply_narrow_mode(top_bar, search)
            return

        # Выходим из узкого режима: восстановить поведение поиска (clear-кнопка и встроенные действия)
        # Важно делать это до дальнейших пересчётов, чтобы repeated adjust() не оставлял поиск в выключенном состоянии
        self._restore_search_actions(search)

        # Кэшировать списки кнопок
        quick_btns = self._iter_buttons(quick, "quickButton")
        fav_btns = self._iter_buttons(fav, "favoriteButton")
        recent_btns = self._iter_buttons(recent, "recentButton")

        # Рассчитать видимые количества
        cnt_recent, cnt_fav, cnt_quick = self._compute_visible_counts(
            width,
            top_bar,
            search,
            recent,
            fav,
            quick,
            recent_btns,
            fav_btns,
            quick_btns,
        )

        # Если расчёт показал, что места нет даже для одной кнопки любой панели (zero-count)
        if cnt_recent == 0 and cnt_fav == 0 and cnt_quick == 0:
            # В узком режиме сохраняем прежнее поведение: оставляем только поиск, без отступов
            if effective_w <= self._narrow_threshold:
                try:
                    self._apply_counts(width, 0, 0, 0)
                    self._update_separators_visibility(
                        top_bar, False, False, False, bool(search)
                    )
                    self._apply_narrow_mode(top_bar, search)
                except Exception:
                    logger.debug(
                        "TopBarLayoutManager: zero-count narrow-mode handling failed",
                        exc_info=True,
                    )
                return
            # НЕ узкий режим: применяем нулевые квоты и корректно ограничиваем поиск
            try:
                # 1) Скрыть панели
                self._apply_counts(width, 0, 0, 0)
                # 2) Обновить разделители
                self._update_separators_visibility(
                    top_bar, False, False, False, bool(search)
                )
                # 3) Растяжение только для поиска
                self._enforce_stretches(top_bar, search)
                # 4) Ограничить ширину поиска: на первом проходе НЕ расширяем, держим на минимуме
                if isinstance(search, QLineEdit):
                    try:
                        min_search_w = int(self._min_search_width)
                        cur_min = int(search.minimumWidth())
                        if cur_min > 0:
                            min_search_w = max(min_search_w, cur_min)
                    except Exception:
                        min_search_w = int(self._min_search_width)
                    # Жёстко фиксируем на минимуме, без расчёта remaining
                    max_search_w = min_search_w
                    if search.maximumWidth() != max_search_w:
                        search.setMaximumWidth(max_search_w)
                    if search.minimumWidth() != min_search_w:
                        search.setMinimumWidth(min_search_w)
            except Exception:
                logger.debug(
                    "TopBarLayoutManager: zero-count regular-mode handling failed",
                    exc_info=True,
                )
            return

        state = (width, cnt_recent, cnt_fav, cnt_quick)
        if self._last_applied == state:
            return

        if self._warmup_adjusts_remaining > 0:
            self._apply_counts(width, 0, 0, 0)
            self._warmup_adjusts_remaining -= 1
            self._throttle_timer.start(0)
            return

        # Hysteresis: avoid frequent toggles near boundary
        prev_counts = self._last_applied
        if prev_counts is not None:
            _, pr, pf, pq = prev_counts
            total_new = self._total_width_for(
                top_bar, search, recent, fav, quick,
                recent_btns, fav_btns, quick_btns,
                cnt_recent, cnt_fav, cnt_quick,
            )
            band = max(8, int(self._button_size // 2))
            if abs(width - total_new) < band:
                cnt_recent, cnt_fav, cnt_quick = pr, pf, pq

        # Применить пакетно под suspend_updates, чтобы исключить дребезжание лейаута
        recent_visible = fav_visible = quick_visible = 0
        try:
            from app.utils.ui.updates import suspend_updates
        except Exception:
            suspend_updates = None

        def _apply_one(panel, btns, btn_name, target):
            # Унифицированный порядок: сначала меняем видимость, затем подгоняем ширину панели.
            # Это снижает визуальные артефакты как при сжатии, так и при расширении.
            vis = self._set_visible_count(panel, btn_name, target)
            self._apply_panel_width_bounds(panel, btns, vis)
            return vis

        def _batch_apply():
            nonlocal recent_visible, fav_visible, quick_visible
            # Diagnostic: log snapshot before applying, to catch pre-apply overflow conditions
            try:
                self._log_layout_snapshot(
                    width,
                    top_bar,
                    search,
                    recent,
                    fav,
                    quick,
                    recent_btns,
                    fav_btns,
                    quick_btns,
                    cnt_recent,
                    cnt_fav,
                    cnt_quick,
                )
            except Exception:
                logger.debug("TopBarLM: pre-apply snapshot failed", exc_info=True)
            recent_visible = _apply_one(recent, recent_btns, "recentButton", cnt_recent)
            fav_visible = _apply_one(fav, fav_btns, "favoriteButton", cnt_fav)
            quick_visible = _apply_one(quick, quick_btns, "quickButton", cnt_quick)

        if suspend_updates is not None and isinstance(self.window, QWidget):
            try:
                with suspend_updates(self.window):
                    _batch_apply()
            except Exception:
                _batch_apply()
        else:
            _batch_apply()

        self._last_applied = (width, recent_visible, fav_visible, quick_visible)
        if self._log_info:
            logger.info(
                "[TopBar] visible: recent=%s, fav=%s, quick=%s; min_search=%s",
                recent_visible,
                fav_visible,
                quick_visible,
                self._min_search_width,
            )
        else:
            logger.debug(
                "[TopBar] visible: recent=%s, fav=%s, quick=%s; min_search=%s",
                recent_visible,
                fav_visible,
                quick_visible,
                self._min_search_width,
            )

        # В обычном режиме восстанавливаем отступы top_bar из конфига (лево/право)
        try:
            side = int(app_config.ui.get_top_bar_widgets_side_spacing())
        except Exception:
            side = 8
        self._set_top_bar_margins(top_bar, side, 0, side, 0)
        # Гарантируем стабильные stretch-факторы в обычном режиме
        self._enforce_stretches(top_bar, search)
        self._update_separators_visibility(
            top_bar,
            recent_visible > 0,
            fav_visible > 0,
            quick_visible > 0,
            search is not None,
        )

        # Жёстко ограничим максимальную ширину поля поиска оставшимся пространством,
        # чтобы исключить визуальное «переполнение» и наезд на соседние панели.
        try:
            if isinstance(search, QLineEdit):
                # Считаем суммарную ширину уже применённых панелей + разделителей/отступов
                occupied = 0
                count = top_bar.count()
                for i in range(count):
                    it = top_bar.itemAt(i)
                    w = it.widget()
                    if w is None:
                        sp = it.spacerItem()
                        if sp:
                            occupied += max(0, sp.sizeHint().width())
                        continue
                    if w is search:
                        continue
                    if w.isVisible():
                        try:
                            occupied += int(w.width())
                        except Exception:
                            occupied += w.sizeHint().width()
                spacing = top_bar.spacing() or 0
                # число видимых элементов (без поиска) для корректировки spacing
                visible_widgets = [
                    top_bar.itemAt(i).widget()
                    for i in range(count)
                    if top_bar.itemAt(i).widget() is not None and top_bar.itemAt(i).widget() is not search and top_bar.itemAt(i).widget().isVisible()
                ]
                occupied += spacing * max(0, len(visible_widgets) - 1)
                m = top_bar.contentsMargins()
                occupied += m.left() + m.right()
                host = self._get_container_widget()
                container_w = host.width() if isinstance(host, QWidget) else 0
                remaining = max(0, container_w - occupied)

                # Синхронизированная минимальная ширина для поиска: учитываем настройку из app_config и текущее minimumWidth()
                min_search_w = int(self._min_search_width)
                try:
                    cur_min = int(search.minimumWidth())
                    if cur_min > 0:
                        min_search_w = max(min_search_w, cur_min)
                except Exception:
                    pass

                # Не даём меньше минимальной ширины поиска
                max_search_w = max(min_search_w, remaining)
                # Применяем ограничения к поиску
                if search.maximumWidth() != max_search_w:
                    search.setMaximumWidth(max_search_w)
                if search.minimumWidth() != min_search_w:
                    search.setMinimumWidth(min_search_w)
        except Exception:
            logger.debug("TopBarLM: failed to clamp search width to remaining space", exc_info=True)

    def _apply_with_animation(
        self, panel: Optional[QWidget], btns: list[QToolButton], target_visible: int
    ) -> int:
        if not panel:
            return 0
        target_visible = max(0, min(target_visible, len(btns)))

        # Build animation group
        group = QParallelAnimationGroup(panel)
        any_anim = False

        # 1) Width animation (maximumWidth)
        panel.setMinimumWidth(0)
        new_w = self._panel_width(panel, btns, target_visible) if target_visible > 0 else 0
        old_w = int(panel.maximumWidth())
        if old_w != new_w:
            wa = QPropertyAnimation(panel, b"maximumWidth")
            wa.setDuration(self._anim_duration_ms)
            wa.setEasingCurve(self._anim_curve)
            wa.setStartValue(old_w)
            wa.setEndValue(new_w)
            group.addAnimation(wa)
            any_anim = True
        else:
            panel.setMaximumWidth(new_w)

        # 2) Buttons opacity animations
        for i, btn in enumerate(btns):
            need_visible = i < target_visible
            cur_visible = btn.isVisible()
            eff = btn.graphicsEffect()
            if not isinstance(eff, QGraphicsOpacityEffect):
                eff = QGraphicsOpacityEffect(btn)
                btn.setGraphicsEffect(eff)
            if need_visible and not cur_visible:
                btn.setVisible(True)
                eff.setOpacity(0.0)
                oa = QPropertyAnimation(eff, b"opacity")
                oa.setDuration(self._anim_duration_ms)
                oa.setEasingCurve(self._anim_curve)
                oa.setStartValue(0.0)
                oa.setEndValue(1.0)
                group.addAnimation(oa)
                any_anim = True
            elif (not need_visible) and cur_visible:
                eff.setOpacity(1.0)
                oa = QPropertyAnimation(eff, b"opacity")
                oa.setDuration(self._anim_duration_ms)
                oa.setEasingCurve(self._anim_curve)
                oa.setStartValue(1.0)
                oa.setEndValue(0.0)
                # Hide after fade-out
                def _hide_button(b=btn):
                    try:
                        b.setVisible(False)
                    except Exception:
                        pass
                oa.finished.connect(_hide_button)
                group.addAnimation(oa)
                any_anim = True

        # Run or apply instantly
        if any_anim:
            self._animating = True
            self._active_groups.append(group)
            def _on_done():
                try:
                    host = self._get_container_widget()
                    if isinstance(host, QWidget):
                        host.updateGeometry()
                        host.update()
                except Exception:
                    pass
                if group in self._active_groups:
                    self._active_groups.remove(group)
                if not self._active_groups:
                    self._animating = False
                    # Trigger a final adjust to settle last state
                    self._throttle_timer.start(0)
            group.finished.connect(_on_done)
            group.start()
        else:
            # Ensure panel width is applied when no animation
            panel.setMaximumWidth(new_w)

        return target_visible

    def _zero_all_spacers(self, top_bar: QLayout) -> None:
        """Устанавливает ширину всех spacerItem в 0 для полного освобождения места (узкий режим)."""
        try:
            count = top_bar.count()
            for i in range(count):
                it = top_bar.itemAt(i)
                sp = it.spacerItem()
                if sp is not None:
                    sp.changeSize(0, 0)
        except Exception:
            # Диагностические ошибки не критичны
            logger.debug("TopBarLM: _zero_all_spacers failed", exc_info=True)

    def _apply_panel_width_bounds(
        self, panel: Optional[QWidget], btns: List[QToolButton], visible: int
    ) -> None:
        if not panel:
            return
        panel.setMinimumWidth(0)
        max_w = self._panel_width(panel, btns, visible) if visible > 0 else 0
        panel.setMaximumWidth(max_w)

    def _set_top_bar_margins(
        self, top_bar: QLayout, left: int, top: int, right: int, bottom: int
    ) -> None:
        """Безопасно выставляет отступы для top_bar (QLayout)."""
        try:
            m = top_bar.contentsMargins()
            if (
                m.left() == left
                and m.top() == top
                and m.right() == right
                and m.bottom() == bottom
            ):
                return
        except Exception:
            logger.debug("TopBarLM: failed to read contentsMargins()", exc_info=True)
        try:
            top_bar.setContentsMargins(left, top, right, bottom)
        except Exception:
            logger.debug("TopBarLM: setContentsMargins failed", exc_info=True)

    def _enforce_stretches(self, top_bar: QLayout, search: Optional[QLineEdit]) -> None:
        """Сбрасывает stretch=0 для всех элементов top_bar и ставит stretch=1 только для поиска."""
        try:
            count = top_bar.count()
            search_index = -1
            for i in range(count):
                it = top_bar.itemAt(i)
                w = it.widget()
                if w is not None and isinstance(search, QLineEdit) and w is search:
                    search_index = i
                try:
                    top_bar.setStretch(i, 0)
                except Exception:
                    logger.debug(
                        "TopBarLM: setStretch(0) failed at index %s", i, exc_info=True
                    )
            if search_index >= 0:
                try:
                    top_bar.setStretch(search_index, 1)
                except Exception:
                    logger.debug(
                        "TopBarLM: setStretch(1) for search failed at index %s",
                        search_index,
                        exc_info=True,
                    )
        except Exception:
            logger.debug("TopBarLM: _enforce_stretches failed", exc_info=True)

    def _apply_narrow_mode(self, top_bar: QLayout, search: Optional[QLineEdit]) -> None:
        """Применяет узкий режим: оставляет только поиск, обнуляет отступы и спейсеры,
        растягивает поиск на всю ширину и обновляет контейнер.
        Поведение идентично ранее дублированным блокам в adjust().
        """
        try:
            count = top_bar.count()
            # Скрыть любые виджеты кроме поиска
            for i in range(count):
                it = top_bar.itemAt(i)
                w = it.widget()
                if w is None:
                    continue
                if isinstance(search, QLineEdit) and w is search:
                    continue
                try:
                    w.setVisible(False)
                except Exception:
                    logger.debug(
                        "TopBarLM: failed to hide non-search widget in narrow mode",
                        exc_info=True,
                    )
            # Обнулить все spacerItem
            try:
                for i in range(count):
                    sp = top_bar.itemAt(i).spacerItem()
                    if sp is not None:
                        sp.changeSize(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            except Exception:
                logger.debug("TopBarLM: failed to zero spacers in narrow mode", exc_info=True)
            # Отключить встроенные действия у поиска
            if isinstance(search, QLineEdit):
                try:
                    search.setClearButtonEnabled(False)
                except Exception:
                    logger.debug(
                        "TopBarLM: failed to disable clear button on search (narrow mode)",
                        exc_info=True,
                    )
                try:
                    for act in search.actions():
                        try:
                            act.setVisible(False)
                        except Exception:
                            logger.debug(
                                "TopBarLM: failed to hide search action in narrow mode",
                                exc_info=True,
                            )
                except Exception:
                    logger.debug(
                        "TopBarLM: failed to iterate search actions in narrow mode",
                        exc_info=True,
                    )
            # Нулевые отступы и растяжение поиска
            try:
                self._set_top_bar_margins(top_bar, 0, 0, 0, 0)
            except Exception:
                logger.debug(
                    "TopBarLM: failed to set zero margins on top_bar (narrow mode)",
                    exc_info=True,
                )
            try:
                if isinstance(search, QLineEdit):
                    search.setMinimumWidth(0)
                    search.setMaximumWidth(16777215)
                    search.setSizePolicy(
                        QSizePolicy.Policy.Expanding, search.sizePolicy().verticalPolicy()
                    )
            except Exception:
                logger.debug(
                    "TopBarLM: failed to expand search to full width (narrow mode)",
                    exc_info=True,
                )
            # Пересчитать лейаут и контейнер
            try:
                self._enforce_stretches(top_bar, search)
                top_bar.invalidate()
                host = self._get_container_widget()
                if isinstance(host, QWidget):
                    host.updateGeometry()
                    host.update()
            except Exception:
                logger.debug(
                    "TopBarLM: failed to enforce stretches/update host in narrow mode",
                    exc_info=True,
                )
        except Exception:
            logger.debug(
                "TopBarLayoutManager: narrow-mode application failed",
                exc_info=True,
            )

    def _restore_search_actions(self, search: Optional[QLineEdit]) -> None:
        """Восстанавливает clear-кнопку и видимость встроенных действий поиска после выхода из узкого режима.
        Должно вызываться при любом не-узком состоянии (включая первичный показ окна).
        """
        if not isinstance(search, QLineEdit):
            return
        try:
            # Вернуть clear-кнопку
            if hasattr(search, "setClearButtonEnabled"):
                search.setClearButtonEnabled(True)
        except Exception:
            logger.debug(
                "TopBarLM: failed to enable clear button on search (restore)",
                exc_info=True,
            )
        # Вернуть видимость встроенных действий
        try:
            for act in search.actions():
                try:
                    act.setVisible(True)
                except Exception:
                    logger.debug(
                        "TopBarLM: failed to show search action on restore",
                        exc_info=True,
                    )
        except Exception:
            logger.debug(
                "TopBarLM: failed to iterate search actions on restore",
                exc_info=True,
            )

    def _compute_visible_counts(
        self,
        width: int,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        recent: Optional[QWidget],
        fav: Optional[QWidget],
        quick: Optional[QWidget],
        recent_btns: List[QToolButton],
        fav_btns: List[QToolButton],
        quick_btns: List[QToolButton],
    ) -> Tuple[int, int, int]:
        max_recent = min(self._max_recent, len(recent_btns))
        max_fav = min(self._max_fav, len(fav_btns))
        max_quick = min(self._max_quick, len(quick_btns))

        # Минимальные квоты из конфигурации (задаются в __init__) с ограничением доступным количеством
        min_recent = max(0, int(self._min_recent))
        min_fav = max(0, int(self._min_fav))
        min_quick = max(0, int(self._min_quick))

        # Не требуем больше, чем реально доступно
        min_recent = min(min_recent, max_recent)
        min_fav = min(min_fav, max_fav)
        min_quick = min(min_quick, max_quick)

        cnt_recent, cnt_fav, cnt_quick = max_recent, max_fav, max_quick
        # cnt_* уже не меньше min_* и не больше max_* благодаря клампам выше
        logger.debug(f"TopBarLayoutManager: _compute_visible_counts start: recent={cnt_recent}, fav={cnt_fav}, quick={cnt_quick}")
        logger.debug(f"TopBarLayoutManager: min constraints: recent>={min_recent}, fav>={min_fav}, quick>={min_quick}")

        max_steps = (
            (cnt_recent - min_recent) + (cnt_fav - min_fav) + (cnt_quick - min_quick)
        )
        steps = 0
        while (
            self._total_width_for(
                top_bar,
                search,
                recent,
                fav,
                quick,
                recent_btns,
                fav_btns,
                quick_btns,
                cnt_recent,
                cnt_fav,
                cnt_quick,
            )
            > width
            and steps < max_steps
        ):
            steps += 1
            if cnt_recent > min_recent:
                cnt_recent -= 1
            elif cnt_fav > min_fav:
                cnt_fav -= 1
            elif cnt_quick > min_quick:
                cnt_quick -= 1
            else:
                break

        # Проверяем, не превышает ли итоговая ширина доступное место
        # НО не обнуляем всё подряд, а соблюдаем минимальные ограничения
        if (
            self._total_width_for(
                top_bar,
                search,
                recent,
                fav,
                quick,
                recent_btns,
                fav_btns,
                quick_btns,
                cnt_recent,
                cnt_fav,
                cnt_quick,
            )
            > width
        ):
            # Принудительно сжимаем до минимальных значений, но не ниже
            cnt_recent = max(min_recent, 0)
            cnt_fav = max(min_fav, 0)
            cnt_quick = max(min_quick, 0)
            logger.debug(f"TopBarLayoutManager: forced to minimum: recent={cnt_recent}, fav={cnt_fav}, quick={cnt_quick}")

        self._log_layout_snapshot(
            width,
            top_bar,
            search,
            recent,
            fav,
            quick,
            recent_btns,
            fav_btns,
            quick_btns,
            cnt_recent,
            cnt_fav,
            cnt_quick,
        )

        logger.debug(f"TopBarLayoutManager: _compute_visible_counts result: recent={cnt_recent}, fav={cnt_fav}, quick={cnt_quick}")
        return cnt_recent, cnt_fav, cnt_quick

    def _log_layout_snapshot(
        self,
        container_w: int,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        recent: Optional[QWidget],
        fav: Optional[QWidget],
        quick: Optional[QWidget],
        recent_btns: List[QToolButton],
        fav_btns: List[QToolButton],
        quick_btns: List[QToolButton],
        c_r: int,
        c_f: int,
        c_q: int,
    ) -> None:
        if not self._log_info:
            return
        try:
            total = self._total_width_for(
                top_bar,
                search,
                recent,
                fav,
                quick,
                recent_btns,
                fav_btns,
                quick_btns,
                c_r,
                c_f,
                c_q,
            )
            tb_spacing = top_bar.spacing() or 0
            tb_m = top_bar.contentsMargins()
            def _panel_line(name: str, panel: Optional[QWidget], btns: List[QToolButton], cnt: int) -> str:
                if not panel:
                    return f"{name}: none"
                try:
                    comp = self._panel_width(panel, btns, cnt)
                except Exception:
                    comp = -1
                try:
                    pw = int(panel.width())
                    pmw = int(panel.maximumWidth())
                except Exception:
                    pw = pmw = -1
                try:
                    bg = self._safe_get(panel, "bg_frame")
                    lay = bg.layout() if bg else None
                    sp = lay.spacing() if lay else 0
                    lm = lay.contentsMargins() if lay else None
                    lm_str = f"{lm.left()},{lm.right()}" if lm else "-"
                except Exception:
                    sp = 0
                    lm_str = "-"
                try:
                    pm = panel.contentsMargins()
                    pm_str = f"{pm.left()},{pm.right()}"
                except Exception:
                    pm_str = "-"
                cur = self._current_visible_count(btns)
                return (
                    f"{name}: tgt={cnt} cur={cur} comp={comp} w={pw} maxW={pmw} "
                    f"lay[sp={sp} mL,R={lm_str}] panel[mL,R={pm_str}]"
                )
            lines = [
                f"TopBarSnapshot: container_w={container_w} total={total} tb[sp={tb_spacing} mL,R={tb_m.left()},{tb_m.right()}]",
                _panel_line("recent", recent, recent_btns, c_r),
                _panel_line("fav", fav, fav_btns, c_f),
                _panel_line("quick", quick, quick_btns, c_q),
                f"search minW={self._min_search_width}",
            ]
            for ln in lines:
                logger.info(ln)
        except Exception:
            logger.debug("TopBarLM: _log_layout_snapshot failed", exc_info=True)

    def _panel_width(
        self, panel: Optional[QWidget], btns: List[QToolButton], count: int
    ) -> int:
        if not panel or not btns or count <= 0:
            return 0
        bg = self._safe_get(panel, "bg_frame")
        lay = bg.layout() if bg else None
        spacing = lay.spacing() if lay else 0
        total = 0
        for i in range(count):
            # Используем sizeHint с fallback на конфигурируемый размер кнопки
            try:
                btn_w = max(self._button_size, int(btns[i].sizeHint().width()))
            except Exception:
                btn_w = self._button_size
            if i > 0:
                total += spacing
            total += btn_w
        if lay:
            m = lay.contentsMargins()
            total += m.left() + m.right()
        pm = panel.contentsMargins()
        total += pm.left() + pm.right()
        # safety pad applied in _apply_panel_width_bounds to avoid layout rounding overlap
        return total

    def _total_width_for(
        self,
        top_bar: QLayout,
        search: Optional[QLineEdit],
        recent: Optional[QWidget],
        fav: Optional[QWidget],
        quick: Optional[QWidget],
        recent_btns: List[QToolButton],
        fav_btns: List[QToolButton],
        quick_btns: List[QToolButton],
        c_r: int,
        c_f: int,
        c_q: int,
    ) -> int:
        items: List[int] = []
        for i in range(top_bar.count()):
            it = top_bar.itemAt(i)
            w = it.widget()
            if w:
                if w is search:
                    items.append(self._min_search_width)
                elif w is recent and c_r > 0:
                    items.append(self._panel_width(recent, recent_btns, c_r))
                elif w is fav and c_f > 0:
                    items.append(self._panel_width(fav, fav_btns, c_f))
                elif w is quick and c_q > 0:
                    items.append(self._panel_width(quick, quick_btns, c_q))
                elif w.isVisible():
                    items.append(w.sizeHint().width())
            else:
                sp = it.spacerItem()
                if sp:
                    items.append(max(0, sp.sizeHint().width()))
        total = sum(items)
        spacing = top_bar.spacing() or 0
        total += spacing * max(0, len(items) - 1)
        m = top_bar.contentsMargins()
        total += m.left() + m.right()
        return total

    def _update_separators_visibility(
        self,
        top_bar: QLayout,
        recent_visible: bool,
        fav_visible: bool,
        quick_visible: bool,
        search_exists: bool,
    ) -> None:
        def logical_visible_panel(w: Optional[QWidget]) -> bool:
            if not w:
                return False
            if w is self._safe_get(self.window, "recent_links_widget"):
                return recent_visible and w.isVisible()
            if w is self._safe_get(self.window, "fav_widget"):
                return fav_visible and w.isVisible()
            if w is self._safe_get(self.window, "quick_add_widget"):
                return quick_visible and w.isVisible()
            return False

        count = top_bar.count()
        i = 0
        while i < count:
            it = top_bar.itemAt(i)
            w = it.widget()
            if self._is_vertical_separator(w):
                left_widget = None
                j = i - 1
                while j >= 0 and not left_widget:
                    prev_it = top_bar.itemAt(j)
                    if prev_it.widget():
                        left_widget = prev_it.widget()
                    j -= 1
                right_widget = None
                j = i + 1
                while j < count and not right_widget:
                    next_it = top_bar.itemAt(j)
                    if next_it.widget():
                        right_widget = next_it.widget()
                    j += 1
                show_sep = logical_visible_panel(left_widget) and (
                    logical_visible_panel(right_widget)
                    or (search_exists and isinstance(right_widget, QLineEdit))
                )
                w.setVisible(show_sep)
                # Размеры спейсеров: при видимом разделителе по 4px с обеих сторон.
                # При скрытом разделителе оставляем стандартный отступ 4px только перед полем поиска,
                # а с другой стороны схлопываем до 0, чтобы не было двойного зазора.
                left_sp = top_bar.itemAt(i - 1).spacerItem() if i - 1 >= 0 else None
                right_sp = top_bar.itemAt(i + 1).spacerItem() if i + 1 < count else None

                if show_sep:
                    if left_sp:
                        left_sp.changeSize(
                            self.DEFAULT_SPACER_SIZE,
                            0,
                            QSizePolicy.Policy.Fixed,
                            QSizePolicy.Policy.Fixed,
                        )
                    if right_sp:
                        right_sp.changeSize(
                            self.DEFAULT_SPACER_SIZE,
                            0,
                            QSizePolicy.Policy.Fixed,
                            QSizePolicy.Policy.Fixed,
                        )
                else:
                    # Если справа Search (QLineEdit) — оставляем 4px справа, слева 0px.
                    is_search_right = isinstance(right_widget, QLineEdit)
                    if left_sp:
                        left_sp.changeSize(
                            0 if is_search_right else self.DEFAULT_SPACER_SIZE,
                            0,
                            QSizePolicy.Policy.Fixed,
                            QSizePolicy.Policy.Fixed,
                        )
                    if right_sp:
                        right_sp.changeSize(
                            self.DEFAULT_SPACER_SIZE if is_search_right else 0,
                            0,
                            QSizePolicy.Policy.Fixed,
                            QSizePolicy.Policy.Fixed,
                        )
            i += 1
        top_bar.invalidate()

    def _is_vertical_separator(self, w: Optional[QWidget]) -> bool:
        if not w:
            return False
        if w.objectName() == "vSeparator":
            return True
        cls = str(w.property("class") or "")
        return cls == "vertical_separator"

    def _apply_counts(self, width: int, c_r: int, c_f: int, c_q: int) -> None:
        recent = self._safe_get(self.window, "recent_links_widget")
        fav = self._safe_get(self.window, "fav_widget")
        quick = self._safe_get(self.window, "quick_add_widget")
        self._set_visible_count(recent, "recentButton", c_r)
        self._set_visible_count(fav, "favoriteButton", c_f)
        self._set_visible_count(quick, "quickButton", c_q)
        self._last_applied = (width, c_r, c_f, c_q)

    def _get_cfg_int(self, key: str, default: int) -> int:
        try:
            return int(app_config.get(key, default))
        except (AttributeError, TypeError, ValueError):
            return default

    def _get_cfg_bool(self, key: str, default: bool) -> bool:
        try:
            return bool(app_config.get(key, default))
        except (AttributeError, TypeError, ValueError):
            return default
