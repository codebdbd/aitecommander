"""Система CSS-переменных для QSS стилей.

Централизует определение цветов и размеров для разных тем,
предотвращает дублирование и упрощает изменение дизайна.
"""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ColorPalette:
    """Палитра цветов для темы."""
    
    # Основные цвета фона
    bg_primary: str
    bg_secondary: str
    bg_tertiary: str
    bg_hover: str
    bg_selected: str
    bg_pressed: str
    
    # Цвета текста
    text_primary: str
    text_secondary: str
    text_disabled: str
    text_on_selected: str
    
    # Цвета границ
    border_light: str
    border_normal: str
    border_dark: str
    border_focus: str
    
    # Акцентные цвета
    accent_primary: str
    accent_hover: str
    accent_pressed: str
    
    # Статусные цвета
    success: str
    warning: str
    error: str
    info: str
    
    # Специальные цвета
    favorite_icon: str
    link_color: str
    separator: str
    shadow: str


@dataclass
class SizePalette:
    """Размеры элементов интерфейса."""
    
    # Радиусы скругления
    border_radius_sm: int = 4
    border_radius_md: int = 6
    border_radius_lg: int = 8
    
    # Толщина границ
    border_width_thin: int = 1
    border_width_normal: int = 2
    border_width_thick: int = 3
    
    # Размеры иконок
    icon_size_sm: int = 16
    icon_size_md: int = 24
    icon_size_lg: int = 32
    icon_size_xl: int = 48
    
    # Отступы
    padding_xs: int = 2
    padding_sm: int = 4
    padding_md: int = 8
    padding_lg: int = 12
    padding_xl: int = 16
    
    # Размеры шрифтов (px)
    font_size_sm: int = 10
    font_size_md: int = 11
    font_size_lg: int = 13
    font_size_xl: int = 14
    
    # Высота элементов
    button_height: int = 32
    input_height: int = 28
    menubar_height: int = 24
    tree_item_height: int = 32
    table_row_height: int = 28


# Определение светлой темы
LIGHT_PALETTE = ColorPalette(
    # Основные цвета фона
    bg_primary="#FFFFFF",
    bg_secondary="#F5F5F5",
    bg_tertiary="#ECECEC",
    bg_hover="#E0E0E0",
    bg_selected="#0078D7",
    bg_pressed="#005A9E",
    
    # Цвета текста
    text_primary="#000000",
    text_secondary="#666666",
    text_disabled="#999999",
    text_on_selected="#FFFFFF",
    
    # Цвета границ
    border_light="#E0E0E0",
    border_normal="#C0C0C0",
    border_dark="#A0A0A0",
    border_focus="#0078D7",
    
    # Акцентные цвета
    accent_primary="#0078D7",
    accent_hover="#005A9E",
    accent_pressed="#004578",
    
    # Статусные цвета
    success="#28A745",
    warning="#FFC107",
    error="#DC3545",
    info="#17A2B8",
    
    # Специальные цвета
    favorite_icon="#FFD700",
    link_color="#0078D7",
    separator="#DDDDDD",
    shadow="rgba(0, 0, 0, 0.1)",
)


# Определение тёмной темы
DARK_PALETTE = ColorPalette(
    # Основные цвета фона
    bg_primary="#2B2B2B",
    bg_secondary="#3C3C3C",
    bg_tertiary="#4D4D4D",
    bg_hover="#252D3A",
    bg_selected="#6A2E44",
    bg_pressed="#501F33",
    
    # Цвета текста
    text_primary="#FFFFFF",
    text_secondary="#B0B0B0",
    text_disabled="#707070",
    text_on_selected="#FFFFFF",
    
    # Цвета границ
    border_light="#404040",
    border_normal="#505050",
    border_dark="#606060",
    border_focus="#6A2E44",
    
    # Акцентные цвета
    accent_primary="#6A2E44",
    accent_hover="#8A4E64",
    accent_pressed="#4A1E34",
    
    # Статусные цвета
    success="#4CAF50",
    warning="#FF9800",
    error="#F44336",
    info="#2196F3",
    
    # Специальные цвета
    favorite_icon="#FFD700",
    link_color="#7AA3CC",
    separator="#404040",
    shadow="rgba(0, 0, 0, 0.3)",
)


class ThemeVariables:
    """Менеджер переменных темы для генерации QSS."""
    
    def __init__(self, theme: str = "dark", sizes: SizePalette = None):
        """Инициализирует переменные темы.
        
        Args:
            theme: Название темы ('light' или 'dark')
            sizes: Палитра размеров (опционально, используется по умолчанию)
        """
        self.theme = theme
        self.colors = DARK_PALETTE if theme == "dark" else LIGHT_PALETTE
        self.sizes = sizes or SizePalette()
    
    def get_all_variables(self) -> Dict[str, Any]:
        """Возвращает все переменные темы в виде словаря.
        
        Returns:
            Dict с ключами-плейсхолдерами и значениями для подстановки в QSS
            
        Example:
            >>> vars = theme.get_all_variables()
            >>> qss_template = "QWidget { background: {bg_primary}; }"
            >>> qss = qss_template.format(**vars)
        """
        variables = {}
        
        # Добавляем цвета
        for key, value in self.colors.__dict__.items():
            variables[key] = value
        
        # Добавляем размеры
        for key, value in self.sizes.__dict__.items():
            variables[key] = f"{value}px" if isinstance(value, int) else value
        
        return variables
    
    def apply_to_template(self, qss_template: str) -> str:
        """Применяет переменные к шаблону QSS.
        
        Args:
            qss_template: Строка QSS с плейсхолдерами {variable_name}
            
        Returns:
            str: QSS с подставленными значениями
            
        Example:
            >>> template = '''
            ... QMainWindow {
            ...     background-color: {bg_primary};
            ...     color: {text_primary};
            ... }
            ... QPushButton {
            ...     background-color: {accent_primary};
            ...     border-radius: {border_radius_md};
            ...     padding: {padding_md};
            ... }
            ... '''
            >>> theme = ThemeVariables('dark')
            >>> qss = theme.apply_to_template(template)
        """
        variables = self.get_all_variables()
        try:
            return qss_template.format(**variables)
        except KeyError as e:
            raise ValueError(f"Missing variable in QSS template: {e}")
    
    def switch_theme(self, theme: str) -> None:
        """Переключает тему.
        
        Args:
            theme: Новая тема ('light' или 'dark')
        """
        self.theme = theme
        self.colors = DARK_PALETTE if theme == "dark" else LIGHT_PALETTE


# Пример использования в QSS-файле:
QSS_TEMPLATE_EXAMPLE = """
/* Основные стили главного окна */
QMainWindow {
    background-color: {bg_primary};
    color: {text_primary};
}

/* Кнопки */
QPushButton {
    background-color: {accent_primary};
    color: {text_on_selected};
    border: {border_width_thin} solid {border_normal};
    border-radius: {border_radius_md};
    padding: {padding_md};
    font-size: {font_size_md};
}

QPushButton:hover {
    background-color: {accent_hover};
    border-color: {border_focus};
}

QPushButton:pressed {
    background-color: {accent_pressed};
}

QPushButton:disabled {
    background-color: {bg_secondary};
    color: {text_disabled};
}

/* Поля ввода */
QLineEdit, QTextEdit {
    background-color: {bg_secondary};
    color: {text_primary};
    border: {border_width_thin} solid {border_normal};
    border-radius: {border_radius_sm};
    padding: {padding_sm};
    selection-background-color: {bg_selected};
    selection-color: {text_on_selected};
}

QLineEdit:focus, QTextEdit:focus {
    border-color: {border_focus};
    border-width: {border_width_normal};
}

/* Таблицы */
QTableWidget {
    background-color: {bg_primary};
    alternate-background-color: {bg_secondary};
    gridline-color: {separator};
    selection-background-color: {bg_selected};
    selection-color: {text_on_selected};
}

QTableWidget::item {
    padding: {padding_sm};
    border: none;
}

QTableWidget::item:hover {
    background-color: {bg_hover};
}

/* Дерево */
QTreeWidget {
    background-color: {bg_primary};
    border: {border_width_thin} solid {border_light};
    selection-background-color: {bg_selected};
    selection-color: {text_on_selected};
}

QTreeWidget::item {
    height: {tree_item_height};
    padding: {padding_sm};
}

QTreeWidget::item:hover {
    background-color: {bg_hover};
}

/* Меню */
QMenuBar {
    background-color: {bg_primary};
    color: {text_primary};
    border-bottom: {border_width_thin} solid {separator};
}

QMenuBar::item:selected {
    background-color: {bg_hover};
}

QMenu {
    background-color: {bg_secondary};
    color: {text_primary};
    border: {border_width_thin} solid {border_normal};
}

QMenu::item:selected {
    background-color: {bg_selected};
    color: {text_on_selected};
}

/* Скроллбары */
QScrollBar:vertical {
    background: {bg_secondary};
    width: 12px;
    border-radius: {border_radius_sm};
}

QScrollBar::handle:vertical {
    background: {border_normal};
    border-radius: {border_radius_sm};
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: {border_dark};
}

/* Сепараторы */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: {separator};
    background-color: {separator};
}
"""
