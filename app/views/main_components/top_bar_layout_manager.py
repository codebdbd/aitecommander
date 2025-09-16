from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple
from weakref import WeakSet

from PyQt6.QtCore import (
    QEvent,
    QObject,
    QTimer,
)
from PyQt6.QtWidgets import (
    QLayout,
    QLineEdit,
    QToolButton,
    QWidget,
)

from app.config_data import app_config
from app.views.main_components.topbar_layout.topbar_measure import (
    iter_buttons as _tb_iter_buttons,
    current_visible_count as _tb_current_visible_count,
    panel_width as _tb_panel_width,
    total_width_for as _tb_total_width_for,
    compute_visible_counts as _tb_compute_visible_counts,
)
from app.views.main_components.topbar_layout.topbar_layout_utils import (
    safe_get as _u_safe_get,
    get_top_bar as _u_get_top_bar,
    set_top_bar_margins as _u_set_top_bar_margins,
    enforce_stretches as _u_enforce_stretches,
    apply_panel_width_bounds as _u_apply_panel_width_bounds,
    zero_all_spacers as _u_zero_all_spacers,
    apply_counts as _u_apply_counts,
    clamp_search_width_to_remaining_space as _u_clamp_search_width,
    install_topbar_event_filters as _u_install_event_filters,
)
from app.views.main_components.topbar_layout.topbar_narrow_mode import (
    apply_narrow_mode as _apply_narrow_mode,
)
from app.views.main_components.topbar_layout.topbar_separators import (
    update_separators_visibility as _u_update_separators_visibility,
)
from app.views.main_components.topbar_layout.topbar_diagnostics import (
    log_layout_snapshot as _u_log_layout_snapshot,
)
from app.views.main_components.topbar_layout.constants import (
    DEFAULT_THROTTLE_MS,
    DEFAULT_LOG_INFO,
    DEFAULT_MIN_SEARCH_WIDTH,
    DEFAULT_MAX_RECENT,
    DEFAULT_MAX_FAV,
    DEFAULT_MAX_QUICK,
    DEFAULT_MIN_RECENT,
    DEFAULT_MIN_FAV,
    DEFAULT_MIN_QUICK,
    DEFAULT_NARROW_THRESHOLD,
    DEFAULT_BUTTON_SIZE,
    DEFAULT_SPACER_SIZE,
)

# Убрана зависимость от sip.isdeleted: вместо проверки "удалённости" виджета
# повторно и безопасно получаем контейнер по атрибутам окна при каждом запросе.


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

    # Константы по умолчанию (вынесены в topbar_layout.constants)

    def __init__(self, window):
        super().__init__(window)
        self.window: QObject = window
        self._last_applied: Optional[Tuple[int, int, int, int]] = (
            None  # (width, recent, fav, quick)
        )
        self._warmup_adjusts_remaining: int = 2
        self._container_widget: Optional[QWidget] = None
        self._watched_panels: WeakSet[QObject] = WeakSet()
        self._cfg_cache: dict[str, object] = {}

        # Настройки из конфига с fallback
        self._throttle_interval_ms: int = self._get_cfg_int(
            "ui.topbar.throttle_ms", DEFAULT_THROTTLE_MS
        )
        self._log_info: bool = self._get_cfg_bool(
            "ui.topbar.log_info", DEFAULT_LOG_INFO
        )
        self._min_search_width: int = self._get_cfg_int(
            "ui.topbar.min_search_width", DEFAULT_MIN_SEARCH_WIDTH
        )
        self._max_recent: int = DEFAULT_MAX_RECENT
        self._max_fav: int = DEFAULT_MAX_FAV
        self._max_quick: int = DEFAULT_MAX_QUICK
        # Минимальные квоты отключены: все панели могут схлопываться до 0
        self._min_recent: int = DEFAULT_MIN_RECENT
        self._min_fav: int = DEFAULT_MIN_FAV
        self._min_quick: int = DEFAULT_MIN_QUICK
        # Узкий режим: порог теперь настраиваемый через конфиг ui.topbar.narrow_threshold
        # (по умолчанию DEFAULT_NARROW_THRESHOLD)
        try:
            self._narrow_threshold: int = int(
                app_config.get("ui.topbar.narrow_threshold", DEFAULT_NARROW_THRESHOLD)
            )
        except (AttributeError, TypeError, ValueError):
            self._narrow_threshold = DEFAULT_NARROW_THRESHOLD
        self._button_size: int = self._get_cfg_int(
            "ui.top_panel_button_size", DEFAULT_BUTTON_SIZE
        )
        # No extra safety pads: use exact computed widths to avoid clipping

        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._run_adjust)
        # Adaptive throttle (optional via config)
        self._dynamic_throttle: bool = self._get_cfg_bool("ui.topbar.dynamic_throttle", False)
        self._last_event_monotonic: float = 0.0

        # Анимация отключена: метод _apply_with_animation и связанные настройки удалены как неиспользуемые

        # Подключение к контейнерам
        self._install_event_filters()

        # Инициализационный пересчет после показа окна выполняется в WindowUISetup,
        # чтобы избежать дублирующих вызовов adjust() и гонок таймингов здесь не подписываемся на shown

    def _install_event_filters(self) -> None:
        """Устанавливает фильтры событий на релевантные виджеты.

        Делегирует в `topbar_layout.topbar_layout_utils.install_topbar_event_filters`.
        """
        _u_install_event_filters(
            window=self.window,
            watched_set=self._watched_panels,
            event_filter_obj=self,
            safe_get=self._safe_get,
        )

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.LayoutRequest,
            QEvent.Type.Show,
            QEvent.Type.Hide,
        ):
            # Используем настраиваемый интервал троттлинга; при dynamic_throttle ускоряемся в бурстах
            interval = self._throttle_interval_ms
            if self._dynamic_throttle:
                now = time.monotonic()
                dt_ms = int((now - self._last_event_monotonic) * 1000.0) if self._last_event_monotonic else None
                # Если события идут частым бурстом — реагируем быстрее, чтобы UI не казался «ленивым»
                if dt_ms is not None and dt_ms <= max(2, interval // 2):
                    interval = 0
                self._last_event_monotonic = now
            self._throttle_timer.start(max(0, int(interval)))
        return super().eventFilter(obj, event)

    def _run_adjust(self) -> None:
        self.adjust()

    def _safe_get(self, obj: Optional[object], name: str) -> Optional[object]:
        """Безопасный getattr.

        Делегирует в `topbar_layout.topbar_layout_utils.safe_get`.
        """
        return _u_safe_get(obj, name)

    def _iter_buttons(
        self, panel_widget: Optional[QWidget], name: str
    ) -> List[QToolButton]:
        """Возвращает упорядоченные кнопки панели.

        Делегирует в `topbar_layout.topbar_measure.iter_buttons`.
        """
        return _tb_iter_buttons(panel_widget, name)

    def _set_visible_count(
        self, panel_widget: Optional[QWidget], btn_object_name: str, count: int
    ) -> int:
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
            try:
                panel_widget.updateGeometry()
            except Exception:
                pass
        return count

    def _current_visible_count(self, btns: List[QToolButton]) -> int:
        """Количество видимых кнопок (по последнему видимому индексу).

        Делегирует в `topbar_layout.topbar_measure.current_visible_count`.
        """
        return _tb_current_visible_count(btns)

    def _get_top_bar(self) -> Optional[QLayout]:
        """Найти лэйаут верхней панели в окне.

        Делегирует в `topbar_layout.topbar_layout_utils.get_top_bar`.
        """
        return _u_get_top_bar(self.window)

    def _get_container_widget(self) -> Optional[QWidget]:
        # Без проверки через sip.isdeleted: повторно получаем актуальную ссылку
        container = self._safe_get(self.window, "top_bar_host") or self._safe_get(
            self.window, "content_container"
        )
        # Кэшируем на время жизни, но не полагаемся на кэш при следующем вызове
        self._container_widget = container if isinstance(container, QWidget) else None
        return self._container_widget

    def adjust(self) -> None:
        pre = self._compute_layout_state()
        if pre is None:
            return
        (
            container,
            width,
            effective_w,
            top_bar,
            quick,
            fav,
            recent,
            search,
        ) = pre

        # Узкий режим — отдельная ветка
        if effective_w <= self._narrow_threshold:
            logger.debug(
                "TopBar narrow mode: width=%s <= threshold=%s",
                width,
                self._narrow_threshold,
            )
            self._apply_narrow_mode_state(width, top_bar, search)
            return

        # Кнопки панелей
        quick_btns = self._iter_buttons(quick, "quickButton")
        fav_btns = self._iter_buttons(fav, "favoriteButton")
        recent_btns = self._iter_buttons(recent, "recentButton")

        # Рассчитать целевые количества
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

        # Обработка zero-count
        if self._handle_zero_count(width, effective_w, top_bar, search, cnt_recent, cnt_fav, cnt_quick):
            return

        # Гистерезис (стабилизация)
        cnt_recent, cnt_fav, cnt_quick = self._apply_hysteresis(
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

        # Прогрев: сначала (0,0,0)
        if self._warmup_adjusts_remaining > 0:
            self._apply_counts(width, 0, 0, 0)
            self._warmup_adjusts_remaining -= 1
            self._throttle_timer.start(0)
            return

        # Применить рассчитанные количества пакетно
        recent_visible, fav_visible, quick_visible = self._apply_layout_state(
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

        # Финализация оформления и ограничение поиска
        self._finalize_layout(
            top_bar,
            search,
            recent_visible,
            fav_visible,
            quick_visible,
        )



    def _zero_all_spacers(self, top_bar: QLayout) -> None:
        """Схлопнуть все spacerItem до нуля.

        Делегирует в `topbar_layout.topbar_layout_utils.zero_all_spacers`.
        """
        _u_zero_all_spacers(top_bar)

    def _apply_panel_width_bounds(
        self, panel: Optional[QWidget], btns: List[QToolButton], visible: int
    ) -> None:
        """Ограничить максимальную ширину панели по расчёту.

        Делегирует в `topbar_layout.topbar_layout_utils.apply_panel_width_bounds`.
        """
        _u_apply_panel_width_bounds(
            panel,
            btns,
            visible,
            panel_width_func=self._panel_width,
        )

    def _set_top_bar_margins(
        self, top_bar: QLayout, left: int, top: int, right: int, bottom: int
    ) -> None:
        _u_set_top_bar_margins(top_bar, left, top, right, bottom)

    def _enforce_stretches(self, top_bar: QLayout, search: Optional[QLineEdit]) -> None:
        _u_enforce_stretches(top_bar, search)

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
        """Рассчитать видимые количества кнопок на панелях.

        Делегирует в `topbar_layout.topbar_measure.compute_visible_counts` и логирует снапшот.
        """
        cnt_recent, cnt_fav, cnt_quick = _tb_compute_visible_counts(
            width=width,
            top_bar=top_bar,
            search=search,
            recent=recent,
            fav=fav,
            quick=quick,
            recent_btns=recent_btns,
            fav_btns=fav_btns,
            quick_btns=quick_btns,
            max_recent_cap=self._max_recent,
            max_fav_cap=self._max_fav,
            max_quick_cap=self._max_quick,
            total_width_for_func=self._total_width_for,
        )

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
        _u_log_layout_snapshot(
            container_w=container_w,
            top_bar=top_bar,
            search=search,
            recent=recent,
            fav=fav,
            quick=quick,
            recent_btns=recent_btns,
            fav_btns=fav_btns,
            quick_btns=quick_btns,
            c_r=c_r,
            c_f=c_f,
            c_q=c_q,
            total_width_for_func=self._total_width_for,
        )

    def _panel_width(
        self, panel: Optional[QWidget], btns: List[QToolButton], count: int
    ) -> int:
        """Ширина панели с учётом margins/spacing.

        Делегирует в `topbar_layout.topbar_measure.panel_width`.
        """
        return _tb_panel_width(panel, btns, count, button_size=self._button_size)

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
        """Суммарная требуемая ширина top-bar.

        Делегирует в `topbar_layout.topbar_measure.total_width_for`.
        """
        return _tb_total_width_for(
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
            button_size=self._button_size,
            min_search_width=self._min_search_width,
        )

    def _update_separators_visibility(
        self,
        top_bar: QLayout,
        recent_visible: bool,
        fav_visible: bool,
        quick_visible: bool,
        search_exists: bool,
    ) -> None:
        """Обновить видимость вертикальных разделителей.

        Делегирует в `topbar_layout.topbar_separators.update_separators_visibility`.
        """
        _u_update_separators_visibility(
            top_bar=top_bar,
            window=self.window,
            recent_visible=recent_visible,
            fav_visible=fav_visible,
            quick_visible=quick_visible,
            search_exists=search_exists,
            safe_get=self._safe_get,
            spacer_size=DEFAULT_SPACER_SIZE,
        )

    def _apply_narrow_mode_state(
        self,
        width: int,
        top_bar: QLayout,
        search: Optional[QLineEdit],
    ) -> None:
        """Применить состояние узкого режима: только поиск, без отступов у панелей.

        Повторяет ранее дублированную логику внутри `adjust()`:
        - обнуление видимых кнопок на всех панелях,
        - обновление разделителей как скрытых панелей,
        - применение узкого режима к лэйауту.
        """
        self._apply_counts(width, 0, 0, 0)
        self._update_separators_visibility(
            top_bar, False, False, False, bool(search)
        )
        _apply_narrow_mode(
            top_bar=top_bar,
            search=search,
            set_top_bar_margins=self._set_top_bar_margins,
            enforce_stretches=self._enforce_stretches,
            get_container_widget=self._get_container_widget,
        )

    def _apply_counts(self, width: int, c_r: int, c_f: int, c_q: int) -> None:
        _u_apply_counts(
            window=self.window,
            set_visible_count=self._set_visible_count,
            safe_get=self._safe_get,
            c_r=c_r,
            c_f=c_f,
            c_q=c_q,
        )
        self._last_applied = (width, c_r, c_f, c_q)

    def _get_cfg_int(self, key: str, default: int) -> int:
        # Простое кэширование чтений конфига в рамках жизни менеджера
        if key in self._cfg_cache:
            try:
                return int(self._cfg_cache[key])
            except Exception:
                del self._cfg_cache[key]
        try:
            val = int(app_config.get(key, default))
            self._cfg_cache[key] = val
            return val
        except (AttributeError, TypeError, ValueError):
            self._cfg_cache[key] = default
            return default

    # --- Helpers extracted from adjust() ---

    def _compute_layout_state(self):
        container = self._get_container_widget()
        if not container or container.width() <= 0:
            return None
        # Не меняем раскладку, пока контейнер верхней панели ещё скрыт
        try:
            if hasattr(container, "isVisible") and not container.isVisible():
                return None
        except (AttributeError, RuntimeError):
            # Непредвидимые ошибки получения видимости контейнера не критичны для продолжения
            logger.debug("TopBarLM: failed to check container visibility", exc_info=True)
        width = container.width()
        # Учитываем фактическую ширину окна, если доступна
        try:
            win_w = int(getattr(self.window, "width", lambda: width)())
            effective_w = min(width, win_w) if win_w > 0 else width
        except (TypeError, ValueError, RuntimeError, AttributeError):
            effective_w = width
        top_bar = self._get_top_bar()
        if not top_bar:
            return None
        # Получить панели и поиск
        quick = self._safe_get(self.window, "quick_add_widget")
        fav = self._safe_get(self.window, "fav_widget")
        recent = self._safe_get(self.window, "recent_links_widget")
        search: Optional[QLineEdit] = self._safe_get(self.window, "search")
        return (container, width, effective_w, top_bar, quick, fav, recent, search)

    def _apply_hysteresis(
        self,
        width: int,
        top_bar,
        search,
        recent,
        fav,
        quick,
        recent_btns,
        fav_btns,
        quick_btns,
        cnt_recent: int,
        cnt_fav: int,
        cnt_quick: int,
    ) -> tuple[int, int, int]:
        state = (width, cnt_recent, cnt_fav, cnt_quick)
        if self._last_applied == state:
            return cnt_recent, cnt_fav, cnt_quick
        prev_counts = self._last_applied
        if prev_counts is not None:
            _, pr, pf, pq = prev_counts
            total_new = self._total_width_for(
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
            band = max(8, int(self._button_size // 2))
            if abs(width - total_new) < band:
                return pr, pf, pq
        return cnt_recent, cnt_fav, cnt_quick

    def _handle_zero_count(
        self,
        width: int,
        effective_w: int,
        top_bar,
        search,
        cnt_recent: int,
        cnt_fav: int,
        cnt_quick: int,
    ) -> bool:
        if cnt_recent == 0 and cnt_fav == 0 and cnt_quick == 0:
            if effective_w <= self._narrow_threshold:
                try:
                    self._apply_narrow_mode_state(width, top_bar, search)
                except Exception:
                    logger.debug(
                        "TopBarLayoutManager: zero-count narrow-mode handling failed",
                        exc_info=True,
                    )
                return True
            # Не узкий режим: не шорткатим. Возвращаем False, чтобы дать шансу общей ветке
            # применить состояние и выполнить _finalize_layout единообразно.
            # Ранее здесь выполнялось локальное применение 0,0,0 и финализация с возвратом True,
            # что пропускало дальнейшие шаги и могло приводить к расхождениям.
            return False
        return False

    def _apply_layout_state(
        self,
        width: int,
        top_bar,
        search,
        recent,
        fav,
        quick,
        recent_btns,
        fav_btns,
        quick_btns,
        cnt_recent: int,
        cnt_fav: int,
        cnt_quick: int,
    ) -> tuple[int, int, int]:
        recent_visible = fav_visible = quick_visible = 0
        try:
            from app.utils.ui.updates import suspend_updates
        except Exception:
            suspend_updates = None

        def _apply_one(panel, btns, btn_name, target):
            cur = self._current_visible_count(btns)
            if target < cur:
                self._apply_panel_width_bounds(panel, btns, target)
                return self._set_visible_count(panel, btn_name, target)
            else:
                vis = self._set_visible_count(panel, btn_name, target)
                self._apply_panel_width_bounds(panel, btns, vis)
                return vis

        def _batch_apply():
            nonlocal recent_visible, fav_visible, quick_visible
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
            except (RuntimeError, AttributeError, TypeError, ValueError):
                logger.exception("TopBarLM: pre-apply snapshot failed")
            recent_visible = _apply_one(recent, recent_btns, "recentButton", cnt_recent)
            fav_visible = _apply_one(fav, fav_btns, "favoriteButton", cnt_fav)
            quick_visible = _apply_one(quick, quick_btns, "quickButton", cnt_quick)

        if suspend_updates is not None and isinstance(self.window, QWidget):
            try:
                with suspend_updates(self.window):
                    _batch_apply()
            except (RuntimeError, AttributeError):
                # Если при приостановке обновлений произошла ожидаемая ошибка — применяем напрямую
                _batch_apply()
            except Exception:
                # Неожиданные исключения — логируем стек и применяем напрямую
                logger.exception("TopBarLM: unexpected error inside suspend_updates; applying without suspension")
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
        return recent_visible, fav_visible, quick_visible

    def _finalize_layout(
        self,
        top_bar,
        search,
        recent_visible: int,
        fav_visible: int,
        quick_visible: int,
    ) -> None:
        try:
            side = int(app_config.ui.get_top_bar_widgets_side_spacing())
        except Exception:
            side = 8
        self._set_top_bar_margins(top_bar, side, 0, side, 0)
        self._enforce_stretches(top_bar, search)
        self._update_separators_visibility(
            top_bar,
            recent_visible > 0,
            fav_visible > 0,
            quick_visible > 0,
            search is not None,
        )
        try:
            if isinstance(search, QLineEdit):
                _u_clamp_search_width(
                    top_bar=top_bar,
                    search=search,
                    get_container_widget=self._get_container_widget,
                    min_search_width=self._min_search_width,
                )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            logger.exception("TopBarLM: failed to clamp search width to remaining space")

    def _get_cfg_bool(self, key: str, default: bool) -> bool:
        if key in self._cfg_cache:
            try:
                return bool(self._cfg_cache[key])
            except Exception:
                del self._cfg_cache[key]
        try:
            val = bool(app_config.get(key, default))
            self._cfg_cache[key] = val
            return val
        except (AttributeError, TypeError, ValueError):
            self._cfg_cache[key] = default
            return default
