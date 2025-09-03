# app/views/main_components/window_ui_setup.py

import os
import sys
import logging
logger = logging.getLogger(__name__)
from typing import Any, Optional

from PyQt6.QtCore import QEvent, QObject, QSize, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.controllers.ui.undo.stack import UndoManager
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.views.category_tiles import CategoryTiles
from app.views.custom_widgets import StructureTreeView
from app.views.link import LinksTableView
from app.views.main_components.top_bar_layout_manager import TopBarLayoutManager
from app.views.models.structure_tree_model import StructureTreeModel
from app.views.status_bar import setup_status_bar as init_status_bar
from app.views.top_panel_widgets import TopPanelWidget


class _AutoHideTreeFilter(QObject):
    """Фильтр событий адаптации UI при узком окне.
    При ширине окна <= threshold:
      - сворачивает левую панель (splitter: left=0)
      - скрывает панели топ-бара (QuickAdd, Favorites, Recent), оставляя только поиск
      - переключает правую область на таблицу (table-only)
    При расширении окна восстанавливает предыдущее состояние.
    """

    def __init__(self, window, threshold_width: int, default_sizes: list[int]):
        super().__init__(window)
        self.window = window
        self.threshold = int(threshold_width)
        self.default_sizes = (
            default_sizes[:] if isinstance(default_sizes, (list, tuple)) else [250, 750]
        )
        self._is_collapsed = False
        self._saved_splitter_sizes = None
        self._prev_stack_index = None

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
                    logging.debug("AutoHideTree: failed to read splitter sizes", exc_info=True)
                try:
                    if stack is not None:
                        self._prev_stack_index = stack.currentIndex()
                except (AttributeError, RuntimeError):
                    self._prev_stack_index = None
                    logging.debug("AutoHideTree: failed to read current stack index", exc_info=True)

                if splitter is not None:
                    try:
                        splitter.setCollapsible(0, True)
                        splitter.setSizes([0, max(1, w)])
                    except (RuntimeError, TypeError):
                        logging.debug("AutoHideTree: failed to collapse left panel on narrow window", exc_info=True)

                if stack is not None and table is not None:
                    try:
                        # Совместимость: таблица может быть добавлена как сам виджет или как контейнер
                        table_container = getattr(self.window, "table_container", None)
                        for i in range(stack.count()):
                            wgt = stack.widget(i)
                            if wgt is table or (table_container is not None and wgt is table_container):
                                stack.setCurrentIndex(i)
                                break
                    except (AttributeError, RuntimeError):
                        logging.debug("AutoHideTree: failed to switch stack to table", exc_info=True)
                self._is_collapsed = True

            # Независимо от состояния — скрыть панели топ-бара на каждом вызове (на случай добавления новых)
            for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
                try:
                    panel = getattr(self.window, attr, None)
                    if panel is not None:
                        panel.setVisible(False)
                except (AttributeError, RuntimeError):
                    logging.debug("AutoHideTree: failed to hide top bar panel '%s'", attr, exc_info=True)

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
                except (RuntimeError, TypeError, ValueError):
                    logging.debug("AutoHideTree: failed to restore splitter sizes", exc_info=True)

            # Показать панели топ-бара обратно
            for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
                try:
                    panel = getattr(self.window, attr, None)
                    if panel is not None:
                        panel.setVisible(True)
                except (AttributeError, RuntimeError):
                    logging.debug("AutoHideTree: failed to re-show top bar panel '%s'", attr, exc_info=True)

            # Восстановить предыдущий вид правой области (если был сохранён)
            if stack is not None and self._prev_stack_index is not None:
                try:
                    if 0 <= self._prev_stack_index < stack.count():
                        stack.setCurrentIndex(self._prev_stack_index)
                except (RuntimeError, ValueError, TypeError, AttributeError):
                    logging.debug("AutoHideTree: failed to restore previous stack index", exc_info=True)

            self._is_collapsed = False

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
        from app.controllers.ui.menu_controller import MenuController

        self.window.menu_controller = MenuController(self.window)
        self.window.setMenuBar(self.window.menu_controller.create_main_menu())

    def setup_central_widget(self) -> None:
        """Настройка центрального виджета."""
        central = QFrame()
        central.setFrameShape(
            getattr(QFrame.Shape, app_config.get_central_frame_shape())
        )
        self.window.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(*app_config.get_main_layout_margins())
        self.main_layout.setSpacing(app_config.get_main_layout_spacing())

    def setup_top_panel(self) -> None:
        """Настройка верхней панели."""
        # Верхний разделитель добавляем напрямую в основной layout
        h_line_top = QWidget()
        h_line_top.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_top)

        # Создание top_bar: без разделителей, только spacing и внешние маргины по side
        top_bar = QHBoxLayout()
        try:
            side = int(app_config.get_top_bar_widgets_side_spacing())
        except (TypeError, ValueError):
            side = 8
            logging.warning("TopPanel: invalid side spacing in config; using default 8")
        top_bar.setContentsMargins(side, 0, side, 0)
        top_bar.setSpacing(side * 2)
        top_bar.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Собираем виджеты верхней панели
        self.setup_top_bar_widgets(top_bar)

        # Лёгкий хост для top_bar (без фиксированной высоты) и добавление в основной layout
        top_bar_host = QWidget()
        top_bar_host.setObjectName("topBarHost")
        top_bar_host.setLayout(top_bar)
        try:
            top_bar_host.setFixedHeight(app_config.get_top_bar_height())
            top_bar_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except (RuntimeError, TypeError, AttributeError):
            logging.warning("TopPanel: failed to set top bar host size policy/height", exc_info=True)
        self.main_layout.addWidget(top_bar_host)

        # Сохраняем ссылку на хост
        self.window.top_bar_host = top_bar_host


        # Адаптивный менеджер верхней панели
        try:
            self.window._topbar_manager = TopBarLayoutManager(self.window)
        except (RuntimeError, TypeError):
            # Не блокируем инициализацию UI при ошибке менеджера
            self.window._topbar_manager = None
            logger.exception("TopPanel: failed to initialize TopBarLayoutManager")
        # Первичный пересчёт после создания (через внутренний троттлинг менеджера)
        try:
            mgr = getattr(self.window, "_topbar_manager", None)
            if mgr:
                mgr._request_adjust()
        except (AttributeError, TypeError, RuntimeError):
            logging.debug("TopPanel: failed to request initial topbar adjust", exc_info=True)
        

    def _create_top_panel_widget(
        self,
        top_bar: QHBoxLayout,
        mode: str,
        attr_name: str,
        object_name: Optional[str],
        log_label: str,
    ) -> None:
        """Фабрика для создания и добавления виджета верхней панели с обработкой ошибок."""
        try:
            if mode == "quick":
                widget = TopPanelWidget(self.window, mode=mode, category_provider=self.window)
            else:
                widget = TopPanelWidget(self.window, mode=mode)
            if object_name:
                widget.setObjectName(object_name)
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            setattr(self.window, attr_name, widget)
            top_bar.addWidget(widget)
        except Exception:
            setattr(self.window, attr_name, None)
            logger.exception("TopPanel: failed to create %s widget", log_label)

    def setup_top_bar_widgets(self, top_bar: QHBoxLayout) -> None:
        """Настройка виджетов верхней панели.
        Создаём и добавляем все панели сразу, без отложенных прослоек:
        Порядок: QuickAdd → Favorites → Recent → Search
        """
        # Создание таблицы (размер шрифта будет применён централизованно)
        self.window.table = LinksTableView(self.window)
        # Размер шрифта для таблицы устанавливается через MainWindow.apply_font_size_to_content()

        # Параметризованное создание QuickAdd, Favorites, Recent
        widgets_params = [
            ("quick", "quick_add_widget", None, "QuickAdd"),
            ("favorites", "fav_widget", "favoritesWidget", "Favorites"),
            ("recent", "recent_links_widget", "recentLinksWidget", "Recent"),
        ]
        for mode, attr_name, obj_name, label in widgets_params:
            self._create_top_panel_widget(top_bar, mode, attr_name, obj_name, label)

        # Поиск (в конце, расширяется по ширине)
        self.setup_search_widget(top_bar)

    def setup_search_widget(self, top_bar: QHBoxLayout) -> None:
        """Настройка поля поиска."""
        self.window.search = QLineEdit()
        self.window.search.setPlaceholderText(app_config.get_search_placeholder())
        self.window.search.setClearButtonEnabled(True)
        # Высота поля поиска берётся из конфигурации
        try:
            self.window.search.setFixedHeight(int(app_config.get_top_panel_search_height()))
        except (TypeError, ValueError, RuntimeError):
            self.window.search.setFixedHeight(32)
            logging.warning("SearchWidget: invalid search height in config; using 32")
        # Политика размеров и минимальная ширина — задаются один раз при инициализации
        # Разрешаем горизонтальное сжатие/растяжение
        self.window.search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        try:
            min_search_w = int(getattr(app_config, "get_top_panel_search_min_width", lambda: 140)())
        except (TypeError, ValueError):
            min_search_w = 140
            logging.debug("SearchWidget: fallback to default min_search_width=140")
        try:
            self.window.search.setMinimumWidth(min_search_w)
        except Exception:
            logging.debug("SearchWidget: failed to set minimum width", exc_info=True)
        self.window.search.setObjectName("mainSearch")

        # Размер шрифта поля поиска берётся из глобального шрифта приложения (без локальной установки)
        self.window.search.textChanged.connect(self.window.on_search)
        # Добавляем со stretch-фактором, чтобы строка поиска занимала всё оставшееся место
        top_bar.addWidget(self.window.search, 1)

    def setup_main_content(self) -> None:
        """Настройка основного содержимого."""
        # Горизонтальный разделитель
        h_line_top = QWidget()
        h_line_top.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_top)

        mid = QHBoxLayout()
        mid.setContentsMargins(*app_config.get_layout_margins("mid"))

        # Левая панель
        self.setup_left_panel(mid)

        # Правая панель с плитками и таблицей
        self.setup_right_panel(mid)

        self.main_layout.addLayout(mid)

        # Разделитель после основного содержимого
        h_line_2 = QWidget()
        h_line_2.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_2)

    def setup_left_panel(self, mid: QHBoxLayout) -> None:
        """Настройка левой панели."""
        left_panel = QWidget()
        self.window.left_panel = left_panel
        left_panel.setObjectName("LeftPanel")
        left_panel.setAutoFillBackground(True)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(*app_config.get_layout_margins("left"))

        # Дерево структуры: используем QTreeView + QAbstractItemModel
        self.window.tree = StructureTreeView()
        self.window.tree.setHeaderHidden(True)
        # Пустая модель, будет заполняться контроллерами позже
        self.window.tree_model = StructureTreeModel(self.window.tree)
        self.window.tree.setModel(self.window.tree_model)

        # Конфиг гарантирует list[int] -> берём ширину, ограничиваем высотой строки
        tree_icon_size = app_config.get_tree_icon_size()
        row_h = app_config.get_row_height()
        base_icon = int(tree_icon_size[0])
        eff_icon = max(0, min(base_icon, max(0, int(row_h) - 8)))  # 4px сверху + 4px снизу
        self.window.tree.setIconSize(QSize(eff_icon, eff_icon))

        # Размер шрифта для дерева устанавливается централизованно через MainWindow.apply_font_size_to_content()
        left_layout.addWidget(self.window.tree)

        # Панель сфер
        self.setup_spheres_bar(left_layout)

    def setup_spheres_bar(self, left_layout: QVBoxLayout) -> None:
        """Настройка панели сфер."""
        self.window.spheres_bar = QWidget()
        self.window.spheres_bar.setObjectName("spheres_bar")
        # Фиксированная высота берется из конфигурации (spheres_bar_height)
        self.window.spheres_bar.setFixedHeight(app_config.get_spheres_bar_height())

        s_layout = QHBoxLayout(self.window.spheres_bar)
        # Отступы панели сфер: поддержка левого/правого через ui.spheres_bar_margin_left/right
        s_layout.setContentsMargins(*app_config.get_spheres_bar_margins())
        # Расстояние между элементами панели сфер
        s_layout.setSpacing(app_config.get_spheres_bar_spacing())
        self.window.sphere_group = QButtonGroup(self.window)

        left_layout.addWidget(self.window.spheres_bar)

    def setup_right_panel(self, mid: QHBoxLayout) -> None:
        """Настройка правой панели."""
        # Плитки категорий - создаем без зависимостей, инжектируем позже
        self.window.tiles = CategoryTiles(parent=None)

        # ЦЕНТРАЛИЗОВАНО: Подключение к UIStateManager
        self.window.tiles.category_selected.connect(
            lambda cat_id: self.window.ui_state.load_category(
                cat_id, source="CategoryTiles"
            )
        )

        self.window.tiles_scroll = QScrollArea()
        self.window.tiles_scroll.setWidgetResizable(True)
        self.window.tiles_scroll.setWidget(self.window.tiles)

        tiles_wrapper = QWidget()
        tiles_layout = QVBoxLayout(tiles_wrapper)
        tiles_layout.setContentsMargins(*app_config.get_layout_margins("tiles"))
        tiles_layout.setSpacing(app_config.get("ui.layout.spacing.tiles", 0))
        tiles_layout.addWidget(self.window.tiles_scroll)

        # Обертка для таблицы
        table_wrapper = QWidget()
        table_layout = QVBoxLayout(table_wrapper)
        table_layout.setContentsMargins(*app_config.get_layout_margins("table"))
        table_layout.setSpacing(app_config.get("ui.layout.spacing.table", 4))
        table_layout.addWidget(self.window.table)

        # Стек для переключения между плитками и таблицей
        self.window.stack = QStackedLayout()

        # Добавляем в стек обёртки, чтобы сохранить отступы и прокрутку
        self.window.tiles_container = tiles_wrapper
        self.window.table_container = table_wrapper
        self.window.stack.addWidget(self.window.tiles_container)
        self.window.stack.addWidget(self.window.table_container)

        # Контейнер для правой панели
        right_panel = QWidget()
        right_panel.setLayout(self.window.stack)

        # Сплиттер
        self.window.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.window.splitter.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Толщина ручки сплиттера из конфигурации
        try:
            self.window.splitter.setHandleWidth(
                int(app_config.get_splitter_handle_width())
            )
        except (TypeError, ValueError, RuntimeError):
            self.window.splitter.setHandleWidth(1)
            logging.warning("RightPanel: invalid splitter handle width in config; using 1")
        self.window.splitter.addWidget(self.window.left_panel)
        self.window.splitter.addWidget(right_panel)
        # Разрешаем сворачивание левой панели (после добавления виджетов, чтобы индекс 0 существовал)
        try:
            self.window.splitter.setCollapsible(0, True)
        except (RuntimeError, TypeError):
            logging.debug("RightPanel: failed to set splitter collapsible(0, True)", exc_info=True)

        stretch_factors = app_config.get_splitter_stretch_factors()
        self.window.splitter.setStretchFactor(0, stretch_factors[0])
        self.window.splitter.setStretchFactor(1, stretch_factors[1])

        mid.addWidget(self.window.splitter)

        splitter_sizes = app_config.get_splitter_sizes()
        self.window.splitter.setSizes(splitter_sizes)
        self.window._first_structure_load = True

        # Установка фильтра авто-скрытия дерева при узком окне
        try:
            min_w = int(app_config.get_window_min_width())
        except (TypeError, ValueError):
            min_w = 280
            logging.warning("RightPanel: invalid window_min_width in config; using 280")
        try:
            self.window._auto_hide_tree_filter = _AutoHideTreeFilter(
                self.window, threshold_width=min_w, default_sizes=splitter_sizes
            )
            self.window.installEventFilter(self.window._auto_hide_tree_filter)
            # Один раз применим после инициализации
            self.window._auto_hide_tree_filter._apply()
        except (RuntimeError, TypeError, AttributeError):
            # Не блокируем UI, если что-то пойдёт не так
            logger.exception("RightPanel: failed to initialize AutoHideTree filter")

        # QStackedLayout ломает стандартную Tab-навигацию Qt
        # Используем кастомную обработку через NavigationKeyHandler
        # Никаких setTabOrder - только динамическое управление фокусом

        # Установить нижней панели NoFocus policy чтобы исключить из Tab
        if hasattr(self.window, "bottom_bar_container"):
            self.window.bottom_bar_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def setup_bottom_panel(self) -> None:
        """Настройка нижней панели."""
        bot = QHBoxLayout()
        # Отступы панели берём из конфигурации (можно выставить в 0,0,0,0 для полного прилегания)
        bot.setContentsMargins(*app_config.get_layout_margins("bottom"))
        # Расстояние между кнопками: берём из конфига, по умолчанию 0 — кнопки занимают всю ширину без зазоров
        bot.setSpacing(app_config.get("ui.layout.spacing.bottom", 0))

        # Используем глобальный размер шрифта приложения для кнопок нижней панели
        font10 = QFont()
        try:
            try:
                font10.setPointSize(self.window.font().pointSize())
            except (AttributeError, TypeError, RuntimeError, ValueError):
                # Ожидаемые проблемы типов/доступности — спокойный фоллбэк
                font10.setPointSize(10)
        except Exception:
            # Неожиданная ошибка — логируем и используем фоллбэк
            logging.exception("BottomPanel: unexpected error determining button font size; fallback to 10")
            font10.setPointSize(10)

        # Кнопка переключения сфер (будет создана после инициализации контроллеров)
        self.window.switch_sphere_button = None

        # Дополнительные кнопки из конфигурации
        bottom_actions = app_config.get_bottom_actions()
        bottom_btns = []
        for text, fn_name in bottom_actions:
            btn = QPushButton(text)
            btn.setFont(font10)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            # Разрешаем горизонтальное сжатие ниже sizeHint
            try:
                btn.setMinimumWidth(0)
                btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            except (RuntimeError, TypeError):
                logging.debug("BottomPanel: failed to apply size policy to bottom button '%s'", text, exc_info=True)
            # Обработчик клика и добавление на панель
            handler = getattr(self.window, fn_name, None)
            if not callable(handler):
                logging.warning("BottomPanel: click handler '%s' not found for button '%s' — skipping", fn_name, text)
                continue
            try:
                btn.clicked.connect(handler)
            except (TypeError, RuntimeError):
                logging.warning("BottomPanel: failed to connect handler '%s' for button '%s' — skipping", fn_name, text, exc_info=True)
                continue
            bot.addWidget(btn)
            bottom_btns.append(btn)

        # Помечаем последнюю кнопку, чтобы убрать у неё правую границу через QSS
        if bottom_btns:
            try:
                bottom_btns[-1].setProperty("last", "1")
            except (RuntimeError, AttributeError):
                logging.debug("BottomPanel: failed to set 'last' property on final button", exc_info=True)

        bottom_bar_container = QWidget()
        bottom_bar_container.setObjectName("bottomBarContainer")
        bottom_bar_container.setLayout(bot)
        # Сохраняем виджет как атрибут окна для последующей настройки фокуса
        self.window.bottom_bar_container = bottom_bar_container
        # Явная политика: по горизонтали расширяется/сжимается, по вертикали фиксированная
        try:
            bottom_bar_container.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        except (RuntimeError, TypeError):
            logging.debug("BottomPanel: failed to set size policy on bottom bar container", exc_info=True)

        self.main_layout.addWidget(bottom_bar_container)

        # Разделитель под нижней панелью (аналог h_line_2)
        h_line_bottom = QWidget()
        h_line_bottom.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_bottom)

    def setup_status_bar(self) -> None:
        """Настройка статус-бара."""
        init_status_bar(self.window)

    def setup_shortcuts(self) -> None:
        """Устарело: горячие клавиши настраивает KeyboardManager.

        Метод сохранён для обратной совместимости и намеренно ничего не делает,
        чтобы не дублировать логику. Фактическая настройка хоткеев выполняется
        централизованно через `KeyboardManager` в компоненте контроллеров.
        """
        logging.info(
            "WindowUISetup.setup_shortcuts(): устарело; горячие клавиши управляются KeyboardManager"
        )

    def setup_window_properties(self) -> None:
        """Настройка базовых свойств окна."""
        self.window.setWindowTitle(app_config.get_main_window_title())
        self.window.resize(*app_config.get_main_window_size())
        # Применяем минимальные размеры окна из конфига, чтобы окно могло сжиматься
        try:
            min_w = int(app_config.get_window_min_width())
            min_h = int(app_config.get_window_min_height())
            self.window.setMinimumSize(min_w, min_h)
        except (TypeError, ValueError):
            # В случае некорректных значений не блокируем инициализацию
            logging.warning("WindowProps: failed to set minimum size from config", exc_info=True)

        # Настройка иконки
        if hasattr(sys, "_MEIPASS"):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_path, "resources", "logo", "logo.png")
        self.window.setWindowIcon(create_icon_from_path(logo_path))
