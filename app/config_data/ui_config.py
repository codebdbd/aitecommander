"""
Конфигурация пользовательского интерфейса.
"""
from typing import Any, Dict, List, Tuple

from .base_config import BaseConfig


class UIConfig(BaseConfig):
    """Конфигурация параметров пользовательского интерфейса."""
    
    # === Основные UI параметры ===
    
    def get_default_font_size(self) -> int:
        """Получение размера шрифта по умолчанию."""
        return self.get("ui.default_font_size", 12)

    def get_default_icon_size(self) -> int:
        """Получение размера иконки по умолчанию."""
        return self.get("ui.default_icon_size", 24)
    
    # === Окно приложения ===
    
    def get_window_width(self) -> int:
        """Получение ширины окна приложения."""
        return self.get("ui.window.width", 1200)
    
    def get_window_height(self) -> int:
        """Получение высоты окна приложения."""
        return self.get("ui.window.height", 800)
    
    def get_window_min_width(self) -> int:
        """Получение минимальной ширины окна приложения."""
        return self.get("ui.window.min_width", 800)
    
    def get_window_min_height(self) -> int:
        """Получение минимальной высоты окна приложения."""
        return self.get("ui.window.min_height", 600)
    
    def get_main_window_title(self) -> str:
        """Получение заголовка главного окна приложения."""
        return self.get("ui.window.title", "Aite Commander")
    
    def get_main_window_size(self) -> tuple:
        """Получение размеров главного окна при запуске."""
        width = self.get("ui.window.width", 1000)
        height = self.get("ui.window.height", 600)
        return (width, height)
    
    # === Иконки и размеры ===
    
    def get_icon_size(self) -> 'QSize':
        """Получение размера иконок в таблице ссылок."""
        from PyQt6.QtCore import QSize
        size = self.get("ui.icon_size", 24)
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return QSize(size[0], size[1])
        return QSize(size, size)

    def get_row_height(self) -> int:
        """Получение высоты строки в таблице ссылок."""
        return self.get("ui.row_height", 30)

    def get_col_widths(self) -> list:
        """Получение ширин колонок таблицы."""
        return self.get("ui.col_widths", [40, 280, 130])

    def get_max_favorites(self) -> int:
        """Получение максимального количества избранных ссылок."""
        return self.get("ui.max_favorites", 20)

    def get_link_table_headers(self) -> list:
        """Получение заголовков колонок таблицы ссылок."""
        return self.get("ui.link_table_headers", ["★", "Название", "Последний запуск", "Заметки"])

    def get_fixed_button_width(self) -> int:
        """Получение фиксированной ширины стандартных кнопок."""
        return self.get("ui.fixed_button_width", 100)
    
    # === Плитки категорий ===

    def get_tile_size(self) -> list:
        """Получение размера плитки категорий."""
        return self.get("ui.tile_size", [120, 120])

    def get_tile_icon_size(self) -> list:
        """Получение размера иконки на плитке категорий."""
        return self.get("ui.tile_icon_size", [64, 64])

    def get_tile_spacing(self) -> int:
        """Получение расстояния между плитками категорий."""
        return self.get("ui.tile_spacing", 12)

    def get_tile_padding(self) -> int:
        """Получение внутренних отступов внутри плитки."""
        return self.get("ui.tile_padding", 10)

    def get_tile_icon_text_gap(self) -> int:
        """Получение расстояния между иконкой и текстом на плитке."""
        return self.get("ui.tile_icon_text_gap", 5)

    def get_tile_text_font_size(self) -> int:
        """Получение размера шрифта текста на плитке."""
        return self.get("ui.tile_text_font_size", 10)

    def get_tile_text_max_lines(self) -> int:
        """Получение максимального количества строк текста на плитке."""
        return self.get("ui.tile_text_max_lines", 4)

    def get_tile_columns(self) -> int:
        """Получение количества колонок плиток категорий."""
        return self.get("ui.tile_columns", 6)

    def get_tile_margins(self) -> list:
        """Получение отступов плиток категорий."""
        return self.get("ui.tile_margins", [20, 20, 20, 20])
    
    def get_tile_width(self) -> int:
        """Получение ширины плитки категории."""
        return self.get("ui.tile_width", 110)

    def get_tile_height(self) -> int:
        """Получение высоты плитки категории."""
        return self.get("ui.tile_height", 110)

    def get_tile_border_radius(self) -> int:
        """Получение радиуса скругления углов плитки."""
        return self.get("ui.tile_border_radius", 8)

    def get_tile_border_width(self) -> int:
        """Получение толщины границы плитки."""
        return self.get("ui.tile_border_width", 2)

    def get_tile_border_margin(self) -> int:
        """Получение отступа для границы плитки."""
        return self.get("ui.tile_border_margin", 2)
    
    # === Панель сфер ===

    def get_spheres_bar_height(self) -> int:
        """Получение высоты панели сфер."""
        return self.get("ui.spheres_bar_height", 48)

    def get_spheres_bar_min_height(self) -> int:
        """Получение минимальной высоты панели сфер."""
        return self.get("ui.spheres_bar_min_height", 64)

    def get_spheres_bar_spacing(self) -> int:
        """Получение расстояния между элементами на панели сфер."""
        return self.get("ui.spheres_bar_spacing", 12)
    
    def get_sphere_button_icon_size(self) -> 'QSize':
        """Получение размера иконки кнопки сферы."""
        from PyQt6.QtCore import QSize

        # Запрашиваем размер больше для качественного уменьшения Qt
        size = self.get("ui.sphere_button_icon_size", 64)  # Увеличено с 48 до 64
        return QSize(size, size)
    
    # === Топпанель ===

    def get_tiles_layout_margins(self) -> list:
        """Получение отступов в layout плиток."""
        return self.get("ui.tiles_layout_margins", [0, 0, 0, 0])

    def get_quick_add_button_size(self) -> list:
        """Получение размера кнопок быстрого доступа."""
        return self.get("ui.quick_add_button_size", [32, 32])
    
    def get_top_panel_button_size(self) -> int:
        """Единый размер для ВСЕХ кнопок в топпанели."""
        return self.get("ui.top_panel_button_size", 36)

    def get_top_panel_icon_size(self) -> 'QSize':
        """Единый размер иконок для ВСЕХ кнопок в топпанели."""
        from PyQt6.QtCore import QSize
        size = self.get("ui.top_panel_icon_size", 32)
        return QSize(size, size)
    
    # === Дерево структуры ===

    def get_tree_icon_size(self) -> list:
        """Получение размера иконок в дереве структуры."""
        return self.get("ui.tree_icon_size", [28, 28])
    
    # === Сплиттер ===

    def get_splitter_handle_width(self) -> int:
        """Получение ширины разделителя в сплиттере."""
        return self.get("ui.splitter_handle_width", 1)

    def get_splitter_stretch_factors(self) -> list:
        """Получение коэффициентов растяжения панелей в сплиттере."""
        return self.get("ui.splitter_stretch_factors", [1, 3])

    def get_splitter_sizes(self) -> list:
        """Получение начальных размеров панелей сплиттера."""
        return self.get("ui.splitter_sizes", [250, 750])

    def get_central_frame_shape(self) -> str:
        """Получение стиля рамки центрального фрейма."""
        return self.get("ui.central_frame_shape", "StyledPanel")

    def get_top_panel_size_policy(self) -> list:
        """Получение политики размеров верхней панели."""
        return self.get("ui.top_panel_size_policy", ["Expanding", "Fixed"])

    def get_top_panel_container_height(self) -> int:
        """Получение высоты контейнера верхней панели."""
        return self.get("ui.top_panel_container_height", 48)

    def get_stack_index_tiles(self) -> int:
        """Получение индекса стека для отображения плиток."""
        return self.get("ui.stack_index_tiles", 0)

    def get_stack_index_table(self) -> int:
        """Получение индекса стека для отображения таблицы."""
        return self.get("ui.stack_index_table", 1)

    def get_table_selection_restore_delay(self) -> int:
        """Получение задержки восстановления выделения в таблице."""
        return self.get("ui.table_selection_restore_delay", 100)

    def get_thread_pool_shutdown_timeout(self) -> int:
        """Получение таймаута завершения потоков при выключении."""
        return self.get("ui.thread_pool_shutdown_timeout", 2000)
    
    # === Диалоги ===

    def get_delete_confirm_title(self) -> str:
        """Получение заголовка диалога подтверждения удаления."""
        return self.get("ui.delete_confirm_title", "Подтверждение удаления")

    def get_delete_confirm_text(self) -> str:
        """Получение текста диалога подтверждения удаления."""
        return self.get("ui.delete_confirm_text", "Вы уверены, что хотите удалить {count} ссылк(и/у)?")

    def get_yes_text(self) -> str:
        """Получение текста кнопки 'Да'."""
        return self.get("ui.yes_text", "Да")

    def get_no_text(self) -> str:
        """Получение текста кнопки 'Нет'."""
        return self.get("ui.no_text", "Нет")
    
    def get_link_dialog_width(self) -> int:
        """Получение ширины диалога добавления/редактирования ссылки."""
        return self.get("ui.link_dialog_width", 600)

    def get_link_dialog_height(self) -> int:
        """Получение высоты диалога добавления/редактирования ссылки."""
        return self.get("ui.link_dialog_height", 520)

    def get_link_dialog_margins(self) -> int:
        """Получение отступов в диалоге ссылок."""
        return self.get("ui.link_dialog_margins", 20)

    def get_link_dialog_spacing(self) -> int:
        """Получение расстояния между элементами в диалоге ссылок."""
        return self.get("ui.link_dialog_spacing", 10)
    
    # === Нижняя панель ===

    def get_bottom_actions(self) -> list:
        """Получение списка действий на нижней панели."""
        return self.get("ui.bottom_actions", [
            ["Добавить раздел (F3)", "show_section_dialog"],
            ["Добавить категорию (F4)", "show_category_dialog"],
            ["Добавить ссылку (F1)", "show_link_dialog"],
            ["Редактировать (F2)", "edit_current"],
            ["Удалить (Del)", "delete_current"]
        ])

    def get_links_table_headers(self) -> list:
        """Получение заголовков колонок таблицы ссылок."""
        return self.get("ui.links_table_headers", ["★", "Название", "Последний запуск", "Заметки"])
    
    def get_links_table_columns(self) -> Dict[str, int]:
        """Получение индексов колонок таблицы ссылок."""
        return self.get("ui.links_table_columns", {
            "favorite": 0, "name": 1, "last_used": 2, "notes": 3
        })
    
    def get_links_table_messages(self) -> Dict[str, str]:
        """Получение сообщений для UI таблицы ссылок."""
        return self.get("ui.links_table_messages", {
            "no_categories": "Нет доступных категорий. Создай категорию сначала.",
            "select_category": "Выберите категорию для вставки ссылки",
            "error_saving": "Ошибка сохранения заметки",
            "database_error": "Ошибка базы данных",
            "validation_error": "Ошибка валидации",
            "warning_title": "Предупреждение",
            "error_title": "Ошибка"
        })
    
    # === Отступы и расстояния ===
    
    def get_layout_margins(self, margin_type: str) -> tuple[int, int, int, int]:
        """Получение отступов для указанного типа layout."""
        margins = self.get(f"ui.layout.margins.{margin_type}")
        if margins and len(margins) == 4:
            return tuple(margins)
        default_margins = {
            'main': (0, 0, 0, 0),
            'mid': (0, 0, 0, 0),
            'left': (0, 0, 0, 0),
            'right': (0, 0, 0, 0),
            'bottom': (0, 0, 0, 0),
            'top': (0, 0, 0, 0)
        }
        return default_margins.get(margin_type, (0, 0, 0, 0))

    def get_top_bar_margins(self) -> tuple:
        """Получение отступов верхней панели."""
        margins = self.get("ui.top_bar_margins", [4, 4, 4, 4])
        return tuple(margins)

    def get_main_layout_margins(self) -> tuple:
        """Получение отступов главного layout."""
        margins = self.get("ui.main_layout_margins", [0, 0, 0, 0])
        return tuple(margins)

    def get_main_layout_spacing(self) -> int:
        """Получение расстояния между элементами в главном layout."""
        return self.get("ui.main_layout_spacing", 0)

    def get_mid_layout_margins(self) -> tuple:
        """Получение отступов среднего layout."""
        margins = self.get("ui.mid_layout_margins", [0, 0, 0, 0])
        return tuple(margins)

    def get_left_layout_margins(self) -> tuple:
        """Получение отступов левого layout."""
        margins = self.get("ui.left_layout_margins", [0, 0, 0, 0])
        return tuple(margins)

    def get_table_layout_margins(self) -> tuple:
        """Получение отступов таблицы layout."""
        margins = self.get("ui.table_layout_margins", [0, 0, 0, 0])
        return tuple(margins)

    def get_table_layout_spacing(self) -> int:
        """Получение расстояния между элементами в таблице layout."""
        return self.get("ui.table_layout_spacing", 6)

    def get_bottom_layout_margins(self) -> tuple:
        """Получение отступов нижнего layout."""
        margins = self.get("ui.bottom_layout_margins", [5, 5, 5, 5])
        return tuple(margins)

    def get_spheres_layout_margins(self) -> tuple:
        """Получение отступов layout сфер."""
        margins = self.get("ui.spheres_layout_margins", [5, 5, 5, 5])
        return tuple(margins)
    
    def get_spheres_bar_margins(self) -> tuple[int, int, int, int]:
        """Отступы панели сфер с возможной подменой левого/правого значений.
        Источники:
        - База: ui.spheres_layout_margins: [L, T, R, B] (по умолчанию [5,5,5,5])
        - Переопределения: ui.spheres_bar_margin_left, ui.spheres_bar_margin_right
        """
        base = list(self.get_spheres_layout_margins())
        left_override = self.get("ui.spheres_bar_margin_left")
        right_override = self.get("ui.spheres_bar_margin_right")
        if isinstance(left_override, int):
            base[0] = left_override
        if isinstance(right_override, int):
            base[2] = right_override
        return tuple(base)
    
    # === Поиск и интерфейс ===

    def get_search_placeholder(self) -> str:
        """Получение текста-заполнителя в поле поиска."""
        return self.get("ui.search_placeholder", "Поиск… (Ctrl+F)")

    def get_qss_path(self) -> str:
        """Получение пути к файлу темы оформления по умолчанию."""
        return self.get("ui.qss_path", "dark.qss")
    
    # === Макросы и статусы ===

    def get_macro_add_links_text(self) -> str:
        """Получение текста для макроса добавления ссылок."""
        return self.get("ui.macro_add_links_text", "Добавление {count} ссылок")

    def get_macro_delete_links_text(self) -> str:
        """Получение текста для макроса удаления ссылок."""
        return self.get("ui.macro_delete_links_text", "Удаление {count} ссылок")

    def get_db_connected_text(self) -> str:
        """Получение текста статуса подключения к БД."""
        return self.get("ui.db_connected_text", "DB: Connected")
    
    def get_db_disconnected_text(self) -> str:
        """Получение текста статуса отключения от БД."""
        return self.get("ui.db_disconnected_text", "DB: Disconnected")

    def get_links_count_text(self) -> str:
        """Получение текста количества ссылок."""
        return self.get("ui.links_count_text", "Ссылок: 0")

    def get_status_ready_text(self) -> str:
        """Получение текста статуса 'Готово'."""
        return self.get("ui.status_ready_text", "Готово")

    def get_path_label_min_width(self) -> int:
        """Получение минимальной ширины метки пути."""
        return self.get("ui.path_label_min_width", 350)

    def get_powershell_path(self) -> str:
        """Получение пути к PowerShell."""
        return self.get("ui.powershell_path", "pwsh.exe")

    def get_favorite_icon_size(self) -> int:
        """Получение размера иконок избранного."""
        return self.get("ui.favorite_icon_size", 24)
    
    # === Дополнительные UI параметры для устранения дублирования с QSS ===
    
    def get_menu_font_size(self) -> int:
        """Получение размера шрифта меню."""
        return self.get("ui.menu_font_size", 12)
    
    def get_menubar_font_size(self) -> int:
        """Получение размера шрифта панели меню."""
        return self.get("ui.menubar_font_size", 9)
    
    def get_menubar_item_height(self) -> int:
        """Получение высоты элементов панели меню."""
        return self.get("ui.menubar_item_height", 24)
    
    def get_menu_icon_size(self) -> int:
        """Получение размера иконок в меню."""
        return self.get("ui.menu_icon_size", 20)
    
    def get_menu_indicator_size(self) -> int:
        """Получение размера индикаторов в меню."""
        return self.get("ui.menu_indicator_size", 16)
    
    def get_scrollbar_width(self) -> int:
        """Получение ширины вертикального скроллбара."""
        return self.get("ui.scrollbar_width", 12)
    
    def get_scrollbar_height(self) -> int:
        """Получение высоты горизонтального скроллбара."""
        return self.get("ui.scrollbar_height", 12)
    
    def get_tree_item_height(self) -> int:
        """Получение высоты элементов дерева."""
        return self.get("ui.tree_item_height", 32)
    
    def get_table_item_height(self) -> int:
        """Получение высоты элементов таблицы.""" 
        return self.get("ui.table_item_height", 28)
    
    def get_separator_height(self) -> int:
        """Получение высоты разделителей."""
        return self.get("ui.separator_height", 24)
