"""
Protocols для сервисного слоя.

✅ НОВЫЙ ФАЙЛ: Строгая типизация зависимостей через Protocol.
"""

from typing import Any, Dict, List, Optional, Protocol


class DatabaseProtocol(Protocol):
    """Протокол для Database с необходимыми атрибутами для сервисов.
    
    ✅ ИСПРАВЛЕНИЕ: Заменяет Any на конкретный Protocol для type safety.
    """
    
    # Репозитории/модели
    spheres: Any
    sections: Any
    categories: Any
    links: Any
    
    # Методы транзакций
    def transaction(self) -> Any:
        """Контекстный менеджер транзакции."""
        ...
    
    def commit(self) -> None:
        """Фиксирует транзакцию."""
        ...
    
    def rollback(self) -> None:
        """Откатывает транзакцию."""
        ...
    
    # Методы импорта/экспорта
    def get_full_structure(self) -> List[Dict]:
        """Возвращает полную структуру данных."""
        ...
    
    def export_full_structure(self) -> Dict[str, List]:
        """Экспортирует структуру."""
        ...
    
    def export_full_structure_async(
        self, on_finished=None, on_error=None, on_progress=None
    ) -> None:
        """Асинхронный экспорт структуры."""
        ...
    
    def import_full_structure(self, data: List[Dict]) -> None:
        """Импортирует структуру."""
        ...
    
    def import_full_structure_async(
        self, data: List[Dict], on_finished=None, on_error=None, on_progress=None
    ) -> None:
        """Асинхронный импорт структуры."""
        ...
    
    def export_section_tree(self, section_id: int) -> Dict[str, Any]:
        """Экспортирует раздел."""
        ...
    
    def import_section_tree(self, tree: Dict[str, Any]) -> None:
        """Импортирует раздел."""
        ...
    
    def export_category_tree(self, category_id: int) -> Dict[str, Any]:
        """Экспортирует категорию."""
        ...
    
    def import_category_tree(self, tree: Dict[str, Any]) -> None:
        """Импортирует категорию."""
        ...
    
    def import_category_trees_bulk(self, trees: List[Dict[str, Any]]) -> None:
        """Импортирует несколько категорий."""
        ...


__all__ = ["DatabaseProtocol"]
