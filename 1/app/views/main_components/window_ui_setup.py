# app/views/main_components/window_ui_setup.py

import logging
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedLayout,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.config_data import app_config
from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.system.task_scheduler import LimitedThreadPool
from app.utils.system.undo.stack import UndoManager
from app.views.category_tiles import CategoryTiles
from app.views.custom_widgets import StructureTreeWidget
from app.views.favorites_widget import FavoritesWidget
from app.views.link import LinksTableView
from app.views.quick_add_widget import QuickAddWidget
from app.views.recent_links_widget import RecentLinksWidget
from .common import create_font


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
        self.window.db = self.window_initializer.db
        self.window.settings = self.window_initializer.settings
        self.window.theme_ctrl = self.window_initializer.theme_ctrl
        self.window.current_category_id = None
        self.window.thread_pool = LimitedThreadPool(max_threads=2)
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
        central.setFrameShape(getattr(QFrame.Shape, app_config.get_central_frame_shape()))
        self.window.setCentralWidget(central)
        
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(*app_config.get_main_layout_margins())
        self.main_layout.setSpacing(app_config.get_main_layout_spacing())
    
    def setup_top_panel(self):
        """Настройка верхней панели."""
        # Контейнер для панели с разделителем
        top_panel_container = QWidget()
        top_panel_container.setObjectName("topPanelContainer")
        top_panel_container.setSizePolicy(
            getattr(QSizePolicy.Policy, app_config.get_top_panel_size_policy()[0]),
            getattr(QSizePolicy.Policy, app_config.get_top_panel_size_policy()[1])
        )
        
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Горизонтальный разделитель
        h_line_top = QWidget()
        h_line_top.setProperty("class", "separator")
        container_layout.addWidget(h_line_top)
        
        # Создание top_bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(*app_config.get_top_bar_margins())
        top_bar.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.setup_top_bar_widgets(top_bar)
        
        # Настройка контейнера
        content_container = QWidget()
        content_container.setFixedHeight(app_config.get_top_panel_container_height())
        content_container.setLayout(top_bar)
        container_layout.addWidget(content_container, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        top_panel_container.setLayout(container_layout)
        self.main_layout.addWidget(top_panel_container)
        
        self.window.top_panel_container = top_panel_container
        self.window.content_container = content_container
    
    def setup_top_bar_widgets(self, top_bar):
        """Настройка виджетов верхней панели."""
            # Создание таблицы и настройка шрифта
        self.window.table = LinksTableView(self.window)
        font_size = self.settings.get_font_size() if hasattr(self.settings, 'get_font_size') else 12
        if hasattr(self.window.table, 'update_font_size'):
            self.window.table.update_font_size(font_size)
        
        # Стили фокуса применяются через тему - не захардкоживаем здесь
        
        # Отложенная инициализация виджетов
        self.window.recent_links_widget = None
        self.window.db_for_delayed_init = self.window_initializer.db
        
        # Разделители
        fav_quick_separator_before = QWidget()
        fav_quick_separator_before.setObjectName("favQuickSeparatorBefore")
        fav_quick_separator_before.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        top_bar.addWidget(fav_quick_separator_before)
        
        self.window.fav_widget = None
        def initialize_delayed_widgets():
            from .delayed_widgets_initializer import DelayedWidgetsInitializer
            initializer = DelayedWidgetsInitializer(self.window)
            initializer.initialize_delayed_widgets()
        
        self.window.shown.connect(initialize_delayed_widgets)
        
        fav_quick_separator = QWidget()
        fav_quick_separator.setObjectName("favQuickSeparatorAfter")
        fav_quick_separator.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        top_bar.addWidget(fav_quick_separator)
        
        # Панель быстрых кнопок - создается позже в WindowControllersSetup после создания контроллеров
        # Оставляем место для QuickAddWidget
        self.window.quick_add_widget = None
        
        # Поле поиска
        self.setup_search_widget(top_bar)
    
    def setup_search_widget(self, top_bar):
        """Настройка поля поиска."""
        self.window.search = QLineEdit()
        self.window.search.setPlaceholderText(app_config.get_search_placeholder())
        self.window.search.setClearButtonEnabled(True)
        self.window.search.setFixedHeight(32)
        # Разрешаем горизонтальное сжатие/растяжение
        self.window.search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.window.search.setObjectName('mainSearch')
        
        self.window.search.setFont(create_font(11))
        self.window.search.textChanged.connect(self.window.on_search)
        top_bar.addWidget(self.window.search)
    
    def setup_main_content(self):
        """Настройка основного содержимого."""
        # Горизонтальный разделитель
        h_line_top = QWidget()
        h_line_top.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_top)
        
        mid = QHBoxLayout()
        mid.setContentsMargins(*app_config.get_layout_margins('mid'))
        
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
        left_layout.setContentsMargins(*app_config.get_layout_margins('left'))
        
        # Дерево структуры
        self.window.tree = StructureTreeWidget()
        self.window.tree.setHeaderHidden(True)
        tree_icon_size = app_config.get_tree_icon_size()
        icon_size = tree_icon_size[0] if isinstance(tree_icon_size, list) else tree_icon_size
        from PyQt6 import QtCore
        self.window.tree.setIconSize(QtCore.QSize(icon_size, icon_size))
        
        font_size = self.settings.get_font_size() if hasattr(self.settings, 'get_font_size') else 12
        if hasattr(self.window.tree, 'update_font_size'):
            self.window.tree.update_font_size(font_size)
        left_layout.addWidget(self.window.tree)
        
        # Панель сфер
        self.setup_spheres_bar(left_layout)
    
    def setup_spheres_bar(self, left_layout):
        """Настройка панели сфер."""
        self.window.spheres_bar = QWidget()
        self.window.spheres_bar.setObjectName("spheres_bar")
        self.window.spheres_bar.setMinimumHeight(app_config.get('ui.layout.spheres_bar.min_height', 40))
        
        s_layout = QHBoxLayout(self.window.spheres_bar)
        s_layout.setContentsMargins(*app_config.get_layout_margins('spheres'))
        s_layout.setSpacing(app_config.get('ui.layout.spacing.spheres_bar', 4))
        self.window.sphere_group = QButtonGroup(self.window)
        
        left_layout.addWidget(self.window.spheres_bar)
    
    def setup_right_panel(self, mid):
        """Настройка правой панели."""
        # Плитки категорий - создаем без зависимостей, инжектируем позже
        self.window.tiles = CategoryTiles(parent=None)
        
        # ЦЕНТРАЛИЗОВАНО: Подключение к UIStateManager
        self.window.tiles.category_selected.connect(
            lambda cat_id: self.window.ui_state.load_category(cat_id, source="CategoryTiles")
        )
        
        self.window.tiles_scroll = QScrollArea()
        self.window.tiles_scroll.setWidgetResizable(True)
        self.window.tiles_scroll.setWidget(self.window.tiles)
        
        tiles_wrapper = QWidget()
        tiles_layout = QVBoxLayout(tiles_wrapper)
        tiles_layout.setContentsMargins(*app_config.get_layout_margins('tiles'))
        tiles_layout.setSpacing(app_config.get('ui.layout.spacing.tiles', 0))
        tiles_layout.addWidget(self.window.tiles_scroll)
        
        # Обертка для таблицы
        table_wrapper = QWidget()
        table_layout = QVBoxLayout(table_wrapper)
        table_layout.setContentsMargins(*app_config.get_layout_margins('table'))
        table_layout.setSpacing(app_config.get('ui.layout.spacing.table', 4))
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
        self.window.splitter.addWidget(self.window.left_panel)
        self.window.splitter.addWidget(right_panel)
        
        stretch_factors = app_config.get('ui.layout.splitter.stretch_factors', [1, 3])
        self.window.splitter.setStretchFactor(0, stretch_factors[0])
        self.window.splitter.setStretchFactor(1, stretch_factors[1])
        
        mid.addWidget(self.window.splitter)
        
        splitter_sizes = app_config.get('ui.layout.splitter.sizes', [200, 600])
        self.window.splitter.setSizes(splitter_sizes)
        self.window._first_structure_load = True
        
        # QStackedLayout ломает стандартную Tab-навигацию Qt
        # Используем кастомную обработку через NavigationKeyHandler
        # Никаких setTabOrder - только динамическое управление фокусом
        
        # Установить нижней панели NoFocus policy чтобы исключить из Tab
        if hasattr(self.window, 'bottom_bar_container'):
            self.window.bottom_bar_container.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    
    def setup_bottom_panel(self):
        """Настройка нижней панели."""
        bot = QHBoxLayout()
        bot.setContentsMargins(*app_config.get_layout_margins('bottom'))
        
        font10 = QFont()
        font10.setPointSize(11)
        
        # Кнопка переключения сфер (будет создана после инициализации контроллеров)
        self.window.switch_sphere_button = None
        
        # Дополнительные кнопки из конфигурации
        bottom_actions = app_config.get('ui.bottom_actions', [])
        for text, fn_name in bottom_actions:
            btn = QPushButton(text)
            btn.setFont(font10)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(getattr(self.window, fn_name))
            bot.addWidget(btn)
        
        bottom_bar_container = QWidget()
        bottom_bar_container.setObjectName("bottomBarContainer")
        bottom_bar_container.setLayout(bot)
        bottom_bar_container.setSizePolicy(
            getattr(QSizePolicy.Policy, app_config.get_top_panel_size_policy()[0]),
            getattr(QSizePolicy.Policy, app_config.get_top_panel_size_policy()[1])
        )
        
        self.main_layout.addWidget(bottom_bar_container)
        
        # Разделитель под нижней панелью
        h_line_bottom = QWidget()
        h_line_bottom.setProperty("class", "separator")
        self.main_layout.addWidget(h_line_bottom)
    
    def setup_status_bar(self):
        """Настройка статус-бара."""
        status = QStatusBar(self.window)
        self.window.setStatusBar(status)
        
        self.window.db_status_label = QLabel(app_config.get('ui.db_connected_text', 'DB: Connected'))
        self.window.path_label = QLabel("")
        self.window.path_label.setObjectName("pathLabel")
        self.window.path_label.setMinimumWidth(app_config.get('ui.path_label_min_width', 350))
        self.window.links_count_label = QLabel(app_config.get('ui.links_count_text', 'Ссылок: 0'))
        
        status.addPermanentWidget(self.window.db_status_label)
        status.addPermanentWidget(self.window.path_label)
        status.addPermanentWidget(self.window.links_count_label)
        status.showMessage(app_config.get('ui.status_ready_text', 'Готово'))
    
    def setup_shortcuts(self):
        """Настройка горячих клавиш."""
        # Горячие клавиши теперь управляются централизованно через KeyboardManager
        # в WindowControllersSetup.setup_keyboard_manager()
        pass
    
    def setup_window_properties(self):
        """Настройка базовых свойств окна."""
        self.window.setWindowTitle(app_config.get_main_window_title())
        self.window.resize(*app_config.get_main_window_size())
        
        # Настройка иконки
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_path, "resources", "logo", "logo.png")
        self.window.setWindowIcon(create_icon_from_path(logo_path))
