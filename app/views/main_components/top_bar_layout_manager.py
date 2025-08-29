# app/views/main_components/top_bar_layout_manager.py

from __future__ import annotations

import logging

from PyQt6 import QtCore
from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QLayout, QLineEdit, QToolButton, QWidget

from app.config_data import app_config

try:
    # PyQt6 provides sip to detect deleted QObject wrappers
    from sip import isdeleted as _sip_isdeleted
except ImportError:  # pragma: no cover
    def _sip_isdeleted(_obj) -> bool:
        return False


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
        # Для стабилизации пересчетов
        self._last_applied: tuple[int, int, int, int] | None = (
            None  # (width, recent, fav, quick)
        )
        # Кэш контейнера топ-бара
        self._container_widget: QWidget | None = None
        # Троттлинг пересчетов (мс)
        try:
            self._throttle_interval_ms: int = int(
                getattr(app_config, "get", lambda *_: 50)("ui.topbar.throttle_ms", 50)
            )
        except (AttributeError, TypeError, ValueError):
            self._throttle_interval_ms = 50
            logging.debug("TopBarLayoutManager: fallback to default throttle_ms=50")
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._run_adjust)
        # Переключатель уровня логирования видимости
        try:
            self._log_info: bool = bool(
                getattr(app_config, "get", lambda *_: False)(
                    "ui.topbar.log_info", False
                )
            )
        except (AttributeError, TypeError, ValueError):
            self._log_info = False
            logging.debug("TopBarLayoutManager: fallback to default log_info=False")

        # Межпанельный зазор не навязываем — используем spacing топ-бара как есть

        # Настройки
        try:
            self._min_search_width = int(
                getattr(app_config, "get_top_panel_search_min_width", lambda: 140)()
            )
        except (AttributeError, TypeError, ValueError):
            self._min_search_width = 140
            logging.debug("TopBarLayoutManager: fallback to default min_search_width=140")
        # Лимиты по умолчанию
        self._max_recent = 7
        self._max_fav = 10
        self._max_quick = 10

        # Подключаемся к контейнерам (поддерживаем новый top_bar_host и старые контейнеры)
        tb = self._safe_get(self.window, "top_bar_host")
        if isinstance(tb, QWidget):
            tb.installEventFilter(self)
        cc = self._safe_get(self.window, "content_container")
        if isinstance(cc, QWidget):
            cc.installEventFilter(self)
        # legacy support — безопасно, если виджет существует
        tpc = self._safe_get(self.window, "top_panel_container")
        if isinstance(tpc, QWidget):
            tpc.installEventFilter(self)
        # На всякий случай слушаем и окно (Resize)
        try:
            if isinstance(self.window, QObject) and not _sip_isdeleted(self.window):
                self.window.installEventFilter(self)
        except RuntimeError:
            pass

        # Инициализационный пересчет после показа окна (один раз)
        if hasattr(self.window, "shown"):
            self.window.shown.connect(lambda: QTimer.singleShot(0, self.adjust))

    # ---------------------------- Event Filter -----------------------------
    def eventFilter(self, obj: QObject, event: QtCore.QEvent) -> bool:
        # Минимизируем источники событий: только Resize окна и контейнера топ-панели
        try:
            if self.window is None or _sip_isdeleted(self.window):
                return False
        except RuntimeError:
            return False

        watched = (
            self._safe_get(self.window, "top_bar_host"),
            self._safe_get(self.window, "top_panel_container"),
            self._safe_get(self.window, "content_container"),
            self.window if isinstance(self.window, QObject) else None,
        )
        if obj in watched:
            if event.type() == QEvent.Type.Resize:
                # Троттлинг пересчетов: запускаем таймер, пересчет выполняется в _run_adjust
                try:
                    self._throttle_timer.start(self._throttle_interval_ms)
                except (RuntimeError, TypeError, ValueError):
                    # На крайний случай без таймера пересчёт вручную
                    try:
                        self.adjust()
                    except (RuntimeError, AttributeError):
                        pass
                    except Exception:
                        logging.exception("TopBarLayoutManager.eventFilter: unexpected error during fallback adjust")
                except Exception:
                    logging.exception("TopBarLayoutManager.eventFilter: unexpected error starting throttle timer")
        return super().eventFilter(obj, event)

    def _ensure_panel_filters(self):
        """Навешивает фильтры на панели, если они уже созданы."""
        for w in (
            getattr(self.window, "quick_add_widget", None),
            getattr(self.window, "fav_widget", None),
            getattr(self.window, "recent_links_widget", None),
        ):
            if isinstance(w, QWidget):
                w.installEventFilter(self)

    def _request_adjust(self):
        """Запрос пересчёта с учётом троттлинга."""
        try:
            self._throttle_timer.start(self._throttle_interval_ms)
        except (RuntimeError, TypeError, ValueError):
            # Фоллбэк — выполнить сразу
            try:
                self.adjust()
            except (RuntimeError, AttributeError):
                pass
            except Exception:
                logging.exception("TopBarLayoutManager._request_adjust: unexpected error during fallback adjust")
        except Exception:
            logging.exception("TopBarLayoutManager._request_adjust: unexpected error starting throttle timer")

    def _run_adjust(self):
        self.adjust()

    # ------------------------------ Helpers --------------------------------
    def _get_top_bar(self) -> QLayout | None:
        host = self._safe_get(self.window, "top_bar_host")
        if isinstance(host, QWidget) and callable(getattr(host, "layout", None)):
            return host.layout()
        cc = self._safe_get(self.window, "content_container")
        if isinstance(cc, QWidget) and callable(getattr(cc, "layout", None)):
            return cc.layout()
        return None

    def _get_container_widget(self) -> QWidget | None:
        """Ленивая выборка контейнера, где лежит топ-панель, с кэшем."""
        if self._container_widget and isinstance(self._container_widget, QWidget):
            return self._container_widget
        container: QWidget | None = self._safe_get(self.window, "top_bar_host")
        if not container:
            container = self._safe_get(self.window, "top_panel_container")
        if not container:
            container = self._safe_get(self.window, "content_container")
        self._container_widget = container
        return container

    # ------------------------------ Utils ----------------------------------
    def _safe_get(self, obj: object | None, name: str):
        """Безопасно получает атрибут QObject, не падая на удалённых объектах PyQt."""
        if obj is None:
            return None
        try:
            # Если это QObject и он удалён — не трогаем
            if isinstance(obj, QObject) and _sip_isdeleted(obj):
                return None
        except RuntimeError:
            return None
        try:
            return getattr(obj, name, None)
        except RuntimeError:
            return None

    def _iter_buttons(
        self, panel_widget: QWidget | None, name: str
    ) -> list[QToolButton]:
        if not panel_widget:
            return []
        try:
            # Собираем кнопки в порядке расположения в layout
            # Кнопки живут в bg_frame с собственным QHBoxLayout
            bg = getattr(panel_widget, "bg_frame", None)
            lay = (
                bg.layout()
                if isinstance(bg, QWidget) and callable(getattr(bg, "layout", None))
                else None
            )
            ordered: list[QToolButton] = []
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
        except (AttributeError, RuntimeError):
            return []
        except Exception:
            logging.exception("TopBarLayoutManager._iter_buttons: unexpected error while collecting buttons")
            return []

    def _set_visible_count(
        self, panel_widget: QWidget | None, btn_object_name: str, count: int
    ) -> int:
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

    # _fixed_width_except удалён как неиспользуемый (логика ширин инкапсулирована в _compute_visible_counts)

    # ------------------------------ Adjust ---------------------------------
    def adjust(self):
        """Пересчет видимости элементов верхней панели."""
        try:
            top_bar = self._get_top_bar()
            if not top_bar:
                return
            # Берем ширину топ-панели, а не всего контейнера окна
            container: QWidget | None = self._get_container_widget()
            if not container:
                return
            width = container.width()
            if width <= 0:
                return

            # Панели
            quick = getattr(self.window, "quick_add_widget", None)
            fav = getattr(self.window, "fav_widget", None)
            recent = getattr(self.window, "recent_links_widget", None)
            search: QLineEdit | None = getattr(self.window, "search", None)

            # Убедимся, что фильтры навешены на панели (при отложенном создании)
            self._ensure_panel_filters()

            # Узкий режим: ширина окна/контейнера <= минимальной ширины окна — скрыть все панели, оставить только поиск
            try:
                narrow_threshold = int(
                    getattr(app_config, "get_window_min_width", lambda: 280)()
                )
            except (RuntimeError, TypeError, ValueError):
                narrow_threshold = 280
            except Exception:
                logging.exception("TopBarLayoutManager.adjust: unexpected error reading window min width; fallback to 280")
                narrow_threshold = 280
            if width <= narrow_threshold:
                self._apply_counts(width, 0, 0, 0, search)
                return

            # Получим списки кнопок
            quick_btns = self._iter_buttons(quick, "quickButton")
            fav_btns = self._iter_buttons(fav, "favoriteButton")
            recent_btns = self._iter_buttons(recent, "recentButton")

            # Верхние/минимальные пределы и расчет видимых количеств чистой функцией
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

            # Если состояние не меняется — выходим рано, чтобы не плодить LayoutRequest
            state = (width, cnt_recent, cnt_fav, cnt_quick)
            if self._last_applied == state:
                return

            # Установим видимые количества (без дополнительных ограничений ширины/политик)
            recent_visible = self._set_visible_count(recent, "recentButton", cnt_recent)
            fav_visible = self._set_visible_count(fav, "favoriteButton", cnt_fav)
            quick_visible = self._set_visible_count(quick, "quickButton", cnt_quick)
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
                except (RuntimeError, AttributeError, TypeError):
                    pass
                except Exception:
                    logging.exception("TopBarLayoutManager.adjust: unexpected error setting search maximum width")

        except (RuntimeError, AttributeError):
            # Не роняем UI из-за ожидаемых ошибок расчета
            pass
        except Exception:
            logging.exception("TopBarLayoutManager.adjust: unexpected error during adjust")

    # -------------------------- Pure calculation ---------------------------
    def _compute_visible_counts(
        self,
        width: int,
        top_bar: QLayout,
        search: QLineEdit | None,
        recent: QWidget | None,
        fav: QWidget | None,
        quick: QWidget | None,
        recent_btns: list[QToolButton],
        fav_btns: list[QToolButton],
        quick_btns: list[QToolButton],
    ) -> tuple[int, int, int]:
        # 1) Верхние пределы и минимальные значения
        max_recent = min(self._max_recent, len(recent_btns))
        max_fav = min(self._max_fav, len(fav_btns))
        max_quick = min(self._max_quick, len(quick_btns))

        cfg_min_recent = self._get_cfg_int("ui.topbar.min_visible.recent", 0)
        cfg_min_fav = self._get_cfg_int("ui.topbar.min_visible.fav", 1)
        cfg_min_quick = self._get_cfg_int("ui.topbar.min_visible.quick", 1)

        # Применяем минимум только если панель непуста; иначе 0
        min_recent = cfg_min_recent if max_recent > 0 else 0
        min_fav = cfg_min_fav if max_fav > 0 else 0
        min_quick = cfg_min_quick if max_quick > 0 else 0

        # 2) Начальные количества (старт с максимумов)
        cnt_recent = max_recent
        cnt_fav = max_fav
        cnt_quick = max_quick

        # 3) Применение минимумов
        cnt_recent = max(min_recent, cnt_recent)
        cnt_fav = max(min_fav, cnt_fav)
        cnt_quick = max(min_quick, cnt_quick)

        # 4) Ужатие до нужной ширины в пределах реального числа шагов
        max_steps = (cnt_recent - min_recent) + (cnt_fav - min_fav) + (cnt_quick - min_quick)
        steps = 0
        while (
            self._total_width_for(top_bar, search, recent, fav, quick, recent_btns, fav_btns, quick_btns, cnt_recent, cnt_fav, cnt_quick)
            > width
            and steps < max_steps
        ):
            steps += 1
            if cnt_recent > min_recent:
                cnt_recent -= 1
                continue
            if cnt_fav > min_fav:
                cnt_fav -= 1
                continue
            if cnt_quick > min_quick:
                cnt_quick -= 1
                continue
            break

        return cnt_recent, cnt_fav, cnt_quick

    def _panel_width(self, panel: QWidget | None, btns: list[QToolButton], count: int) -> int:
        """Возвращает ширину панели для первых `count` кнопок с учётом spacing."""
        if not panel or not btns or count <= 0:
            return 0
        bg = getattr(panel, "bg_frame", None)
        lay = (
            bg.layout() if isinstance(bg, QWidget) and callable(getattr(bg, "layout", None)) else None
        )
        spacing = lay.spacing() or 0 if lay else 0
        total = 0
        for i, b in enumerate(btns[:count]):
            w = b.sizeHint().width()
            if i > 0:
                w += spacing
            total += w
        return total

    def _total_width_for(
        self,
        top_bar: QLayout,
        search: QLineEdit | None,
        recent: QWidget | None,
        fav: QWidget | None,
        quick: QWidget | None,
        recent_btns: list[QToolButton],
        fav_btns: list[QToolButton],
        quick_btns: list[QToolButton],
        c_r: int,
        c_f: int,
        c_q: int,
    ) -> int:
        """Считает суммарную ширину top_bar для заданных количеств видимых кнопок панелей."""
        items: list[int] = []
        for i in range(top_bar.count()):
            it = top_bar.itemAt(i)
            w = it.widget() if it else None
            if not w:
                continue
            if isinstance(w, QLineEdit) and (w is search):
                items.append(self._min_search_width)
                continue
            if w is recent:
                if c_r > 0:
                    items.append(self._panel_width(recent, recent_btns, c_r))
                continue
            if w is fav:
                if c_f > 0:
                    items.append(self._panel_width(fav, fav_btns, c_f))
                continue
            if w is quick:
                if c_q > 0:
                    items.append(self._panel_width(quick, quick_btns, c_q))
                continue
            if w.isVisible():
                items.append(w.sizeHint().width())
        if not items:
            return 0
        total = sum(items)
        spacing = top_bar.spacing() or 0
        total += spacing * (len(items) - 1)
        m = top_bar.contentsMargins()
        total += m.left() + m.right()
        return total

    def _get_cfg_int(self, key: str, default: int) -> int:
        """Безопасно получает целочисленное значение конфигурации с запасным значением."""
        try:
            return int(getattr(app_config, "get", lambda *_: default)(key, default))
        except Exception:
            return default

    # ----------------------------- Apply -----------------------------------
    def _apply_counts(
        self, width: int, c_r: int, c_f: int, c_q: int, search: QLineEdit | None
    ) -> None:
        # Скрываем все кнопки у Recent/Fav/Quick (по 0 или заданное)
        recent = getattr(self.window, "recent_links_widget", None)
        fav = getattr(self.window, "fav_widget", None)
        quick = getattr(self.window, "quick_add_widget", None)
        self._set_visible_count(recent, "recentButton", c_r)
        self._set_visible_count(fav, "favoriteButton", c_f)
        self._set_visible_count(quick, "quickButton", c_q)
        if search:
            try:
                # В узком режиме позволяем занять всё
                if c_r == c_f == c_q == 0:
                    search.setMinimumWidth(0)
                else:
                    search.setMinimumWidth(self._min_search_width)
                search.setMaximumWidth(16777215)
            except Exception:
                pass
        self._last_applied = (width, c_r, c_f, c_q)
