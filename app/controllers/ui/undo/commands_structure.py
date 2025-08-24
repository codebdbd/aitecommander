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

    def __init__(
        self,
        category_data: Dict,
        main_window,
        *,
        skip_reload: bool = False,
        lightweight_reload: bool = False,
    ):
        super().__init__("Delete category")
        self.main = main_window
        self.db = main_window.db
        self.structure_service = StructureService(self.db)
        self.category = dict(category_data) if category_data else {}
        self.skip_reload = bool(skip_reload)
        self.lightweight_reload = bool(lightweight_reload)
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

        if self.lightweight_reload:
            # Облегчённый режим: точечные обновления без полной перезагрузки структуры
            try:
                self.main.structure.update_tree(item_to_select=("section", section_id))
            except Exception:
                pass
            try:
                if business:
                    try:
                        business._invalidate_categories_cache(section_id)
                    except Exception:
                        pass
                    business.select_section(section_id)
                    # В lightweight-режиме не вызываем clear_icon_cache() и load_structure()
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


class DeleteCategoriesBatchCmd(QUndoCommand):
    """Пакетное удаление нескольких категорий одной операцией.

    - Удаляет категории по списку ID через сервис без промежуточной перезагрузки UI
    - Эмитит business.item_deleted для каждой категории
    - В конце выполняет ОДНУ финальную перезагрузку UI/плиток
    - Поддерживает undo через восстановление сохранённых бэкапов поддеревьев
    """

    def __init__(self, categories_data: list[Dict], main_window):
        super().__init__("Delete categories (batch)")
        self.main = main_window
        self.db = main_window.db
        self.structure_service = StructureService(self.db)
        # Сохраним плоский список данных категорий и их бэкапы для undo
        self.categories = [dict(c) for c in (categories_data or [])]
        self._backups = []
        for cat in self.categories:
            try:
                backup = self.structure_service.export_category_tree(cat.get("id"))
            except Exception:
                backup = None
            self._backups.append(backup)

    def redo(self):
        business = getattr(self.main, "structure_business", None)
        section_id_for_focus = None
        # Подавляем всплеск сигналов выбора на время пакетной операции
        tree = None
        selection = None
        try:
            struct = getattr(self.main, "structure", None)
            tree = getattr(struct, "tree", None)
            selection = getattr(struct, "selection_handler", None)
            if selection is not None:
                try:
                    selection.begin_suppress_selection()
                except Exception:
                    pass
            if tree is not None:
                tree.blockSignals(True)
        except Exception:
            tree = None
        try:
            # 1) Удаляем все категории и эмитим точечные события
            for cat in self.categories:
                cid = cat.get("id")
                if cid is None:
                    continue
                try:
                    self.structure_service.delete_category(cid)
                except Exception:
                    continue
                try:
                    if business:
                        business.item_deleted.emit("category", cid)
                except Exception:
                    pass
                # Используем последний встретившийся section_id для финального фокуса
                section_id_for_focus = cat.get("section_id") or section_id_for_focus
        finally:
            # 2) Одна финальная перезагрузка/фокус
            # ВАЖНО: перед финальными обновлениями возвращаем сигналы/обработку
            try:
                if tree is not None:
                    tree.blockSignals(False)
            except Exception:
                pass
            try:
                if selection is not None:
                    selection.end_suppress_selection()
            except Exception:
                pass
        try:
            if section_id_for_focus is not None:
                self.main.structure.update_tree(
                    item_to_select=("section", section_id_for_focus)
                )
        except Exception:
            pass
        try:
            if business:
                try:
                    clear_icon_cache()
                except Exception:
                    pass
                if section_id_for_focus is not None:
                    try:
                        business._invalidate_categories_cache(section_id_for_focus)
                    except Exception:
                        pass
                    business.select_section(section_id_for_focus)
                business.load_structure()
        except Exception:
            pass

    def undo(self):
        # Восстанавливаем категории из бэкапов в исходном порядке (только данные),
        # без тяжёлых перезагрузок/сигналов на каждом элементе
        business = getattr(self.main, "structure_business", None)
        section_id_for_focus = None
        # Подавляем сигналы выбора на время восстановления
        tree = None
        selection = None
        try:
            struct = getattr(self.main, "structure", None)
            tree = getattr(struct, "tree", None)
            selection = getattr(struct, "selection_handler", None)
            if selection is not None:
                try:
                    selection.begin_suppress_selection()
                except Exception:
                    pass
            if tree is not None:
                tree.blockSignals(True)
        except Exception:
            tree = None
        try:
            for backup in self._backups:
                if not backup:
                    continue
                try:
                    self.structure_service.import_category_tree(backup)
                except Exception:
                    # Плохой бэкап — пропускаем, не ломаем общую операцию
                    continue
                # Запомним раздел для финального фокуса
                section_id_for_focus = (
                    backup.get("category", {}).get("section_id", section_id_for_focus)
                )
        finally:
            # Одна финальная перезагрузка/фокус и очистка кэша
            # Перед финальными действиями возвращаем сигналы и обработку
            try:
                if tree is not None:
                    tree.blockSignals(False)
            except Exception:
                pass
            try:
                if selection is not None:
                    selection.end_suppress_selection()
            except Exception:
                pass
        try:
            # Иконки могли измениться — очищаем кэш один раз
            clear_icon_cache()
        except Exception:
            pass

        try:
            if section_id_for_focus is not None:
                self.main.structure.update_tree(
                    item_to_select=("section", section_id_for_focus)
                )
        except Exception:
            pass

        try:
            if business:
                # По аналогии с redo: инвалидация кэша категорий выбранного раздела
                if section_id_for_focus is not None:
                    try:
                        business._invalidate_categories_cache(section_id_for_focus)
                    except Exception:
                        pass
                    business.select_section(section_id_for_focus)
                business.load_structure()
        except Exception:
            pass
