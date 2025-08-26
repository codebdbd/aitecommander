# app/utils/system/undo/commands_structure.py
from __future__ import annotations

import logging
from typing import Dict, Optional

from PyQt6.QtGui import QUndoCommand

from app.services.structure_service import StructureService
from app.utils.ui.icon.cache_manager import clear_icon_cache

logger = logging.getLogger(__name__)

class SaveSectionCmd(QUndoCommand):
    """Сохранение (создание/редактирование) раздела.
    Тонкая обёртка над DB с эмиссией сигналов business-слоя для UI.
    """

    def __init__(self, new_data: Dict, old_data: Optional[Dict], main_window):
        super().__init__("Save section")
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
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
                # Полная перезагрузка больше не требуется — модель обновится через сигналы
        except Exception:
            pass

    def redo(self):
        # Глобальная защита от удалений на время чувствительных операций (например, вставки)
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug("[DeleteGuard] DeleteSectionCmd.redo suppressed by _suppress_deletes flag")
                return
        except Exception:
            pass
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
        # Наводим фокус на раздел через бизнес-логику
        try:
            business = getattr(self.main, "structure_business", None)
            if business:
                business.select_section(self.new_id)
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
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_deleted.emit("section", self.new_id)
                        # Инкрементальное обновление — без полной перезагрузки
                except Exception:
                    pass
        else:
            # откат редактирования – восстанавливаем старые данные
            if self.old_data:
                self.structure_service.update_section(
                    self.old_data["id"], self.old_data
                )
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.select_section(self.old_data["id"])
                except Exception:
                    pass
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_updated.emit(
                            "section", self.old_data["id"], self.old_data
                        )
                        # Инкрементальное обновление — без полной перезагрузки
                except Exception:
                    pass


class DeleteSectionCmd(QUndoCommand):
    """Удаление раздела с поддержкой полноценного восстановления (раздел+категории+ссылки)."""

    def __init__(self, section_data: Dict, main_window):
        super().__init__("Delete section")
        self.main = main_window
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
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
            business = getattr(self.main, "structure_business", None)
            if business:
                business.item_deleted.emit("section", section_id)
                # Инкрементальное обновление — без полной перезагрузки
        except Exception:
            pass

    def undo(self):
        try:
            self.structure_service.import_section_tree(self._backup_tree)
            section_id = self._backup_tree["section"]["id"]
            # Если есть восстановленные категории — выберем первую и обновим таблицу ссылок
            try:
                categories = self._backup_tree.get("categories") or []
                first_cat = None
                for item in categories:
                    cat = (item or {}).get("category") or {}
                    if cat.get("id") is not None:
                        first_cat = cat
                        break
                if first_cat is not None:
                    cat_id = first_cat.get("id")
                    try:
                        self.main.structure.update_links_table(cat_id)
                    except Exception:
                        pass
                    try:
                        business = getattr(self.main, "structure_business", None)
                        if business:
                            business.select_category(cat_id)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.select_section(section_id)
            except Exception:
                pass
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.item_added.emit(
                        "section", section_id, self._backup_tree["section"]
                    )
                    # Инкрементальное обновление — без полной перезагрузки
            except Exception:
                pass
            # Гарантируем немедленное обновление дерева после Undo за счёт перезагрузки структуры
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    try:
                        business._invalidate_structure_cache()
                    except Exception:
                        pass
                    business._schedule_structure_reload(0)
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
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
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
                # Полная перезагрузка больше не требуется — модель обновится через сигналы
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
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.select_category(self.new_id)
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
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.select_section(section_id)
            except Exception:
                pass
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.item_deleted.emit("category", self.new_id)
                    # Инкрементальное обновление — без полной перезагрузки
            except Exception:
                pass
        else:
            if self.old_data:
                self.structure_service.update_category(
                    self.old_data["id"], self.old_data
                )
                try:
                    if not self.skip_reload:
                        business = getattr(self.main, "structure_business", None)
                        if business:
                            business.select_category(self.old_data["id"])
                except Exception:
                    pass
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_updated.emit(
                            "category", self.old_data["id"], self.old_data
                        )
                        # Инкрементальное обновление — без полной перезагрузки
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
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
        self.structure_service = StructureService(self.db)
        self.category = dict(category_data) if category_data else {}
        self.skip_reload = bool(skip_reload)
        self.lightweight_reload = bool(lightweight_reload)
        # Бэкап поддерева категории
        self._backup_tree = self.structure_service.export_category_tree(
            self.category.get("id")
        )

    def redo(self):
        # Глобальная защита от удалений на время чувствительных операций (например, вставки)
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug("[DeleteGuard] DeleteCategoryCmd.redo suppressed by _suppress_deletes flag")
                return
        except Exception:
            pass
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
            # Фокус на раздел без полной перезагрузки дерева
            try:
                if business:
                    business.select_section(section_id)
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
            # Попробуем сместить фокус корректно без полной перезагрузки
            if business:
                business.select_section(section_id)
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
                # Инкрементальное обновление — без полной перезагрузки
        except Exception:
            pass

    def undo(self):
        try:
            self.structure_service.import_category_tree(self._backup_tree)
            category_id = self.category.get("id")
            # После восстановления сразу обновим таблицу ссылок для восстановленной категории
            try:
                self.main.structure.update_links_table(category_id)
            except Exception:
                pass
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.select_category(category_id)
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
                    # Проставим флаг '__from_undo__' в данные, чтобы UI не переключал фокус
                    cat_payload = dict(self._backup_tree.get("category") or {})
                    try:
                        cat_payload["__from_undo__"] = True
                    except Exception:
                        pass
                    business.item_added.emit(
                        "category",
                        self.category.get("section_id"),
                        cat_payload,
                    )
                    # Инкрементальное обновление — без полной перезагрузки
            except Exception:
                pass
            # Гарантируем немедленное обновление дерева после Undo за счёт перезагрузки структуры и категорий раздела
            try:
                section_id = self.category.get("section_id")
                business = getattr(self.main, "structure_business", None)
                if business:
                    try:
                        business._invalidate_categories_cache(section_id)
                    except Exception:
                        pass
                    try:
                        business._invalidate_structure_cache()
                    except Exception:
                        pass
                    business._schedule_structure_reload(0)
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
        dc = getattr(main_window, "database_controller", None)
        self.db = getattr(dc, "db", None)
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
        # Глобальная защита от удалений на время чувствительных операций (например, вставки)
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug("[DeleteGuard] DeleteCategoriesBatchCmd.redo suppressed by _suppress_deletes flag")
                return
        except Exception:
            pass
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
            # 1) Удаляем все категории одной операцией и эмитим точечные события
            ids = [c.get("id") for c in self.categories if c.get("id") is not None]
            # Сохраним section_id для финального фокуса (берём последний валидный)
            for cat in self.categories:
                sid = cat.get("section_id")
                if sid is not None:
                    section_id_for_focus = sid
            try:
                self.structure_service.delete_categories_bulk(ids)
            except Exception:
                # Если bulk не удался, пробуем поштучно как fallback
                for cid in ids:
                    try:
                        self.structure_service.delete_category(cid)
                    except Exception:
                        pass
            # Точечные события для UI по каждому ID
            for cid in ids:
                try:
                    if business:
                        business.item_deleted.emit("category", cid)
                except Exception:
                    pass
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
            if section_id_for_focus is not None and business:
                business.select_section(section_id_for_focus)
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
                # Инкрементальное обновление — без полной перезагрузки
        except Exception:
            pass

    def undo(self):
        # Восстанавливаем категории из бэкапов одним bulk-вызовом (одна транзакция),
        # без тяжёлых перезагрузок/сигналов на каждом элементе
        business = getattr(self.main, "structure_business", None)
        section_id_for_focus = None
        category_id_for_focus = None
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
            # 1) Импорт всех деревьев в одной транзакции
            try:
                self.structure_service.import_category_trees_bulk(self._backups)
            except Exception:
                # Если bulk не удался, частично ничего не делаем (UI продолжит жить)
                pass
            # 2) Определим раздел для финального фокуса (берём из первого валидного бэкапа)
            for backup in self._backups:
                if backup and backup.get("category"):
                    section_id_for_focus = backup["category"].get("section_id")
                    category_id_for_focus = backup["category"].get("id")
                    if section_id_for_focus is not None:
                        break
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
            # Фокусируем раздел без полной перезагрузки дерева
            if section_id_for_focus is not None and business:
                business.select_section(section_id_for_focus)
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
                # ВАЖНО: также выберем одну из восстановленных категорий, чтобы таблица ссылок обновилась сразу
                try:
                    if category_id_for_focus is not None:
                        business.select_category(category_id_for_focus)
                        try:
                            self.main.structure.update_links_table(category_id_for_focus)
                        except Exception:
                            pass
                except Exception:
                    pass
                # Инкрементальное обновление — без полной перезагрузки
        except Exception:
            pass

        # ВАЖНО: дерево должно получить событие полной перезагрузки,
        # т.к. в bulk-Undo мы не эмитили item_added для каждой категории
        try:
            if business:
                try:
                    business._invalidate_structure_cache()
                except Exception:
                    pass
                # Немедленная перезагрузка структуры сферы -> придёт structure_loaded
                business._schedule_structure_reload(0)
        except Exception:
            pass
