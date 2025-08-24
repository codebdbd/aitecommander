# app/utils/system/undo/commands_structure.py
from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtGui import QUndoCommand

from app.services.structure_service import StructureService
from app.utils.ui.icon.cache_manager import clear_icon_cache


class SaveSectionCmd(QUndoCommand):
    """Сохранение (создание/редактирование) раздела.
    Тонкая обёртка над DB с эмиссией сигналов business-слоя для UI.
    """

    def __init__(self, new_data: Dict, old_data: Optional[Dict], main_window):
        super().__init__("Save section")
        self.main = main_window
        self.db = main_window.db
        self.structure_service = StructureService(self.db)
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.is_new = not bool(self.new_data.get("id"))
        self.new_id = self.new_data.get("id")

    def _emit_reload(self):
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                if self.is_new:
                    business.item_added.emit("section", self.new_id, self.new_data)
                else:
                    business.item_updated.emit("section", self.new_id, self.new_data)
                business.load_structure()
        except Exception:
            pass

    def redo(self):
        if self.is_new:
            result = self.structure_service.create_section(self.new_data)
            if result:
                self.new_id = result
                self.new_data["id"] = result
        else:
            # update возвращает bool; ID уже известен
            self.structure_service.update_section(
                self.new_data.get("id"), self.new_data
            )
            self.new_id = self.new_data.get("id")
        # UI выбор в дереве
        try:
            self.main.structure.update_tree(item_to_select=("section", self.new_id))
        except Exception:
            pass
        self._emit_reload()

    def undo(self):
        if self.is_new:
            # отменяем создание – удаляем раздел
            try:
                self.structure_service.delete_section(self.new_id)
            finally:
                try:
                    self.main.structure.update_tree()
                except Exception:
                    pass
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_deleted.emit("section", self.new_id)
                        business.load_structure()
                except Exception:
                    pass
        else:
            # откат редактирования – восстанавливаем старые данные
            if self.old_data:
                self.structure_service.update_section(
                    self.old_data["id"], self.old_data
                )
                try:
                    self.main.structure.update_tree(
                        item_to_select=("section", self.old_data["id"])
                    )
                except Exception:
                    pass
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_updated.emit(
                            "section", self.old_data["id"], self.old_data
                        )
                        business.load_structure()
                except Exception:
                    pass


class DeleteSectionCmd(QUndoCommand):
    """Удаление раздела с поддержкой полноценного восстановления (раздел+категории+ссылки)."""

    def __init__(self, section_data: Dict, main_window):
        super().__init__("Delete section")
        self.main = main_window
        self.db = main_window.db
        self.structure_service = StructureService(self.db)
        self.section = dict(section_data) if section_data else {}
        # Бэкап полного дерева раздела
        self._backup_tree = self.structure_service.export_section_tree(
            self.section.get("id")
        )

    def redo(self):
        section_id = self.section.get("id")
        if section_id is None:
            return
        self.structure_service.delete_section(section_id)
        try:
            self.main.structure.update_tree()
        except Exception:
            pass
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                business.item_deleted.emit("section", section_id)
                business.load_structure()
        except Exception:
            pass

    def undo(self):
        try:
            self.structure_service.import_section_tree(self._backup_tree)
            section_id = self._backup_tree["section"]["id"]
            try:
                self.main.structure.update_tree(item_to_select=("section", section_id))
            except Exception:
                pass
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.item_added.emit(
                        "section", section_id, self._backup_tree["section"]
                    )
                    business.load_structure()
            except Exception:
                pass
        except Exception:
            # В случае сбоя восстановления — оставляем как есть, без исключений в UI
            pass


class SaveCategoryCmd(QUndoCommand):
    """Сохранение (создание/редактирование) категории."""

    def __init__(
        self,
        new_data: Dict,
        old_data: Optional[Dict],
        main_window,
        *,
        skip_reload: bool = False,
    ):
        super().__init__("Save category")
        self.main = main_window
        self.db = main_window.db
        self.structure_service = StructureService(self.db)
        self.new_data = dict(new_data) if new_data else {}
        self.old_data = dict(old_data) if old_data else None
        self.is_new = not bool(self.new_data.get("id"))
        self.new_id = self.new_data.get("id")
        self.skip_reload = skip_reload

    def _emit_reload(self):
        if self.skip_reload:
            return
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                # Иконки категорий могли измениться — очищаем кэш, чтобы плитки перерисовали актуальные
                try:
                    clear_icon_cache()
                except Exception:
                    pass
                if self.is_new:
                    # Для категорий второй аргумент — parent_id (section_id)
                    parent_id = self.new_data.get("section_id")
                    business.item_added.emit("category", parent_id, self.new_data)
                else:
                    business.item_updated.emit("category", self.new_id, self.new_data)
                business.load_structure()
        except Exception:
            pass

    def redo(self):
        if self.is_new:
            result = self.structure_service.create_category(self.new_data)
            if result:
                self.new_id = result
                self.new_data["id"] = result
        else:
            self.structure_service.update_category(
                self.new_data.get("id"), self.new_data
            )
            self.new_id = self.new_data.get("id")
        try:
            if not self.skip_reload:
                self.main.structure.update_tree(
                    item_to_select=("category", self.new_id)
                )
        except Exception:
            pass
        self._emit_reload()

    def undo(self):
        if self.is_new:
            section_id = self.new_data.get("section_id")
            if self.new_id:
                self.structure_service.delete_category(self.new_id)
            try:
                if not self.skip_reload:
                    self.main.structure.update_tree(
                        item_to_select=("section", section_id)
                    )
            except Exception:
                pass
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.item_deleted.emit("category", self.new_id)
                    business.load_structure()
            except Exception:
                pass
        else:
            if self.old_data:
                self.structure_service.update_category(
                    self.old_data["id"], self.old_data
                )
                try:
                    if not self.skip_reload:
                        self.main.structure.update_tree(
                            item_to_select=("category", self.old_data["id"])
                        )
                except Exception:
                    pass
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_updated.emit(
                            "category", self.old_data["id"], self.old_data
                        )
                        business.load_structure()
                except Exception:
                    pass


class DeleteCategoryCmd(QUndoCommand):
    """Удаление категории с восстановлением поддерева (категория+ссылки)."""

    def __init__(self, category_data: Dict, main_window, *, skip_reload: bool = False):
        super().__init__("Delete category")
        self.main = main_window
        self.db = main_window.db
        self.structure_service = StructureService(self.db)
        self.category = dict(category_data) if category_data else {}
        self.skip_reload = bool(skip_reload)
        # Бэкап поддерева категории
        self._backup_tree = self.structure_service.export_category_tree(
            self.category.get("id")
        )

    def redo(self):
        category_id = self.category.get("id")
        if category_id is None:
            return
        self.structure_service.delete_category(category_id)
        section_id = self.category.get("section_id")
        business = getattr(self.main, "structure_business", None)

        if self.skip_reload:
            # Минимальные события без тяжёлых перезагрузок
            try:
                if business:
                    # Точечно уведомляем UI о удалении
                    business.item_deleted.emit("category", category_id)
            except Exception:
                pass
            return

        # Обычный одиночный сценарий: корректно обновляем UI и данные
        try:
            # Попробуем сместить фокус корректно
            self.main.structure.update_tree(item_to_select=("section", section_id))
        except Exception:
            pass
        # Явно обновляем плитки категорий для выбранного раздела,
        # чтобы гарантировать отражение удаления в интерфейсе
        try:
            if business:
                # Критично: инвалидируем кэш категорий раздела, иначе select_section
                # может взять устаревшие данные из categories_{section_id}
                try:
                    # внутренний метод, но безопасен для вызова из команды
                    business._invalidate_categories_cache(section_id)
                except Exception:
                    pass
                business.select_section(section_id)
        except Exception:
            pass
        try:
            if business:
                # При удалении также сбрасываем кэш иконок категорий
                try:
                    clear_icon_cache()
                except Exception:
                    pass
                business.item_deleted.emit("category", category_id)
                business.load_structure()
        except Exception:
            pass

    def undo(self):
        try:
            self.structure_service.import_category_tree(self._backup_tree)
            category_id = self.category.get("id")
            try:
                self.main.structure.update_links_table(category_id)
            except Exception:
                pass
            try:
                self.main.structure.update_tree(
                    item_to_select=("category", category_id)
                )
            except Exception:
                pass
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    # После восстановления сбрасываем кэш, чтобы обновились иконки восстановленной категории
                    try:
                        clear_icon_cache()
                    except Exception:
                        pass
                    business.item_added.emit(
                        "category",
                        self.category.get("section_id"),
                        self._backup_tree["category"],
                    )
                    business.load_structure()
            except Exception:
                pass
        except Exception:
            # В случае сбоя восстановления — оставляем как есть
            pass
