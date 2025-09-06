from __future__ import annotations

import logging
from typing import Optional, List, Tuple
from weakref import WeakSet

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget, QSizePolicy

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
        self._last_applied: Optional[Tuple[int, int, int, int]] = None  # (width, recent, fav, quick)
        self._warmup_adjusts_remaining: int = 2
        self._container_widget: Optional[QWidget] = None
        self._watched_panels: WeakSet[QObject] = WeakSet()

        # Настройки из конфига с fallback
        self._throttle_interval_ms: int = self._get_cfg_int("ui.topbar.throttle_ms", self.DEFAULT_THROTTLE_MS)
        self._log_info: bool = self._get_cfg_bool("ui.topbar.log_info", self.DEFAULT_LOG_INFO)
        self._min_search_width: int = self._get_cfg_int("ui.topbar.min_search_width", self.DEFAULT_MIN_SEARCH_WIDTH)
        self._max_recent: int = self.DEFAULT_MAX_RECENT
        self._max_fav: int = self.DEFAULT_MAX_FAV
        self._max_quick: int = self.DEFAULT_MAX_QUICK
        # Минимальные квоты отключены: все панели могут схлопываться до 0
        self._min_recent: int = 0
        self._min_fav: int = 0
        self._min_quick: int = 0
        # Узкий режим: фиксированный порог 280, без переопределения конфигом
        self._narrow_threshold: int = self.DEFAULT_NARROW_THRESHOLD
        self._button_size: int = self._get_cfg_int("ui.top_panel_button_size", self.DEFAULT_BUTTON_SIZE)

        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._run_adjust)

        # Подключение к контейнерам
        self._install_event_filters()

        # Инициализационный пересчет после показа окна
        if hasattr(self.window, "shown"):
            self.window.shown.connect(self.adjust)

    def _install_event_filters(self) -> None:
        """Устанавливает фильтры событий на релевантные виджеты."""
        for attr_name in ["top_bar_host", "content_container", "quick_add_widget", "fav_widget", "recent_links_widget"]:
            widget = self._safe_get(self.window, attr_name)
            if isinstance(widget, QWidget) and widget not in self._watched_panels:
                widget.installEventFilter(self)
                self._watched_panels.add(widget)
        # Окно
        if isinstance(self.window, QWidget) and not _sip_isdeleted(self.window):
            self.window.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.Resize, QEvent.Type.LayoutRequest, QEvent.Type.Show, QEvent.Type.Hide):
            self._throttle_timer.start(0)
        return super().eventFilter(obj, event)

    def _run_adjust(self) -> None:
        self.adjust()

    def _safe_get(self, obj: Optional[object], name: str) -> Optional[object]:
        if obj is None or (isinstance(obj, QObject) and _sip_isdeleted(obj)):
            return None
        try:
            return getattr(obj, name, None)
        except RuntimeError:
            return None

    def _iter_buttons(self, panel_widget: Optional[QWidget], name: str) -> List[QToolButton]:
        if not panel_widget:
            return []
        bg = self._safe_get(panel_widget, "bg_frame")
        lay = (bg.layout() if isinstance(bg, QWidget) and callable(getattr(bg, "layout", None)) else None)
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

    def _set_visible_count(self, panel_widget: Optional[QWidget], btn_object_name: str, count: int) -> int:
        buttons = self._iter_buttons(panel_widget, btn_object_name)
        if not buttons:
            if panel_widget:
                panel_widget.setVisible(False)
                panel_widget.updateGeometry()
            return 0
        count = max(0, min(count, len(buttons)))
        for i, btn in enumerate(buttons):
            btn.setVisible(i < count)
        if panel_widget:
            panel_widget.setVisible(count > 0)
            panel_widget.updateGeometry()
        return count

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
        self._container_widget = self._safe_get(self.window, "top_bar_host") or self._safe_get(self.window, "content_container")
        return self._container_widget

    def adjust(self) -> None:
        container = self._get_container_widget()
        if not container or container.width() <= 0:
            return
        width = container.width()
        # Для активации узкого режима учитываем фактическую ширину окна, если доступна
        try:
            win_w = int(getattr(self.window, "width", lambda: width)())
            effective_w = min(width, win_w) if win_w > 0 else width
        except Exception:
            effective_w = width
        top_bar = self._get_top_bar()
        if not top_bar:
            return

        # Получить панели и поиск
        quick = self._safe_get(self.window, "quick_add_widget")
        fav = self._safe_get(self.window, "fav_widget")
        recent = self._safe_get(self.window, "recent_links_widget")
        search: Optional[QLineEdit] = self._safe_get(self.window, "search")

        self._install_event_filters()  # Убедиться в фильтрах

        if effective_w <= self._narrow_threshold:
            logger.debug("TopBar narrow mode: width=%s <= threshold=%s", width, self._narrow_threshold)
            self._apply_counts(width, 0, 0, 0)
            self._update_separators_visibility(top_bar, False, False, False, bool(search))
            # Скрыть любые виджеты top-bar, кроме поля поиска
            try:
                count = top_bar.count()
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
                        pass
                # Обнулить все spacerItem, чтобы не было отступов слева/справа от поиска
                try:
                    for i in range(count):
                        sp = top_bar.itemAt(i).spacerItem()
                        if sp is not None:
                            sp.changeSize(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                except Exception:
                    pass
                # Отключить встроенные действия у поиска (иконки слева/справа, кнопка очистки)
                if isinstance(search, QLineEdit):
                    try:
                        search.setClearButtonEnabled(False)
                    except Exception:
                        pass
                    try:
                        for act in search.actions():
                            try:
                                act.setVisible(False)
                            except Exception:
                                pass
                    except Exception:
                        pass
                # Нулевые отступы у top_bar, чтобы поиск примыкал к краям
                try:
                    self._set_top_bar_margins(top_bar, 0, 0, 0, 0)
                except Exception:
                    pass
                # Поиск занимает всю ширину
                try:
                    if isinstance(search, QLineEdit):
                        search.setMinimumWidth(0)
                        # Не ограничиваем maxWidth конкретным значением, чтобы тянулся на весь доступный размер
                        search.setMaximumWidth(16777215)
                        search.setSizePolicy(QSizePolicy.Policy.Expanding, search.sizePolicy().verticalPolicy())
                except Exception:
                    pass
                # Пересчитать лейаут, чтобы исключить наложение
                try:
                    # Зафиксировать stretch-факторы: только поиск тянется
                    self._enforce_stretches(top_bar, search)
                    top_bar.invalidate()
                    host = self._get_container_widget()
                    if isinstance(host, QWidget):
                        host.updateGeometry()
                        host.update()
                except Exception:
                    pass
            except Exception:
                logger.debug("TopBarLayoutManager: narrow-mode hide non-search widgets failed", exc_info=True)
            return

        # Кэшировать списки кнопок
        quick_btns = self._iter_buttons(quick, "quickButton")
        fav_btns = self._iter_buttons(fav, "favoriteButton")
        recent_btns = self._iter_buttons(recent, "recentButton")

        # Рассчитать видимые количества
        cnt_recent, cnt_fav, cnt_quick = self._compute_visible_counts(
            width, top_bar, search, recent, fav, quick, recent_btns, fav_btns, quick_btns
        )

        # Если расчёт показал, что места нет даже для одной кнопки любой панели — принудительно оставляем только поиск
        if cnt_recent == 0 and cnt_fav == 0 and cnt_quick == 0:
            try:
                self._apply_counts(width, 0, 0, 0)
                self._update_separators_visibility(top_bar, False, False, False, bool(search))
                count = top_bar.count()
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
                        pass
                # Обнулить все spacerItem, чтобы не было отступов
                try:
                    for i in range(count):
                        sp = top_bar.itemAt(i).spacerItem()
                        if sp is not None:
                            sp.changeSize(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                except Exception:
                    pass
                # Отключить встроенные действия у поиска
                if isinstance(search, QLineEdit):
                    try:
                        search.setClearButtonEnabled(False)
                    except Exception:
                        pass
                    try:
                        for act in search.actions():
                            try:
                                act.setVisible(False)
                            except Exception:
                                pass
                    except Exception:
                        pass
                # Нулевые отступы и перерасчёт
                try:
                    self._set_top_bar_margins(top_bar, 0, 0, 0, 0)
                    # Зафиксировать stretch-факторы: только поиск тянется
                    self._enforce_stretches(top_bar, search)
                    top_bar.invalidate()
                    host = self._get_container_widget()
                    if isinstance(host, QWidget):
                        host.updateGeometry()
                        host.update()
                except Exception:
                    pass
            except Exception:
                logger.debug("TopBarLayoutManager: forced narrow-mode hide due to zero counts failed", exc_info=True)
            return

        state = (width, cnt_recent, cnt_fav, cnt_quick)
        if self._last_applied == state:
            return

        if self._warmup_adjusts_remaining > 0:
            self._apply_counts(width, 0, 0, 0)
            self._warmup_adjusts_remaining -= 1
            self._throttle_timer.start(0)
            return

        # Применить
        recent_visible = self._set_visible_count(recent, "recentButton", cnt_recent)
        fav_visible = self._set_visible_count(fav, "favoriteButton", cnt_fav)
        quick_visible = self._set_visible_count(quick, "quickButton", cnt_quick)

        # Ограничить ширину панелей
        self._apply_panel_width_bounds(recent, recent_btns, recent_visible)
        self._apply_panel_width_bounds(fav, fav_btns, fav_visible)
        self._apply_panel_width_bounds(quick, quick_btns, quick_visible)

        self._last_applied = (width, recent_visible, fav_visible, quick_visible)
        msg = f"[TopBar] visible: recent={recent_visible}, fav={fav_visible}, quick={quick_visible}; min_search={self._min_search_width}"
        if self._log_info:
            logger.info(msg)
        else:
            logger.debug(msg)

        # В обычном режиме восстанавливаем отступы top_bar из конфига (лево/право)
        try:
            side = int(app_config.ui.get_top_bar_widgets_side_spacing())
        except Exception:
            side = 8
        self._set_top_bar_margins(top_bar, side, 0, side, 0)
        # Гарантируем стабильные stretch-факторы в обычном режиме
        self._enforce_stretches(top_bar, search)
        self._update_separators_visibility(top_bar, recent_visible > 0, fav_visible > 0, quick_visible > 0, search is not None)

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
            pass

    def _apply_panel_width_bounds(self, panel: Optional[QWidget], btns: List[QToolButton], visible: int) -> None:
        if not panel:
            return
        panel.setMinimumWidth(0)
        max_w = self._panel_width(panel, btns, visible) if visible > 0 else 0
        panel.setMaximumWidth(max_w)

    def _set_top_bar_margins(self, top_bar: QLayout, left: int, top: int, right: int, bottom: int) -> None:
        """Безопасно выставляет отступы для top_bar (QLayout)."""
        try:
            m = top_bar.contentsMargins()
            if m.left() == left and m.top() == top and m.right() == right and m.bottom() == bottom:
                return
        except Exception:
            pass
        try:
            top_bar.setContentsMargins(left, top, right, bottom)
        except Exception:
            pass

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
                    pass
            if search_index >= 0:
                try:
                    top_bar.setStretch(search_index, 1)
                except Exception:
                    pass
        except Exception:
            pass

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

        # Минимальные квоты отключены для единообразного поведения
        min_recent = 0
        min_fav = 0
        min_quick = 0

        cnt_recent, cnt_fav, cnt_quick = max_recent, max_fav, max_quick
        cnt_recent = max(min_recent, cnt_recent)
        cnt_fav = max(min_fav, cnt_fav)
        cnt_quick = max(min_quick, cnt_quick)

        max_steps = (cnt_recent - min_recent) + (cnt_fav - min_fav) + (cnt_quick - min_quick)
        steps = 0
        while self._total_width_for(top_bar, search, recent, fav, quick, recent_btns, fav_btns, quick_btns, cnt_recent, cnt_fav, cnt_quick) > width and steps < max_steps:
            steps += 1
            if cnt_recent > min_recent:
                cnt_recent -= 1
            elif cnt_fav > min_fav:
                cnt_fav -= 1
            elif cnt_quick > min_quick:
                cnt_quick -= 1
            else:
                break

        if self._total_width_for(top_bar, search, recent, fav, quick, recent_btns, fav_btns, quick_btns, cnt_recent, cnt_fav, cnt_quick) > width:
            cnt_recent, cnt_fav, cnt_quick = 0, 0, 0

        return cnt_recent, cnt_fav, cnt_quick

    def _panel_width(self, panel: Optional[QWidget], btns: List[QToolButton], count: int) -> int:
        if not panel or not btns or count <= 0:
            return 0
        bg = self._safe_get(panel, "bg_frame")
        lay = bg.layout() if bg else None
        spacing = lay.spacing() if lay else 0
        total = 0
        for i in range(count):
            # Используем реальную ширину кнопки (sizeHint), с fallback к конфигу
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
                    logical_visible_panel(right_widget) or (search_exists and isinstance(right_widget, QLineEdit))
                )
                w.setVisible(show_sep)
                # Спейсеры фиксированы на 4px
                left_sp = top_bar.itemAt(i - 1).spacerItem() if i - 1 >= 0 else None
                if left_sp:
                    left_sp.changeSize(self.DEFAULT_SPACER_SIZE, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                right_sp = top_bar.itemAt(i + 1).spacerItem() if i + 1 < count else None
                if right_sp:
                    right_sp.changeSize(self.DEFAULT_SPACER_SIZE, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
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