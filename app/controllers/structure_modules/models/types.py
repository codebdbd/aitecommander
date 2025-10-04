# app/controllers/structure_modules/types.py

"""Строгие типы для structure_modules - PyQt6 Best Practices.

Этот модуль содержит TypedDict определения для всех data структур,
используемых в операциях со структурой. Заменяет Dict[str, Any] на
конкретные типизированные структуры для лучшей безопасности типов.
"""

from typing import TypedDict, Optional, List, Any
from enum import Enum


# ===== ENUMS =====

class StructureItemType(Enum):
    """Типы элементов структуры."""
    SPHERE = "sphere"
    SECTION = "section"
    CATEGORY = "category"
    LINK = "link"


class SignalType(Enum):
    """Типы сигналов для операций со структурой."""
    ITEM_ADDED = "item_added"
    ITEM_UPDATED = "item_updated"
    ITEM_DELETED = "item_deleted"
    STRUCTURE_LOADED = "structure_loaded"
    SECTIONS_LOADED = "sections_loaded"
    CATEGORIES_LOADED = "categories_loaded"
    SPHERES_LOADED = "spheres_loaded"
    LINKS_LOADED = "links_loaded"
    SEARCH_RESULTS = "search_results"
    ERROR_OCCURRED = "error_occurred"
    OPERATION_STARTED = "operation_started"
    OPERATION_FINISHED = "operation_finished"
    LOADING_STARTED = "loading_started"
    UPDATE_UI = "update_ui"
    UPDATE_FAVORITES = "update_favorites"
    UPDATE_RECENT_LINKS = "update_recent_links"


# ===== BASE TYPED DICTS =====

class BaseItemData(TypedDict):
    """Базовые поля для всех элементов структуры."""
    id: int
    name: str
    created_at: Optional[str]
    updated_at: Optional[str]


# ===== SPHERE TYPES =====

class SphereData(BaseItemData):
    """Данные сферы.
    
    Сфера - это верхний уровень структуры, содержащий разделы.
    Примеры: "Работа", "Личное", "Образование".
    
    Attributes:
        id: Уникальный идентификатор сферы
        name: Название сферы (обязательно)
        description: Описание сферы (опционально)
        color: Цвет сферы в hex формате (например, "#FF5733")
        icon: Иконка сферы (опционально)
        is_active: Активна ли сфера (обязательно)
        created_at: Время создания
        updated_at: Время последнего обновления
    """
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    is_active: bool


class SphereCreateData(TypedDict):
    """Данные для создания сферы."""
    name: str
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    is_active: bool


class SphereUpdateData(TypedDict, total=False):
    """Данные для обновления сферы (все поля опциональны)."""
    name: str
    description: Optional[str]
    color: Optional[str]
    icon: Optional[str]
    is_active: bool


# ===== SECTION TYPES =====

class SectionData(BaseItemData):
    """Данные раздела.
    
    Раздел - это средний уровень структуры, принадлежит сфере и содержит категории.
    Примеры: "Проекты", "Задачи", "Документы".
    
    Attributes:
        id: Уникальный идентификатор раздела
        name: Название раздела (обязательно)
        sphere_id: ID сферы, к которой принадлежит раздел
        description: Описание раздела (опционально)
        position: Позиция раздела в списке (для сортировки)
        is_active: Активен ли раздел (обязательно)
        created_at: Время создания
        updated_at: Время последнего обновления
    """
    sphere_id: int
    description: Optional[str]
    position: int
    is_active: bool


class SectionCreateData(TypedDict):
    """Данные для создания раздела."""
    name: str
    sphere_id: int
    description: Optional[str]
    position: Optional[int]
    is_active: bool


class SectionUpdateData(TypedDict, total=False):
    """Данные для обновления раздела (все поля опциональны)."""
    name: str
    sphere_id: int
    description: Optional[str]
    position: int
    is_active: bool


# ===== CATEGORY TYPES =====

class CategoryData(BaseItemData):
    """Данные категории.
    
    Категория - это нижний уровень структуры, принадлежит разделу и содержит ссылки.
    Примеры: "Важное", "Идеи", "Ресурсы".
    
    Attributes:
        id: Уникальный идентификатор категории
        name: Название категории (обязательно)
        section_id: ID раздела, к которому принадлежит категория
        description: Описание категории (опционально)
        position: Позиция категории в списке (для сортировки)
        is_active: Активна ли категория (обязательно)
        color: Цвет категории в hex формате (опционально)
        icon: Иконка категории (опционально)
        created_at: Время создания
        updated_at: Время последнего обновления
    """
    section_id: int
    description: Optional[str]
    position: int
    is_active: bool
    color: Optional[str]
    icon: Optional[str]


class CategoryCreateData(TypedDict):
    """Данные для создания категории."""
    name: str
    section_id: int
    description: Optional[str]
    position: Optional[int]
    is_active: bool
    color: Optional[str]
    icon: Optional[str]


class CategoryUpdateData(TypedDict, total=False):
    """Данные для обновления категории (все поля опциональны)."""
    name: str
    section_id: int
    description: Optional[str]
    position: int
    is_active: bool
    color: Optional[str]
    icon: Optional[str]


# ===== LINK TYPES =====

class LinkData(TypedDict):
    """Данные ссылки."""
    id: int
    category_id: int
    url: str
    title: str
    description: Optional[str]
    favicon_url: Optional[str]
    is_favorite: bool
    created_at: Optional[str]
    updated_at: Optional[str]
    last_accessed: Optional[str]
    access_count: int


# ===== SEARCH TYPES =====

class SearchResultItem(TypedDict):
    """Элемент результата поиска."""
    id: int
    type: str  # "sphere", "section", "category", "link"
    title: str
    description: Optional[str]
    url: Optional[str]
    parent_id: Optional[int]
    parent_name: Optional[str]
    relevance_score: float


# ===== OPERATION RESULT TYPES =====

class OperationResult(TypedDict):
    """Результат операции."""
    success: bool
    message: Optional[str]
    error: Optional[str]
    data: Optional[Any]


class ValidationResult(TypedDict):
    """Результат валидации."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]


# ===== COUNT TYPES =====

class NestedObjectsCount(TypedDict):
    """Количество вложенных объектов."""
    categories_count: int
    links_count: int


class SectionNestedCount(NestedObjectsCount):
    """Количество объектов в разделе."""
    pass


class CategoryNestedCount(TypedDict):
    """Количество объектов в категории."""
    links_count: int


# ===== SIGNAL PAYLOAD TYPES =====

class ItemCreatedPayload(TypedDict):
    """Payload для сигнала создания элемента."""
    item_type: str
    parent_id: int
    item_data: BaseItemData


class ItemUpdatedPayload(TypedDict):
    """Payload для сигнала обновления элемента."""
    item_type: str
    item_id: int
    item_data: BaseItemData


class ItemDeletedPayload(TypedDict):
    """Payload для сигнала удаления элемента."""
    item_type: str
    item_id: int
    old_data: Optional[BaseItemData]


class ErrorPayload(TypedDict):
    """Payload для сигнала ошибки."""
    title: str
    message: str
    error_code: Optional[str]


# ===== CACHE TYPES =====

class CacheKey(TypedDict):
    """Ключ кэша."""
    key: str
    ttl: Optional[int]


class CacheEntry(TypedDict):
    """Запись кэша."""
    key: str
    value: Any
    created_at: float
    expires_at: Optional[float]


# ===== METRICS TYPES =====

class MetricSpan(TypedDict):
    """Метрический спан."""
    name: str
    start_time: float
    end_time: Optional[float]
    duration: Optional[float]
    tags: Optional[dict[str, str]]


# ===== TASK TYPES =====

class TaskInfo(TypedDict):
    """Информация о задаче."""
    task_id: str
    description: str
    status: str  # "pending", "running", "completed", "failed"
    created_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    progress: Optional[float]
    result: Optional[Any]
    error: Optional[str]


# ===== CONFIGURATION TYPES =====

class ItemTypeConfig:
    """Конфигурация для типа элемента структуры."""

    def __init__(
        self,
        item_type: StructureItemType,
        parent_field: str,
        ru_name: str,
        upsert_method_name: str,
    ):
        self.item_type = item_type
        self.parent_field = parent_field
        self.ru_name = ru_name
        self.upsert_method_name = upsert_method_name


# ===== UNION TYPES =====

# Объединение всех типов данных элементов
AnyItemData = SphereData | SectionData | CategoryData
AnyCreateData = SphereCreateData | SectionCreateData | CategoryCreateData  
AnyUpdateData = SphereUpdateData | SectionUpdateData | CategoryUpdateData

# Объединение всех payload типов
AnySignalPayload = (
    ItemCreatedPayload | 
    ItemUpdatedPayload | 
    ItemDeletedPayload | 
    ErrorPayload
)
