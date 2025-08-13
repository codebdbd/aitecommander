# Модуль для создания элементов таблицы ссылок
# Содержит методы построения различных типов элементов QTableWidgetItem

import logging
from typing import Dict, List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTableWidgetItem

from app.utils.ui.icon.icon_operations.creators import create_icon_from_path, themed_icon
from app.utils.ui.icon.path_service import get_current_theme, icon_path_service

# Константы для магических чисел
MAX_NOTES_LENGTH = 462
STAR_SYMBOL = "★"
STAR_COLOR = "#FFD700"
PATH_SEPARATOR = " → "


class ItemBuildersMixin:
    """Миксин для создания элементов таблицы ссылок."""
    
    def _set_icon_if_exists(self, item: QTableWidgetItem, icon_name: str) -> None:
        """Устанавливает иконку для элемента. Если файл не найден, ничего не делает."""
        if not icon_name:
            return
        
        try:
            # Используем систему иконок из utils
            theme = get_current_theme()
            icon = themed_icon(icon_name, theme, source='links_table')
            if icon and not icon.isNull():
                item.setIcon(icon)
                return
            
            # Fallback: пробуем найти иконку по путям
            icon_path = icon_path_service.get_user_icons_dir() / icon_name
            if not icon_path.exists():
                icon_path = icon_path_service.get_ui_icons_dir() / icon_name
            if icon_path.exists():
                # Используем вспомогательную функцию для создания иконки из пути
                fallback_icon = create_icon_from_path(str(icon_path))
                if not fallback_icon.isNull():
                    item.setIcon(fallback_icon)
                    return
        except Exception as e:
            logging.warning(f"[LinksTableView] Ошибка установки иконки {icon_name}: {e}")

    def _create_star_item(self, is_favorite: bool) -> QTableWidgetItem:
        """Создает элемент со звездочкой для избранного."""
        star_text = STAR_SYMBOL if is_favorite else ""

        
        star_item = QTableWidgetItem(star_text)
        star_item.setForeground(QColor(STAR_COLOR))
        star_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return star_item

    def _create_name_item(self, link: Dict, mode: str) -> QTableWidgetItem:
        """Создает элемент с названием и иконкой."""
        name_text = link.get("name", "")
        
        # Для режима поиска добавляем путь
        if mode == "search":
            trail = self._build_category_trail(link)
            if trail:
                name_text = f"{name_text} ({trail})"
        
        name_item = QTableWidgetItem(name_text)
        
        # Получаем иконку из данных ссылки
        icon_name = link.get("icon_path", "")
        link_type = link.get("type", "file")  # По умолчанию тип "file"
        
        # Сначала пробуем установить пользовательскую иконку
        icon_set = False
        if icon_name:
            # Проверяем, что иконка реально существует
            theme = get_current_theme()
            icon = themed_icon(icon_name, theme, source='links_table')
            if icon and not icon.isNull():
                name_item.setIcon(icon)
                icon_set = True
            else:
                # Проверяем по путям
                icon_path = icon_path_service.get_user_icons_dir() / icon_name
                if not icon_path.exists():
                    icon_path = icon_path_service.get_ui_icons_dir() / icon_name
                if icon_path.exists():
                    fallback_icon = create_icon_from_path(str(icon_path))
                    if not fallback_icon.isNull():
                        name_item.setIcon(fallback_icon)
                        icon_set = True
        
        # Если пользовательская иконка не установлена, устанавливаем иконку по умолчанию
        if not icon_set:
            from app.config_data import app_config
            default_icons = app_config.get('settings', {}).get('default_icons', {})
            default_icon = default_icons.get(link_type, default_icons.get('default', 'default.ico'))
            self._set_icon_if_exists(name_item, default_icon)
        
        return name_item

    def _build_category_trail(self, link: Dict) -> str:
        """Строит путь категории для режима поиска."""
        parts = [
            link.get("sphere_name", ""),
            link.get("section_name", ""),
            link.get("category_name", "")
        ]
        return PATH_SEPARATOR.join(filter(None, parts))

    def _create_last_used_item(self, last_used) -> QTableWidgetItem:
        """Создает элемент с датой последнего использования."""
        from app.utils.system.date_utils import format_last_used
        last_used_item = QTableWidgetItem(format_last_used(last_used))
        last_used_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return last_used_item

    def _create_notes_item(self, notes: str, truncate: bool = False) -> QTableWidgetItem:
        """Создает элемент с заметками."""
        notes_text = str(notes or "")
        
        if truncate and len(notes_text) > MAX_NOTES_LENGTH:
            display_text = notes_text[:MAX_NOTES_LENGTH] + "..."
            notes_item = QTableWidgetItem(display_text)
            # Добавляем tooltip с полным текстом
            if notes_text:
                notes_item.setToolTip(notes)
        else:
            notes_item = QTableWidgetItem(notes_text)
        
        # Устанавливаем иконку заметки, если текст не пустой
        if notes_text:
            self._set_icon_if_exists(notes_item, "notes.png")
        
        return notes_item

    def _create_path_item(self, link: Dict) -> QTableWidgetItem:
        """Создает элемент с URL или путем."""
        url_or_path = link.get("url", "") or link.get("path", "")
        path_item = QTableWidgetItem(url_or_path)
        
        if url_or_path:
            path_item.setToolTip(url_or_path)
        
        return path_item

    def _add_tooltips_to_name_item(self, name_item: QTableWidgetItem, link: Dict):
        """Добавляет tooltip к элементу названия."""
        url_or_path = link.get("url", "") or link.get("path", "")
        if url_or_path:
            name_item.setToolTip(f"<b>URL/Путь:</b> {url_or_path}")

    def build_row(self, link: Dict, mode: str = "normal") -> List[QTableWidgetItem]:
        """Строит строку таблицы для ссылки."""
        # Проверка входных параметров
        if not isinstance(link, dict):
            logging.warning(f"[LinksTableView] Некорректные данные ссылки: {type(link)}")
            return []
        
        if 'id' not in link:
            logging.warning("[LinksTableView] Отсутствует ID в данных ссылки")
            return []

        try:
            # Основные элементы для всех режимов
            star_item = self._create_star_item(link.get("is_favorite", False))
            name_item = self._create_name_item(link, mode)
            items = [star_item, name_item]

            if mode == "normal":
                # Режим обычного отображения
                last_used_item = self._create_last_used_item(link.get("last_used"))
                notes_item = self._create_notes_item(link.get("notes", ""))
                items.extend([last_used_item, notes_item])
            else:
                # Режим поиска
                path_item = self._create_path_item(link)
                notes_item = self._create_notes_item(link.get("notes", ""), truncate=True)
                self._add_tooltips_to_name_item(name_item, link)
                items.extend([path_item, notes_item])

            # Сохраняем данные ссылки в каждом элементе
            for item in items:
                item.setData(Qt.ItemDataRole.UserRole, link)

            return items

        except Exception as e:
            logging.error(f"[LinksTableView] Ошибка создания строки для ссылки {link.get('id', 'unknown')}: {e}")
            return []
