from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.models.db import Database
from app.models.structure_model import StructureModel

from .uow import UnitOfWork


class StructureService:
    """
    Сервис работы со структурой (сферы -> разделы -> категории).
    Этап 1: тонкая обёртка над текущим StructureModel/Database без дублирования логики.
    Этап 2+: постепенный перенос бизнес‑логики из StructureModel внутрь сервиса.
    """

    def __init__(self, db: Database):
        self.db = db
        # Временно используем существующую модель как адаптер
        self._model = StructureModel(db)

    # --- Чтение ---
    def get_spheres(self) -> List[Dict[str, Any]]:
        return self._model.get_spheres()

    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        return self._model.get_sphere_by_id(sphere_id)

    def get_sections(self, sphere_id: int) -> List[Dict[str, Any]]:
        return self._model.get_sections(sphere_id)

    def get_section_by_id(self, section_id: int) -> Optional[Dict[str, Any]]:
        return self._model.get_section_by_id(section_id)

    def get_categories(self, section_id: int) -> List[Dict[str, Any]]:
        return self._model.get_categories(section_id)

    def get_category_by_id(self, category_id: int) -> Optional[Dict[str, Any]]:
        return self._model.get_category_by_id(category_id)

    def get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, Any]]:
        return self._model.get_category_hierarchy(category_id)

    def get_full_structure(self) -> List[Dict[str, Any]]:
        # Используем существующую агрегирующую реализацию
        return self.db.get_full_structure()

    # --- Статистика/подсчёты ---
    def count_nested_objects_for_section(self, section_id: int) -> Tuple[int, int]:
        return self._model.count_nested_objects_for_section(section_id)

    # --- Мутации (с транзакциями) ---
    def update_item_positions(self, table_name: str, ids_in_order: List[int]) -> None:
        # Гарантируем атомарность перестановки
        with UnitOfWork(self.db):
            self._model.update_item_positions(table_name, ids_in_order)

    def create_section(self, data: Dict[str, Any]) -> Optional[int]:
        with UnitOfWork(self.db):
            return self._model.create_section(data)

    def update_section(self, section_id: int, data: Dict[str, Any]) -> bool:
        with UnitOfWork(self.db):
            return self._model.update_section(section_id, data)

    def delete_section(self, section_id: int) -> bool:
        with UnitOfWork(self.db):
            return self._model.delete_section(section_id)

    def create_category(self, data: Dict[str, Any]) -> Optional[int]:
        with UnitOfWork(self.db):
            return self._model.create_category(data)

    def update_category(self, category_id: int, data: Dict[str, Any]) -> bool:
        with UnitOfWork(self.db):
            return self._model.update_category(category_id, data)

    def delete_category(self, category_id: int) -> bool:
        # ВАЖНО: CategoryModel.delete_category() уже использует self.transaction()
        # и управляет транзакцией самостоятельно (BEGIN/COMMIT). Оборачивание
        # во внешний UnitOfWork приведёт к вложенным транзакциям в SQLite и
        # ошибке вида "cannot start a transaction within a transaction".
        return self._model.delete_category(category_id)

    def delete_categories_bulk(self, category_ids: List[int]) -> int:
        """Пакетное удаление категорий в одной транзакции (делегирование модели).

        ВАЖНО: метод модели сам управляет транзакцией, поэтому здесь НЕ используем UnitOfWork,
        чтобы избежать вложенных транзакций в SQLite.
        Возвращает число удалённых категорий.
        """
        return self.db.categories.delete_categories_bulk(category_ids or [])

    def create_categories_bulk(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Пакетное создание категорий (единая транзакция).

        ВАЖНО: insert_categories_bulk в CategoryModel/Repository уже управляет
        транзакцией самостоятельно. Оборачивание здесь в UnitOfWork приведёт к
        вложенным транзакциям в SQLite и ошибке вида
        "cannot start a transaction within a transaction".
        """
        return self._model.create_categories_bulk(items)

    # --- Импорт/экспорт ---
    def export_full_structure(self) -> Dict[str, List]:
        return self.db.export_full_structure()

    def import_full_structure(self, data: List[Dict[str, Any]]) -> None:
        with UnitOfWork(self.db):
            self.db.import_full_structure(data)

    def export_section_tree(self, section_id: int) -> Dict[str, Any]:
        return self.db.export_section_tree(section_id)

    def import_section_tree(self, tree: Dict[str, Any]) -> None:
        with UnitOfWork(self.db):
            self.db.import_section_tree(tree)

    def export_category_tree(self, category_id: int) -> Dict[str, Any]:
        return self.db.export_category_tree(category_id)

    def import_category_tree(self, tree: Dict[str, Any]) -> None:
        with UnitOfWork(self.db):
            self.db.import_category_tree(tree)

    # --- Bulk operations ---
    def import_category_trees_bulk(self, trees: List[Dict[str, Any]]) -> None:
        """Импортирует несколько поддеревьев категорий одной операцией (одна транзакция).

        Делегирует в Database.import_category_trees_bulk, чтобы избежать вложенных транзакций.
        Используется, например, для быстрого undo пакетного удаления категорий.
        """
        self.db.import_category_trees_bulk(trees or [])
