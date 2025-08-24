"""
Главный загрузчик конфигурации приложения.
Объединяет все специализированные конфигурационные модули.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .limits_config import LimitsConfig
from .path_config import PathConfig
from .settings_config import SettingsConfig
from .ui_config import UIConfig
from .utils import get_by_path


class AppConfig:
    """Управление конфигурацией приложения из JSON файла."""

    def __init__(self, config_path: Optional[str] = None):
        """Инициализация загрузчика конфигурации."""
        if config_path is None:
            config_path = Path(__file__).parent / "app_config.json"
        self._config_path = Path(config_path)
        self._config = self._load_config()

        # Инициализация специализированных конфигураций
        self.ui = UIConfig(self._config)
        self.paths = PathConfig(self._config)
        self.limits = LimitsConfig(self._config)
        self.settings = SettingsConfig(self._config)

    def _load_config(self) -> Dict[str, Any]:
        """Загрузка конфигурации из JSON файла."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"Файл конфигурации не найден: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Получение значения из конфигурации по пути к ключу."""
        return get_by_path(self._config, key_path, default)

    def get_full_config(self) -> Dict[str, Any]:
        """Получение полной конфигурации."""
        return self._config.copy()

    # === МЕТОДЫ ОБРАТНОЙ СОВМЕСТИМОСТИ ===
    # Все старые методы делегируются к соответствующим модулям

    # === Основные настройки приложения ===

    def get_app_name(self) -> str:
        """Получение названия приложения."""
        return self.settings.get_app_name()

    def get_org_name(self) -> str:
        """Получение названия организации."""
        return self.settings.get_org_name()

    def get_app_version(self) -> str:
        """Получение версии приложения."""
        return self.settings.get_app_version()

    def is_debug_mode(self) -> bool:
        """Получение признака режима отладки."""
        return self.settings.is_debug_mode()

    def get_log_level(self) -> str:
        """Получение уровня логирования."""
        return self.settings.get_log_level()

    def get_max_backups(self) -> int:
        """Получение максимального количества резервных копий базы данных."""
        return self.settings.get_max_backups()

    def is_backup_enabled(self) -> bool:
        """Получение признака включения резервного копирования."""
        return self.settings.is_backup_enabled()

    def get_about_title(self) -> str:
        """Получение заголовка диалога 'О программе'."""
        return self.settings.get_about_title()

    def get_about_text(self) -> str:
        """Получение текста диалога 'О программе'."""
        return self.settings.get_about_text()

    # === UI параметры ===

    def get_default_font_size(self) -> int:
        """Получение размера шрифта по умолчанию."""
        return self.ui.get_default_font_size()

    def get_default_icon_size(self) -> int:
        """Получение размера иконки по умолчанию."""
        return self.ui.get_default_icon_size()

    def get_window_width(self) -> int:
        """Получение ширины окна приложения."""
        return self.ui.get_window_width()

    def get_window_height(self) -> int:
        """Получение высоты окна приложения."""
        return self.ui.get_window_height()

    def get_window_min_width(self) -> int:
        """Получение минимальной ширины окна приложения."""
        return self.ui.get_window_min_width()

    def get_window_min_height(self) -> int:
        """Получение минимальной высоты окна приложения."""
        return self.ui.get_window_min_height()

    def get_icon_size(self) -> Any:
        """Получение размера иконок в таблице ссылок."""
        return self.ui.get_icon_size()

    def get_row_height(self) -> int:
        """Получение высоты строки в таблице ссылок."""
        return self.ui.get_row_height()

    def get_col_widths(self) -> list:
        """Получение ширин колонок таблицы."""
        return self.ui.get_col_widths()

    def get_max_favorites(self) -> int:
        """Получение максимального количества избранных ссылок."""
        return self.ui.get_max_favorites()

    def get_fixed_button_width(self) -> int:
        """Получение фиксированной ширины стандартных кнопок."""
        return self.ui.get_fixed_button_width()

    def get_tile_size(self) -> list:
        """Получение размера плитки категорий."""
        return self.ui.get_tile_size()

    def get_tile_icon_size(self) -> list:
        """Получение размера иконки на плитке категорий."""
        return self.ui.get_tile_icon_size()

    def get_tile_spacing(self) -> int:
        """Получение расстояния между плитками категорий."""
        return self.ui.get_tile_spacing()

    def get_tile_padding(self) -> int:
        """Получение внутренних отступов внутри плитки."""
        return self.ui.get_tile_padding()

    def get_tile_icon_text_gap(self) -> int:
        """Получение расстояния между иконкой и текстом на плитке."""
        return self.ui.get_tile_icon_text_gap()

    def get_tile_text_font_size(self) -> int:
        """Получение размера шрифта текста на плитке."""
        return self.ui.get_tile_text_font_size()

    def get_tile_text_max_lines(self) -> int:
        """Получение максимального количества строк текста на плитке."""
        return self.ui.get_tile_text_max_lines()

    def get_tile_columns(self) -> int:
        """Получение количества колонок плиток категорий."""
        return self.ui.get_tile_columns()

    def get_tile_margins(self) -> list:
        """Получение отступов плиток категорий."""
        return self.ui.get_tile_margins()

    def get_spheres_bar_height(self) -> int:
        """Получение высоты панели сфер."""
        return self.ui.get_spheres_bar_height()

    def get_spheres_bar_min_height(self) -> int:
        """Получение минимальной высоты панели сфер."""
        return self.ui.get_spheres_bar_min_height()

    def get_spheres_bar_spacing(self) -> int:
        """Получение расстояния между элементами на панели сфер."""
        return self.ui.get_spheres_bar_spacing()

    def get_spheres_bar_margins(self) -> tuple:
        """Получение отступов панели сфер (с учётом переопределений слева/справа)."""
        return self.ui.get_spheres_bar_margins()

    def get_tiles_layout_margins(self) -> list:
        """Получение отступов в layout плиток."""
        return self.ui.get_tiles_layout_margins()

    def get_quick_add_button_size(self) -> list:
        """Получение размера кнопок быстрого доступа."""
        return self.ui.get_quick_add_button_size()

    def get_tree_icon_size(self) -> list:
        """Получение размера иконок в дереве структуры."""
        return self.ui.get_tree_icon_size()

    def get_splitter_handle_width(self) -> int:
        """Получение ширины разделителя в сплиттере."""
        return self.ui.get_splitter_handle_width()

    def get_splitter_stretch_factors(self) -> list:
        """Получение коэффициентов растяжения панелей в сплиттере."""
        return self.ui.get_splitter_stretch_factors()

    def get_splitter_sizes(self) -> list:
        """Получение начальных размеров панелей сплиттера."""
        return self.ui.get_splitter_sizes()

    def get_central_frame_shape(self) -> str:
        """Получение стиля рамки центрального фрейма."""
        return self.ui.get_central_frame_shape()

    def get_top_panel_size_policy(self) -> list:
        """Получение политики размеров верхней панели."""
        return self.ui.get_top_panel_size_policy()

    def get_top_panel_container_height(self) -> int:
        """Получение высоты контейнера верхней панели."""
        return self.ui.get_top_panel_container_height()

    def get_top_panel_search_width(self) -> int:
        """Получение ширины поля поиска в верхней панели."""
        return self.ui.get_top_panel_search_width()

    def get_stack_index_tiles(self) -> int:
        """Получение индекса стека для отображения плиток."""
        return self.ui.get_stack_index_tiles()

    def get_stack_index_table(self) -> int:
        """Получение индекса стека для отображения таблицы."""
        return self.ui.get_stack_index_table()

    def get_table_selection_restore_delay(self) -> int:
        """Получение задержки восстановления выделения в таблице."""
        return self.ui.get_table_selection_restore_delay()

    def get_thread_pool_shutdown_timeout(self) -> int:
        """Получение таймаута завершения потоков при выключении."""
        return self.ui.get_thread_pool_shutdown_timeout()

    def get_delete_confirm_title(self) -> str:
        """Получение заголовка диалога подтверждения удаления."""
        return self.ui.get_delete_confirm_title()

    def get_delete_confirm_text(self) -> str:
        """Получение текста диалога подтверждения удаления."""
        return self.ui.get_delete_confirm_text()

    def get_yes_text(self) -> str:
        """Получение текста кнопки 'Да'."""
        return self.ui.get_yes_text()

    def get_no_text(self) -> str:
        """Получение текста кнопки 'Нет'."""
        return self.ui.get_no_text()

    def get_bottom_actions(self) -> list:
        """Получение списка действий на нижней панели."""
        return self.ui.get_bottom_actions()

    def get_links_table_headers(self) -> list:
        """Получение заголовков колонок таблицы ссылок."""
        return self.ui.get_links_table_headers()

    def get_layout_margins(self, margin_type: str) -> tuple[int, int, int, int]:
        """Получение отступов для указанного типа layout."""
        return self.ui.get_layout_margins(margin_type)

    def get_sphere_button_icon_size(self) -> Any:
        """Получение размера иконки кнопки сферы."""
        return self.ui.get_sphere_button_icon_size()

    def get_tile_width(self) -> int:
        """Получение ширины плитки категории."""
        return self.ui.get_tile_width()

    def get_tile_height(self) -> int:
        """Получение высоты плитки категории."""
        return self.ui.get_tile_height()

    def get_tile_border_radius(self) -> int:
        """Получение радиуса скругления углов плитки."""
        return self.ui.get_tile_border_radius()

    def get_tile_border_width(self) -> int:
        """Получение толщины границы плитки."""
        return self.ui.get_tile_border_width()

    def get_tile_border_margin(self) -> int:
        """Получение отступа для границы плитки."""
        return self.ui.get_tile_border_margin()

    def get_main_window_title(self) -> str:
        """Получение заголовка главного окна приложения."""
        return self.ui.get_main_window_title()

    def get_search_placeholder(self) -> str:
        """Получение текста-заполнителя в поле поиска."""
        return self.ui.get_search_placeholder()

    def get_main_window_size(self) -> tuple:
        """Получение размеров главного окна при запуске."""
        return self.ui.get_main_window_size()

    def get_qss_path(self) -> str:
        """Получение пути к файлу темы оформления по умолчанию."""
        return self.ui.get_qss_path()

    def get_top_bar_margins(self) -> tuple:
        """Получение отступов верхней панели."""
        return self.ui.get_top_bar_margins()

    def get_top_bar_spacing(self) -> int:
        """Получение расстояния между элементами верхней панели."""
        return self.ui.get_top_bar_spacing()

    def get_top_bar_buttons_spacing(self) -> int:
        """Внутренний spacing между кнопками в панелях топ-бара."""
        return self.ui.get_top_bar_buttons_spacing()

    def get_top_bar_widgets_side_spacing(self) -> int:
        """Боковой отступ с каждой стороны для виджетов топ-бара (между соседями = 2*side)."""
        return self.ui.get_top_bar_widgets_side_spacing()

    def get_link_dialog_width(self) -> int:
        """Получение ширины диалога добавления/редактирования ссылки."""
        return self.ui.get_link_dialog_width()

    def get_link_dialog_height(self) -> int:
        """Получение высоты диалога добавления/редактирования ссылки."""
        return self.ui.get_link_dialog_height()

    def get_link_dialog_margins(self) -> int:
        """Получение отступов в диалоге ссылок."""
        return self.ui.get_link_dialog_margins()

    def get_link_dialog_spacing(self) -> int:
        """Получение расстояния между элементами в диалоге ссылок."""
        return self.ui.get_link_dialog_spacing()

    def get_main_layout_margins(self) -> tuple:
        """Получение отступов главного layout."""
        return self.ui.get_main_layout_margins()

    def get_main_layout_spacing(self) -> int:
        """Получение расстояния между элементами в главном layout."""
        return self.ui.get_main_layout_spacing()

    def get_mid_layout_margins(self) -> tuple:
        """Получение отступов среднего layout."""
        return self.ui.get_mid_layout_margins()

    def get_left_layout_margins(self) -> tuple:
        """Получение отступов левого layout."""
        return self.ui.get_left_layout_margins()

    def get_table_layout_margins(self) -> tuple:
        """Получение отступов таблицы layout."""
        return self.ui.get_table_layout_margins()

    def get_table_layout_spacing(self) -> int:
        """Получение расстояния между элементами в таблице layout."""
        return self.ui.get_table_layout_spacing()

    def get_bottom_layout_margins(self) -> tuple:
        """Получение отступов нижнего layout."""
        return self.ui.get_bottom_layout_margins()

    def get_spheres_layout_margins(self) -> tuple:
        """Получение отступов layout сфер."""
        return self.ui.get_spheres_layout_margins()

    def get_macro_add_links_text(self) -> str:
        """Получение текста для макроса добавления ссылок."""
        return self.ui.get_macro_add_links_text()

    def get_macro_delete_links_text(self) -> str:
        """Получение текста для макроса удаления ссылок."""
        return self.ui.get_macro_delete_links_text()

    def get_db_connected_text(self) -> str:
        """Получение текста статуса подключения к БД."""
        return self.ui.get_db_connected_text()

    def get_db_disconnected_text(self) -> str:
        """Получение текста статуса отключения от БД."""
        return self.ui.get_db_disconnected_text()

    def get_links_count_text(self) -> str:
        """Получение текста количества ссылок."""
        return self.ui.get_links_count_text()

    def get_status_ready_text(self) -> str:
        """Получение текста статуса 'Готово'."""
        return self.ui.get_status_ready_text()

    def get_path_label_min_width(self) -> int:
        """Получение минимальной ширины метки пути."""
        return self.ui.get_path_label_min_width()

    def get_powershell_path(self) -> str:
        """Получение пути к PowerShell."""
        return self.ui.get_powershell_path()

    def get_favorite_icon_size(self) -> int:
        """Получение размера иконок избранного."""
        return self.ui.get_favorite_icon_size()

    def get_top_panel_button_size(self) -> int:
        """Единый размер для ВСЕХ кнопок в топпанели."""
        return self.ui.get_top_panel_button_size()

    def get_top_panel_icon_size(self) -> Any:
        """Единый размер иконок для ВСЕХ кнопок в топпанели."""
        return self.ui.get_top_panel_icon_size()

    def get_menu_font_size(self) -> int:
        """Получение размера шрифта меню."""
        return self.ui.get_menu_font_size()

    def get_menubar_font_size(self) -> int:
        """Получение размера шрифта панели меню."""
        return self.ui.get_menubar_font_size()

    def get_menubar_item_height(self) -> int:
        """Получение высоты элементов панели меню."""
        return self.ui.get_menubar_item_height()

    def get_menu_icon_size(self) -> int:
        """Получение размера иконок в меню."""
        return self.ui.get_menu_icon_size()

    def get_menu_indicator_size(self) -> int:
        """Получение размера индикаторов в меню."""
        return self.ui.get_menu_indicator_size()

    def get_scrollbar_width(self) -> int:
        """Получение ширины вертикального скроллбара."""
        return self.ui.get_scrollbar_width()

    def get_scrollbar_height(self) -> int:
        """Получение высоты горизонтального скроллбара."""
        return self.ui.get_scrollbar_height()

    def get_tree_item_height(self) -> int:
        """Получение высоты элементов дерева."""
        return self.ui.get_tree_item_height()

    def get_table_item_height(self) -> int:
        """Получение высоты элементов таблицы."""
        return self.ui.get_table_item_height()

    def get_separator_height(self) -> int:
        """Получение высоты разделителей."""
        return self.ui.get_separator_height()

    def get_separator_width(self) -> int:
        """Получение толщины (ширины) вертикальных разделителей."""
        return self.ui.get_separator_width()

    # === Пути ===

    def get_base_path(self):
        """Получение базового пути приложения."""
        return self.paths.get_base_path()

    def get_ui_icons_dir(self):
        """Получение пути к директории с иконками интерфейса."""
        return self.paths.get_ui_icons_dir()

    def get_db_path(self):
        """Получение пути к файлу базы данных."""
        return self.paths.get_db_path()

    def get_link_icons_dir(self):
        """Получение пути к директории с иконками ссылок."""
        return self.paths.get_link_icons_dir()

    def get_ui_icons_path(self) -> str:
        """Возвращает путь к UI-иконкам как строку."""
        return str(self.paths.get_ui_icons_dir())

    def get_qss_dir(self):
        """Получение пути к директории с QSS темами как объект Path."""
        return self.paths.get_qss_dir()

    def get_themes_manifest_path(self):
        """Получение пути к файлу манифеста тем оформления."""
        return self.paths.get_themes_manifest_path()

    def get_chrome_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Chrome."""
        p = self.paths.get_chrome_profiles_dir()
        return str(p) if p else None

    def get_firefox_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Firefox."""
        p = self.paths.get_firefox_profiles_dir()
        return str(p) if p else None

    def get_edge_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Edge."""
        p = self.paths.get_edge_profiles_dir()
        return str(p) if p else None

    def get_brave_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Brave."""
        p = self.paths.get_brave_profiles_dir()
        return str(p) if p else None

    def get_vivaldi_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Vivaldi."""
        p = self.paths.get_vivaldi_profiles_dir()
        return str(p) if p else None

    def get_opera_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Opera."""
        p = self.paths.get_opera_profiles_dir()
        return str(p) if p else None

    def get_yandex_profiles_dir(self) -> Optional[str]:
        """Получение пути к директории профилей Yandex."""
        p = self.paths.get_yandex_profiles_dir()
        return str(p) if p else None

    # === Лимиты ===

    def get_max_icon_size(self) -> int:
        """Получение максимального размера файлов иконок."""
        return self.limits.get_max_icon_size()

    def get_max_web_icon_size(self) -> int:
        """Получение максимального размера веб-иконок."""
        return self.limits.get_max_web_icon_size()

    def get_icon_cache_size(self) -> int:
        """Получение размера кэша иконок."""
        return self.limits.get_icon_cache_size()

    def get_icon_cache_ttl(self) -> int:
        """Получение времени жизни кэша иконок в секундах."""
        return self.limits.get_icon_cache_ttl()

    def get_negative_cache_ttl(self) -> int:
        """Получение времени жизни негативного кэша в секундах."""
        return self.limits.get_negative_cache_ttl()

    def get_abs_icon_cache_ttl(self) -> int:
        """Получение времени жизни кэша иконок по абсолютным путям в секундах."""
        return self.limits.get_abs_icon_cache_ttl()

    # === Настройки ===

    def get_supported_icon_formats(self) -> list:
        """Получение списка поддерживаемых форматов файлов иконок."""
        return self.settings.get_supported_icon_formats()

    def get_valid_themes(self) -> list:
        """Получение списка допустимых тем оформления."""
        return self.settings.get_valid_themes()

    def get_link_types(self) -> list:
        """Получение справочника поддерживаемых типов ссылок."""
        return self.settings.get_link_types()

    def get_default_icons(self) -> dict:
        """Получение иконок по умолчанию для различных типов элементов."""
        return self.settings.get_default_icons()

    def get_quick_types(self) -> list:
        """Получение списка быстрых типов ссылок."""
        return self.settings.get_quick_types()

    def get_quick_type_tooltips(self) -> dict:
        """Получение подсказок для быстрых типов ссылок."""
        return self.settings.get_quick_type_tooltips()

    def get_default_browse_paths(self) -> dict:
        """Получение путей по умолчанию для диалогов выбора файлов/папок."""
        return self.settings.get_default_browse_paths()

    def get_browser_profile_settings(self) -> dict:
        """Получение настроек профилей браузеров."""
        return self.settings.get_browser_profile_settings()

    def get_supported_browsers(self) -> list:
        """Получение списка поддерживаемых браузеров."""
        return self.settings.get_supported_browsers()

    def get_browser_config(self) -> dict:
        """Получение конфигурации браузеров для текущей ОС."""
        return self.settings.get_browser_config()

    def get_mime_types(self) -> dict:
        """Получение MIME-типов приложения."""
        return self.settings.get_mime_types()

    def get_link_mime_type(self) -> str:
        """Получение MIME-типа для ссылок."""
        return self.settings.get_link_mime_type()

    def get_category_mime_type(self) -> str:
        """Получение MIME-типа для категорий."""
        return self.settings.get_category_mime_type()
