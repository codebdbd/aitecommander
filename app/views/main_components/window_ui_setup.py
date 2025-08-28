# app/views/main_components/window_ui_setup.py

import os
import sys

from PyQt6.QtCore import QEvent, QObject, Qt, QSize
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.controllers.ui.undo.stack import UndoManager
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.views.category_tiles import CategoryTiles
from app.views.custom_widgets import StructureTreeView
from app.views.models.structure_tree_model import StructureTreeModel
from app.views.effects.neon_effect import NeonEventFilter
from app.views.link import LinksTableView
from app.views.main_components.top_bar_layout_manager import TopBarLayoutManager
from app.views.status_bar import setup_status_bar as init_status_bar
from app.views.top_panel_widgets import TopPanelWidget

from .common import create_font


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
                except Exception:
                    self._saved_splitter_sizes = None
                try:
                    if stack is not None:
                        self._prev_stack_index = stack.currentIndex()
                except Exception:
                    self._prev_stack_index = None

                if splitter is not None:
                    try:
                        splitter.setCollapsible(0, True)
                        splitter.setSizes([0, max(1, w)])
                    except Exception:
                        pass

                if stack is not None and table is not None:
                    try:
                        for i in range(stack.count()):
                            wgt = stack.widget(i)
                            if wgt is table:
                                stack.setCurrentIndex(i)
                                break
                    except Exception:
                        pass
                self._is_collapsed = True

            # Независимо от состояния — скрыть панели топ-бара на каждом вызове (на случай добавления новых)
            for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
                try:
                    panel = getattr(self.window, attr, None)
                    if panel is not None:
                        panel.setVisible(False)
                except Exception:
                    pass

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
                except Exception:
                    pass

            # Показать панели топ-бара обратно
            for attr in ("quick_add_widget", "fav_widget", "recent_links_widget"):
                try:
                    panel = getattr(self.window, attr, None)
                    if panel is not None:
                        panel.setVisible(True)
                except Exception:
                    pass

            # Восстановить предыдущий вид правой области (если был сохранён)
            if stack is not None and self._prev_stack_index is not None:
                try:
                    if 0 <= self._prev_stack_index < stack.count():
                        stack.setCurrentIndex(self._prev_stack_index)
                except Exception:
                    pass

            self._is_collapsed = False

    def eventFilter(self, obj, event):
        if obj is self.window and event.type() == QEvent.Type.Resize:
            self._apply()
        return super().eventFilter(obj, event)


class WindowUISetup:
    """Компонент для настройки UI-элементов главного окна."""

    def __init__(self, window_initializer):
        self.window_initializer = window_initializer
        self.window = window_initializer.window
        self.settings = window_initializer.settings
        self.theme_ctrl = window_initializer.theme_ctrl

        # main_layout будет установлен позже
        self.main_layout = None

    def setup_basic_attributes(self):
        """Настройка базовых атрибутов окна."""
        self.window.settings = self.window_initializer.settings
        self.window.theme_ctrl = self.window_initializer.theme_ctrl
        self.window.current_category_id = None
        # Используем единый глобальный пул потоков из TaskScheduler
        self.window.thread_pool = get_task_scheduler().get_thread_pool()
        self.window.undo_stack = UndoManager(self.window)
        self.window.sphere_buttons = {}

    def setup_menu(self):
        """Настройка меню."""
        from app.controllers.ui.menu_controller import MenuController

        self.window.menu_controller = MenuController(self.window)
        self.window.setMenuBar(self.window.menu_controller.create_main_menu())

    def setup_central_widget(self):
        """Настройка центрального виджета."""
        central = QFrame()
        central.setFrameShape(
            getattr(QFrame.Shape, app_config.get_central_frame_shape())
        )
        self.window.setCentralWidget(central)

        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(*app_config.get_main_layout_margins())
        self.main_layout.setSpacing(app_config.get_main_layout_spacing())

    def setup_top_panel(self):
        """Настройка верхней панели."""
        # Верхний разделитель добавляем напрямую в основной layout
        h_line_top = QWidget()
        h_line_top.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_top)

        # Создание top_bar: без разделителей, только spacing и внешние маргины по side
        top_bar = QHBoxLayout()
        try:
            side = int(app_config.get_top_bar_widgets_side_spacing())
        except Exception:
            side = 8
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
            from PyQt6.QtWidgets import QSizePolicy
            top_bar_host.setFixedHeight(app_config.get_top_panel_container_height())
            top_bar_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass
        self.main_layout.addWidget(top_bar_host)

        # Сохраняем ссылку на хост
        self.window.top_bar_host = top_bar_host

        # Неоновый эффект: вешаем фильтр на хост и его детей
        if (
            not hasattr(self.window, "_neon_top_filter")
            or self.window._neon_top_filter is None
        ):
            self.window._neon_top_filter = NeonEventFilter(self.window, blur_radius=16)
        top_bar_host.installEventFilter(self.window._neon_top_filter)
        for w in top_bar_host.findChildren((QPushButton, QToolButton, QLineEdit)):
            w.installEventFilter(self.window._neon_top_filter)

        # Адаптивный менеджер верхней панели
        try:
            self.window._topbar_manager = TopBarLayoutManager(self.window)
        except Exception:
            # Не блокируем инициализацию UI при ошибке менеджера
            self.window._topbar_manager = None
        # Первичный пересчёт после создания
        try:
            from PyQt6.QtCore import QTimer

            if getattr(self.window, "_topbar_manager", None):
                QTimer.singleShot(0, self.window._topbar_manager.adjust)
        except Exception:
            pass
        

    def setup_top_bar_widgets(self, top_bar):
        """Настройка виджетов верхней панели.
        Создаём и добавляем все панели сразу, без отложенных прослоек:
        Порядок: QuickAdd → Favorites → Recent → Search
        """
        # Создание таблицы и настройка шрифта
        self.window.table = LinksTableView(self.window)
        font_size = (
            self.settings.get_font_size()
            if hasattr(self.settings, "get_font_size")
            else 12
        )
        if hasattr(self.window.table, "update_font_size"):
            self.window.table.update_font_size(font_size)

        # QuickAdd
        try:
            self.window.quick_add_widget = TopPanelWidget(
                self.window, mode="quick", category_provider=self.window
            )
            # Фиксированная политика размеров для кнопочных панелей
            self.window.quick_add_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            top_bar.addWidget(self.window.quick_add_widget)
        except Exception:
            self.window.quick_add_widget = None

        # Favorites
        try:
            self.window.fav_widget = TopPanelWidget(self.window, mode="favorites")
            # Совместимость со старым стилем/поиском через objectName
            self.window.fav_widget.setObjectName("favoritesWidget")
            self.window.fav_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            top_bar.addWidget(self.window.fav_widget)
        except Exception:
            self.window.fav_widget = None

        # Recent
        try:
            self.window.recent_links_widget = TopPanelWidget(self.window, mode="recent")
            self.window.recent_links_widget.setObjectName("recentLinksWidget")
            self.window.recent_links_widget.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            top_bar.addWidget(self.window.recent_links_widget)
        except Exception:
            self.window.recent_links_widget = None

        # Поиск (в конце, расширяется по ширине)
        self.setup_search_widget(top_bar)

    def setup_search_widget(self, top_bar):
        """Настройка поля поиска."""
        self.window.search = QLineEdit()
        self.window.search.setPlaceholderText(app_config.get_search_placeholder())
        self.window.search.setClearButtonEnabled(True)
        self.window.search.setFixedHeight(32)
        # Разрешаем горизонтальное сжатие/растяжение
        self.window.search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.window.search.setObjectName("mainSearch")

        # Применяем глобальный размер шрифта приложения
        try:
            base_size = self.window.font().pointSize()
            self.window.search.setFont(create_font(base_size))
        except Exception:
            # На случай сбоев оставляем шрифт по умолчанию
            pass
        self.window.search.textChanged.connect(self.window.on_search)
        top_bar.addWidget(self.window.search)

    def setup_main_content(self):
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

    def setup_left_panel(self, mid):
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

        font_size = (
            self.settings.get_font_size()
            if hasattr(self.settings, "get_font_size")
            else 12
        )
        if hasattr(self.window.tree, "update_font_size"):
            self.window.tree.update_font_size(font_size)
        left_layout.addWidget(self.window.tree)

        # Панель сфер
        self.setup_spheres_bar(left_layout)

    def setup_spheres_bar(self, left_layout):
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

    def setup_right_panel(self, mid):
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

        # Прямое добавление в стек без оберток
        self.window.stack.addWidget(self.window.tiles)
        self.window.stack.addWidget(self.window.table)

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
        except Exception:
            self.window.splitter.setHandleWidth(1)
        self.window.splitter.addWidget(self.window.left_panel)
        self.window.splitter.addWidget(right_panel)
        # Разрешаем сворачивание левой панели (после добавления виджетов, чтобы индекс 0 существовал)
        try:
            self.window.splitter.setCollapsible(0, True)
        except Exception:
            pass

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
        except Exception:
            min_w = 280
        try:
            self.window._auto_hide_tree_filter = _AutoHideTreeFilter(
                self.window, threshold_width=min_w, default_sizes=splitter_sizes
            )
            self.window.installEventFilter(self.window._auto_hide_tree_filter)
            # Один раз применим после инициализации
            self.window._auto_hide_tree_filter._apply()
        except Exception:
            # Не блокируем UI, если что-то пойдёт не так
            pass

        # QStackedLayout ломает стандартную Tab-навигацию Qt
        # Используем кастомную обработку через NavigationKeyHandler
        # Никаких setTabOrder - только динамическое управление фокусом

        # Установить нижней панели NoFocus policy чтобы исключить из Tab
        if hasattr(self.window, "bottom_bar_container"):
            self.window.bottom_bar_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def setup_bottom_panel(self):
        """Настройка нижней панели."""
        bot = QHBoxLayout()
        # Отступы панели берём из конфигурации (можно выставить в 0,0,0,0 для полного прилегания)
        bot.setContentsMargins(*app_config.get_layout_margins("bottom"))
        # Расстояние между кнопками: берём из конфига, по умолчанию 0 — кнопки занимают всю ширину без зазоров
        bot.setSpacing(app_config.get("ui.layout.spacing.bottom", 0))

        # Используем глобальный размер шрифта приложения для кнопок нижней панели
        font10 = QFont()
        try:
            font10.setPointSize(self.window.font().pointSize())
        except Exception:
            # Фоллбэк на 11 как дефолтный глобальный
            font10.setPointSize(11)

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
            except Exception:
                pass
            btn.clicked.connect(getattr(self.window, fn_name))
            bot.addWidget(btn)
            bottom_btns.append(btn)

        # Помечаем последнюю кнопку, чтобы убрать у неё правую границу через QSS
        if bottom_btns:
            try:
                bottom_btns[-1].setProperty("last", "1")
            except Exception:
                pass

        bottom_bar_container = QWidget()
        bottom_bar_container.setObjectName("bottomBarContainer")
        bottom_bar_container.setLayout(bot)
        # Явная политика: по горизонтали расширяется/сжимается, по вертикали фиксированная
        try:
            bottom_bar_container.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        except Exception:
            pass

        self.main_layout.addWidget(bottom_bar_container)

        # Разделитель под нижней панелью (аналог h_line_2)
        h_line_bottom = QWidget()
        h_line_bottom.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_bottom)

    def setup_status_bar(self):
        """Настройка статус-бара."""
        init_status_bar(self.window)

    def setup_shortcuts(self):
        """Настройка горячих клавиш."""
        # Горячие клавиши теперь управляются централизованно через KeyboardManager
        # в WindowControllersSetup.setup_keyboard_manager()
        pass

    def setup_window_properties(self):
        """Настройка базовых свойств окна."""
        self.window.setWindowTitle(app_config.get_main_window_title())
        self.window.resize(*app_config.get_main_window_size())
        # Применяем минимальные размеры окна из конфига, чтобы окно могло сжиматься
        try:
            min_w = int(app_config.get_window_min_width())
            min_h = int(app_config.get_window_min_height())
            self.window.setMinimumSize(min_w, min_h)
        except Exception:
            # В случае некорректных значений не блокируем инициализацию
            pass

        # Настройка иконки
        if hasattr(sys, "_MEIPASS"):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_path, "resources", "logo", "logo.png")
        self.window.setWindowIcon(create_icon_from_path(logo_path))
