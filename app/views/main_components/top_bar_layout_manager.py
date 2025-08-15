# app/views/main_components/top_bar_layout_manager.py

from __future__ import annotations

from typing import List, Optional
import logging

from PyQt6 import QtCore
from PyQt6.QtCore import QObject, QEvent, QTimer
from PyQt6.QtWidgets import QWidget, QLayout, QToolButton, QLineEdit

from app.config_data import app_config


class TopBarLayoutManager(QObject):
    """Управляет иерархическим схлопыванием верхней панели при изменении размера.

    Порядок при сжатии:
      1) Поиск удерживает минимальную ширину (из конфига).
      2) Скрывать Recent по одной кнопке до min_recent (по умолчанию 0) — полностью, прежде чем трогать Favorites.
      3) Скрывать Favorites по одной кнопке до min_fav (по умолчанию 1).
      4) Скрывать QuickAdd по одной кнопке до min_quick (по умолчанию 1).
    При расширении — в обратном порядке восстанавливаем кнопки до лимитов.
    """

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._pending_adjust = False
        # Для стабилизации пересчетов
        self._last_applied: tuple[int, int, int, int] | None = None  # (width, recent, fav, quick)
        # Троттлинг пересчетов (мс)
        try:
            self._throttle_interval_ms: int = int(getattr(app_config, 'get', lambda *_: 50)('ui.topbar.throttle_ms', 50))
        except Exception:
            self._throttle_interval_ms = 50
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._run_adjust)
        # Переключатель уровня логирования видимости
        try:
            self._log_info: bool = bool(getattr(app_config, 'get', lambda *_: False)('ui.topbar.log_info', False))
        except Exception:
            self._log_info = False

        # Межпанельный зазор не навязываем — используем spacing топ-бара как есть

        # Настройки
        try:
            self._min_search_width = int(getattr(app_config, 'get_top_panel_search_min_width', lambda: 140)())
        except Exception:
            self._min_search_width = 140
        # Лимиты по умолчанию
        self._max_recent = 7
        self._max_fav = 10
        self._max_quick = 10

        # Подключаемся к контейнерам
        if hasattr(self.window, 'content_container') and isinstance(self.window.content_container, QWidget):
            self.window.content_container.installEventFilter(self)
        if hasattr(self.window, 'top_panel_container') and isinstance(self.window.top_panel_container, QWidget):
            self.window.top_panel_container.installEventFilter(self)
        # На всякий случай слушаем и окно (Resize)
        self.window.installEventFilter(self)

        # Инициализационный пересчет после показа окна
        if hasattr(self.window, 'shown'):
            # Первый тик сразу, затем еще один, чтобы дождаться отложенных виджетов
            self.window.shown.connect(lambda: QTimer.singleShot(0, self.adjust))
            self.window.shown.connect(lambda: QTimer.singleShot(50, self.adjust))

    # ---------------------------- Event Filter -----------------------------
    def eventFilter(self, obj: QObject, event: QtCore.QEvent) -> bool:
        # Минимизируем источники событий: только Resize окна и контейнера топ-панели
        if obj in (
            getattr(self.window, 'top_panel_container', None),
            getattr(self.window, 'content_container', None),
            self.window,
        ):
            if event.type() == QEvent.Type.Resize:
                self._request_adjust()
        return super().eventFilter(obj, event)

    def _ensure_panel_filters(self):
        """Навешивает фильтры на панели, если они уже созданы."""
        for w in (
            getattr(self.window, 'quick_add_widget', None),
            getattr(self.window, 'fav_widget', None),
            getattr(self.window, 'recent_links_widget', None),
        ):
            if isinstance(w, QWidget):
                w.installEventFilter(self)

    def _request_adjust(self):
        """Запросить пересчет с троттлингом и коалесингом событий."""
        if self._pending_adjust:
            # Уже запланировано — просто перезапустим таймер
            try:
                if self._throttle_interval_ms <= 0:
                    # Уже стоит задача на ближайший тик — ничего не делаем
                    pass
                else:
                    self._throttle_timer.start(self._throttle_interval_ms)
            except Exception:
                pass
            return
        self._pending_adjust = True
        try:
            if self._throttle_interval_ms <= 0:
                # Немедленный пересчет на следующем тике цикла событий
                QtCore.QTimer.singleShot(0, self._run_adjust)
            else:
                self._throttle_timer.start(self._throttle_interval_ms)
        except Exception:
            # Fallback: без таймера — сразу
            self._run_adjust()

    def _run_adjust(self):
        self._pending_adjust = False
        self.adjust()

    # ------------------------------ Helpers --------------------------------
    def _get_top_bar(self) -> Optional[QLayout]:
        cc = getattr(self.window, 'content_container', None)
        if not cc:
            return None
        return cc.layout()


    def _iter_buttons(self, panel_widget: Optional[QWidget], name: str) -> List[QToolButton]:
        if not panel_widget:
            return []
        try:
            # Собираем кнопки в порядке расположения в layout
            # Кнопки живут в bg_frame с собственным QHBoxLayout
            bg = getattr(panel_widget, 'bg_frame', None)
            lay = bg.layout() if isinstance(bg, QWidget) and callable(getattr(bg, 'layout', None)) else None
            ordered: List[QToolButton] = []
            if lay:
                for i in range(lay.count()):
                    w = lay.itemAt(i).widget()
                    if isinstance(w, QToolButton) and w.objectName() == name:
                        ordered.append(w)
            # На всякий случай добавим все найденные по findChildren
            for b in panel_widget.findChildren(QToolButton, name):
                if b not in ordered:
                    ordered.append(b)
            return ordered
        except Exception:
            return []

    def _set_visible_count(self, panel_widget: Optional[QWidget], btn_object_name: str, count: int) -> int:
        """Показывает первые count кнопок, остальные скрывает. Возвращает фактическое число видимых."""
        buttons = self._iter_buttons(panel_widget, btn_object_name)
        if not buttons:
            # Скрываем сам виджет, чтобы не занимал место
            if panel_widget:
                panel_widget.setVisible(False)
            return 0

        count = max(0, min(count, len(buttons)))
        for i, btn in enumerate(buttons):
            btn.setVisible(i < count)

        # Видимость панели только по факту наличия видимых кнопок
        if panel_widget:
            panel_widget.setVisible(count > 0)

        return count

    def _fixed_width_except(self, excludes: Optional[List[QWidget]] = None) -> int:
        """Суммарная ширина всех видимых виджетов top_bar, кроме поиска и excludes."""
        top_bar = self._get_top_bar()
        if not top_bar:
            return 0

        excludes = excludes or []
        spacing = top_bar.spacing() or 0

        visible_widgets: List[QWidget] = []
        for i in range(top_bar.count()):
            item = top_bar.itemAt(i)
            w = item.widget() if item else None
            if not w or not w.isVisible():
                continue
            if isinstance(w, QLineEdit):  # поиск
                continue
            if any(w is ex for ex in excludes if ex is not None):
                continue
            visible_widgets.append(w)

        total = 0
        for w in visible_widgets:
            total += w.sizeHint().width()
        if visible_widgets:
            total += spacing * (len(visible_widgets) - 1)
        # margins
        m = top_bar.contentsMargins()
        total += m.left() + m.right()
        return total

    # ------------------------------ Adjust ---------------------------------
    def adjust(self):
        """Пересчет видимости элементов верхней панели."""
        try:
            top_bar = self._get_top_bar()
            if not top_bar:
                return
            # Берем ширину топ-панели, а не всего контейнера окна
            container: Optional[QWidget] = getattr(self.window, 'top_panel_container', None)
            if not container:
                container = getattr(self.window, 'content_container', None)
            if not container:
                return
            width = container.width()
            if width <= 0:
                return

            # Панели
            quick = getattr(self.window, 'quick_add_widget', None)
            fav = getattr(self.window, 'fav_widget', None)
            recent = getattr(self.window, 'recent_links_widget', None)
            search: Optional[QLineEdit] = getattr(self.window, 'search', None)

            # Убедимся, что фильтры навешены на панели (при отложенном создании)
            self._ensure_panel_filters()

            # Узкий режим: ширина окна/контейнера <= минимальной ширины окна — скрыть все панели, оставить только поиск
            try:
                narrow_threshold = int(getattr(app_config, 'get_window_min_width', lambda: 280)())
            except Exception:
                narrow_threshold = 280
            if width <= narrow_threshold:
                # Скрываем все кнопки у Recent/Fav/Quick (по 0)
                self._set_visible_count(getattr(self.window, 'recent_links_widget', None), 'recentButton', 0)
                self._set_visible_count(getattr(self.window, 'fav_widget', None), 'favoriteButton', 0)
                self._set_visible_count(getattr(self.window, 'quick_add_widget', None), 'quickButton', 0)
                # Поиск — без минимальной ширины, чтобы занимал доступное
                if search:
                    try:
                        search.setMinimumWidth(0)
                        search.setMaximumWidth(16777215)
                    except Exception:
                        pass
                # Запоминаем состояние, чтобы не дёргать лейаут лишний раз
                self._last_applied = (width, 0, 0, 0)
                return

            # Получим списки кнопок
            quick_btns = self._iter_buttons(quick, 'quickButton')
            fav_btns = self._iter_buttons(fav, 'favoriteButton')
            recent_btns = self._iter_buttons(recent, 'recentButton')

            # Верхние пределы
            max_recent = min(self._max_recent, len(recent_btns))
            max_fav = min(self._max_fav, len(fav_btns))
            max_quick = min(self._max_quick, len(quick_btns))

            # Минимальные видимые количества из конфига (по умолчанию recent=0, fav=1, quick=1)
            try:
                cfg_min_recent = int(getattr(app_config, 'get', lambda *_: 0)('ui.topbar.min_visible.recent', 0))
            except Exception:
                cfg_min_recent = 0
            try:
                cfg_min_fav = int(getattr(app_config, 'get', lambda *_: 1)('ui.topbar.min_visible.fav', 1))
            except Exception:
                cfg_min_fav = 1
            try:
                cfg_min_quick = int(getattr(app_config, 'get', lambda *_: 1)('ui.topbar.min_visible.quick', 1))
            except Exception:
                cfg_min_quick = 1

            # Применяем минимум только если панель непуста; иначе 0
            min_recent = cfg_min_recent if max_recent > 0 else 0
            min_fav = cfg_min_fav if max_fav > 0 else 0
            min_quick = cfg_min_quick if max_quick > 0 else 0

            # Не меняем видимость на старте, чтобы не провоцировать лишние LayoutRequest

            # Вспомогательная функция для подсчета ширины N кнопок панели
            def panel_width(panel: Optional[QWidget], btns: list[QToolButton], count: int) -> int:
                if not panel or not btns or count <= 0:
                    return 0
                # Кнопки располагаются в bg_frame, берём spacing именно оттуда,
                # чтобы избежать конфликта с атрибутом instance-level 'layout'
                bg = getattr(panel, 'bg_frame', None)
                lay = bg.layout() if isinstance(bg, QWidget) and callable(getattr(bg, 'layout', None)) else None
                spacing = lay.spacing() or 0 if lay else 0
                total = 0
                for i, b in enumerate(btns[:count]):
                    w = b.sizeHint().width()
                    if i > 0:
                        w += spacing
                    total += w
                return total

            # Начальные количества
            cnt_recent = max_recent
            cnt_fav = max_fav
            cnt_quick = max_quick

            # Итеративно уменьшаем справа-налево, пока не влезем
            def total_width_for(count_recent: int, count_fav: int, count_quick: int) -> int:
                # Проходим по всем элементам top_bar по порядку и считаем суммарную ширину
                total = 0
                items = []
                for i in range(top_bar.count()):
                    it = top_bar.itemAt(i)
                    w = it.widget() if it else None
                    if not w:
                        continue
                    # Поиск — учитываем минимальную ширину
                    if isinstance(w, QLineEdit) and (w is search):
                        items.append(self._min_search_width)
                        continue
                    # Панели
                    if w is recent:
                        if count_recent > 0:
                            items.append(panel_width(recent, recent_btns, count_recent))
                        continue
                    if w is fav:
                        if count_fav > 0:
                            items.append(panel_width(fav, fav_btns, count_fav))
                        continue
                    if w is quick:
                        if count_quick > 0:
                            items.append(panel_width(quick, quick_btns, count_quick))
                        continue
                    # Прочие виджеты (разделители и т.п.)
                    if w.isVisible():
                        items.append(w.sizeHint().width())

                if not items:
                    return 0

                total = sum(items)
                # Добавляем межвиджетные отступы
                spacing = top_bar.spacing() or 0
                total += spacing * (len(items) - 1)
                # Добавляем маргины
                m = top_bar.contentsMargins()
                total += m.left() + m.right()
                return total

            # Гарантируем минимумы и ужимаем
            cnt_recent = max(min_recent, cnt_recent)
            cnt_fav = max(min_fav, cnt_fav)
            cnt_quick = max(min_quick, cnt_quick)

            guard = 0
            while total_width_for(cnt_recent, cnt_fav, cnt_quick) > width and guard < 1000:
                guard += 1
                # Уменьшаем справа: Recent -> Favorites -> Quick, но не ниже минимума (1 если панель непуста)
                if cnt_recent > min_recent:
                    cnt_recent -= 1
                    continue
                if cnt_fav > min_fav:
                    cnt_fav -= 1
                    continue
                if cnt_quick > min_quick:
                    cnt_quick -= 1
                    continue
                # Больше нельзя уменьшать — выходим
                break

            # Если состояние не меняется — выходим рано, чтобы не плодить LayoutRequest
            state = (width, cnt_recent, cnt_fav, cnt_quick)
            if self._last_applied == state:
                return

            # Установим видимые количества (без дополнительных ограничений ширины/политик)
            recent_visible = self._set_visible_count(recent, 'recentButton', cnt_recent)
            fav_visible = self._set_visible_count(fav, 'favoriteButton', cnt_fav)
            quick_visible = self._set_visible_count(quick, 'quickButton', cnt_quick)
            self._last_applied = (width, recent_visible, fav_visible, quick_visible)
            msg = f"[TopBar] visible: recent={recent_visible}, fav={fav_visible}, quick={quick_visible}; min_search={self._min_search_width}"
            if self._log_info:
                logging.info(msg)
            else:
                logging.debug(msg)

            # Поиск: минимум, максимум не ограничиваем (Expanding)
            if search:
                search.setMinimumWidth(self._min_search_width)
                try:
                    search.setMaximumWidth(16777215)
                except Exception:
                    pass

        except Exception:
            # Не роняем UI из-за ошибок расчета
            pass
