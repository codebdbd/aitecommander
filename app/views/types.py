"""Типы данных для модуля views.

Централизованное определение TypedDict для улучшения type safety.
"""

from typing import Any, Literal, TypedDict, NotRequired

# ================================================================================
# БАЗОВЫЕ ТИПЫ
# ================================================================================

NodeType = Literal["section", "category", "root"]
LinkType = Literal["web", "file", "folder", "app"]


# ================================================================================
# ТИПЫ ССЫЛОК
# ================================================================================

class LinkData(TypedDict):
    """Полная структура данных ссылки.
    
    Используется в моделях, диалогах и контроллерах для типобезопасной
    передачи данных ссылок.
    """
    id: NotRequired[int]
    name: str
    url: str
    type: LinkType
    category_id: NotRequired[int]
    icon_path: NotRequired[str]
    is_favorite: NotRequired[bool]
    notes: NotRequired[str]
    args: NotRequired[str]
    last_used: NotRequired[str | float | None]
    created_at: NotRequired[str]
    updated_at: NotRequired[str]
    # Кэш иконки (внутреннее использование модели)
    _icon: NotRequired[Any]


class MinimalLinkData(TypedDict):
    """Минимальная структура ссылки для отображения."""
    id: int
    name: str
    url: str
    type: LinkType


# ================================================================================
# ТИПЫ СТРУКТУРЫ (ИЕРАРХИЯ)
# ================================================================================

class SphereData(TypedDict):
    """Данные сферы."""
    id: int
    name: str
    icon_path: NotRequired[str]
    color: NotRequired[str]


class SectionData(TypedDict):
    """Данные раздела."""
    id: int
    name: str
    sphere_id: int
    icon_path: NotRequired[str]
    categories: NotRequired[list["CategoryData"]]


class CategoryData(TypedDict):
    """Данные категории."""
    id: int
    name: str
    section_id: int
    icon_path: NotRequired[str]


class HierarchyData(TypedDict):
    """Иерархический путь к категории."""
    sphere_id: NotRequired[int]
    section_id: NotRequired[int]
    category_id: NotRequired[int]


# ================================================================================
# ТИПЫ ДЛЯ ДИАЛОГОВ
# ================================================================================

class LinkDialogInitData(TypedDict):
    """Данные инициализации LinkDialog."""
    spheres: list[SphereData]
    category_hierarchy: NotRequired[HierarchyData]


class BrowserProfileData(TypedDict):
    """Данные профиля браузера."""
    id: NotRequired[int]
    name: str
    email: NotRequired[str]
    browser_type: str
    profile_path: str


# ================================================================================
# ТИПЫ ДЛЯ DRAG & DROP
# ================================================================================

class DragDropPayload(TypedDict):
    """Payload для drag & drop операций."""
    item_type: NodeType
    item_id: int
    source_parent_id: NotRequired[int]


# ================================================================================
# ТИПЫ ДЛЯ КОНФИГУРАЦИИ
# ================================================================================

class UIConfig(TypedDict):
    """Конфигурация UI (подмножество app_config.ui)."""
    row_height: int
    icon_size: tuple[int, int]
    col_widths: list[int]
    link_dialog_width: int
    link_dialog_height: int
    link_dialog_margins: int
    link_dialog_spacing: int


# ================================================================================
# ЭКСПОРТ
# ================================================================================

__all__ = [
    # Базовые типы
    "NodeType",
    "LinkType",
    # Типы ссылок
    "LinkData",
    "MinimalLinkData",
    # Типы структуры
    "SphereData",
    "SectionData",
    "CategoryData",
    "HierarchyData",
    # Типы диалогов
    "LinkDialogInitData",
    "BrowserProfileData",
    # Drag & Drop
    "DragDropPayload",
    # Конфигурация
    "UIConfig",
]
