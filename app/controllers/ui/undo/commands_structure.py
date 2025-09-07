# app/utils/system/undo/commands_structure.py
from __future__ import annotations

import logging
from typing import Dict, Optional

from app.controllers.ui.undo.base import BaseCommand, log_command
from app.services.structure_service import StructureService
from app.utils.ui.icon.cache_manager import clear_icon_cache

logger = logging.getLogger(__name__)

class SaveSectionCmd(BaseCommand):
    """Сохранение (создание/редактирование) раздела.
    Тонкая обёртка над DB с эмиссией сигналов business-слоя для UI.
    """

    def __init__(self, new_data: Dict, old_data: Optional[Dict], main_window):
        super().__init__("Save section", main_window)
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
        except Exception as exc:
            logger.warning("SaveSectionCmd._emit_reload: failed to emit update signals: %s", exc, exc_info=True)

    @log_command
    def redo(self):
        # Глобальная защита от удалений на время чувствительных операций (например, вставки)
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug("[DeleteGuard] DeleteSectionCmd.redo suppressed by _suppress_deletes flag")
                return
        except Exception as exc:
            logger.debug("SaveSectionCmd.redo: delete guard check failed: %s", exc)
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
                business.section_selected.emit(self.new_id)
        except Exception as exc:
            logger.warning("SaveCategoryCmd.redo: select_category failed: %s", exc)
        self._emit_reload()

    @log_command
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
                except Exception as exc:
                    logger.warning("SaveSectionCmd.undo: item_deleted emit failed: %s", exc)
        else:
            # откат редактирования – восстанавливаем старые данные
            if self.old_data:
                self.structure_service.update_section(
                    self.old_data["id"], self.old_data
                )
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.section_selected.emit(self.old_data["id"]) 
                except Exception as exc:
                    logger.warning("SaveSectionCmd.undo: select_section failed: %s", exc)
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_updated.emit(
                            "section", self.old_data["id"], self.old_data
                        )
                        # Инкрементальное обновление — без полной перезагрузки
                except Exception as exc:
                    logger.warning("SaveSectionCmd.undo: item_updated emit failed: %s", exc)


class DeleteSectionCmd(BaseCommand):
    """Удаление раздела с поддержкой полноценного восстановления (раздел+категории+ссылки)."""

    def __init__(self, section_data: Dict, main_window):
        super().__init__("Delete section", main_window)
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
        except Exception as exc:
            logger.debug("DeleteSectionCmd.redo: item_deleted emit failed: %s", exc, exc_info=True)

    def undo(self):
        try:
            self.structure_service.import_section_tree(self._backup_tree)
            section_id = self._backup_tree["section"]["id"]
            # Если есть восстановленные категории — выберем первую
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
                        business = getattr(self.main, "structure_business", None)
                        if business:
                            business.select_category(cat_id)
                    except Exception as exc:
                        logger.debug("DeleteSectionCmd.undo: select_category failed: %s", exc, exc_info=True)
            except Exception as exc:
                logger.warning("DeleteSectionCmd.undo: categories handling failed: %s", exc)
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.section_selected.emit(section_id)
            except Exception as exc:
                logger.warning("DeleteSectionCmd.undo: select_section failed: %s", exc)
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.item_added.emit(
                        "section", section_id, self._backup_tree["section"]
                    )
                    # Инкрементальное обновление — без полной перезагрузки
            except Exception as exc:
                logger.debug("DeleteSectionCmd.undo: item_added emit failed: %s", exc, exc_info=True)
            # Полной перезагрузки структуры не требуется: выше отправлены необходимые сигналы
        except Exception as exc:
            # В случае сбоя восстановления — оставляем как есть, без исключений в UI
            logger.exception("DeleteSectionCmd.undo: restore failed: %s", exc)


class SaveCategoryCmd(BaseCommand):
    """Сохранение (создание/редактирование) категории."""

    def __init__(
        self,
        new_data: Dict,
        old_data: Optional[Dict],
        main_window,
        *,
        skip_reload: bool = False,
    ):
        super().__init__("Save category", main_window)
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
                except Exception as exc:
                    logger.warning("SaveCategoryCmd._emit_reload: clear_icon_cache failed: %s", exc)
                if self.is_new:
                    # Для категорий второй аргумент — parent_id (section_id)
                    parent_id = self.new_data.get("section_id")
                    business.item_added.emit("category", parent_id, self.new_data)
                else:
                    business.item_updated.emit("category", self.new_id, self.new_data)
                # Полная перезагрузка больше не требуется — модель обновится через сигналы
        except Exception as exc:
            logger.warning("SaveCategoryCmd._emit_reload: emit failed: %s", exc)

    @log_command
    def redo(self):
        if self.is_new:
            result = self.structure_service.create_category(self.new_data)
            if result:
                self.new_id = result
                self.new_data["id"] = result
        else:
            # Диалог может вернуть неполный payload. Для корректного апдейта
            # гарантируем наличие обязательных полей.
            try:
                if self.old_data:
                    for k in ("id", "section_id", "position", "icon_path"):
                        if k not in self.new_data and k in self.old_data:
                            self.new_data[k] = self.old_data[k]
                    # Подставим name, если диалог его не вернул вовсе
                    if "name" not in self.new_data and "name" in self.old_data:
                        self.new_data["name"] = self.old_data["name"]
            except Exception as exc:
                logger.debug("SaveCategoryCmd.redo: payload normalization failed: %s", exc, exc_info=True)
            self.structure_service.update_category(
                self.new_data.get("id"), self.new_data
            )
            self.new_id = self.new_data.get("id")
        try:
            if not self.skip_reload:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.select_category(self.new_id)
        except Exception as exc:
            logger.warning("SaveCategoryCmd.redo: select_category failed: %s", exc)
        self._emit_reload()

    @log_command
    def undo(self):
        if self.is_new:
            section_id = self.new_data.get("section_id")
            if self.new_id:
                self.structure_service.delete_category(self.new_id)
            try:
                if not self.skip_reload:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.section_selected.emit(section_id)
            except Exception as exc:
                logger.warning("SaveCategoryCmd.undo: select_section failed: %s", exc)
            try:
                business = getattr(self.main, "structure_business", None)
                if business:
                    business.item_deleted.emit("category", self.new_id)
                    # Инкрементальное обновление — без полной перезагрузки
            except Exception as exc:
                logger.warning("SaveCategoryCmd.undo: item_deleted emit failed: %s", exc)
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
                except Exception as exc:
                    logger.warning("SaveCategoryCmd.undo: select_category failed: %s", exc)
                try:
                    business = getattr(self.main, "structure_business", None)
                    if business:
                        business.item_updated.emit(
                            "category", self.old_data["id"], self.old_data
                        )
                        # Инкрементальное обновление — без полной перезагрузки
                except Exception as exc:
                    logger.warning("SaveCategoryCmd.undo: item_updated emit failed: %s", exc)


class DeleteCategoryCmd(BaseCommand):
    """Удаление категории с восстановлением поддерева (категория+ссылки)."""

    def __init__(
        self,
        category_data: Dict,
        main_window,
        *,
        skip_reload: bool = False,
        lightweight_reload: bool = False,
    ):
        super().__init__("Delete category", main_window)
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

    @log_command
    def redo(self):
        # Глобальная защита от удалений на время чувствительных операций (например, вставки)
        try:
            if getattr(self.main, "_suppress_deletes", False):
                logger.debug("[DeleteGuard] DeleteCategoryCmd.redo suppressed by _suppress_deletes flag")
                return
        except Exception as exc:
            logger.debug("DeleteCategoryCmd.redo: delete guard check failed: %s", exc, exc_info=True)
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
            except Exception as exc:
                logger.warning("DeleteCategoryCmd.redo(skip_reload): item_deleted emit failed: %s", exc)
            return

        if self.lightweight_reload:
            # Облегчённый режим: точечные обновления без полной перезагрузки структуры
            # Фокус на раздел без полной перезагрузки дерева
            try:
                if business:
                    business.section_selected.emit(section_id)
            except Exception as exc:
                logger.warning("DeleteCategoryCmd.redo(lightweight): select_section failed: %s", exc)
            try:
                if business:
                    try:
                        business._invalidate_categories_cache(section_id)
                    except Exception as exc:
                        logger.debug("DeleteCategoryCmd.redo(lightweight): invalidate cache failed: %s", exc)
                    business.section_selected.emit(section_id)
                    # В lightweight-режиме не вызываем clear_icon_cache() и load_structure()
                    business.item_deleted.emit("category", category_id)
            except Exception as exc:
                logger.warning("DeleteCategoryCmd.redo(lightweight): updates failed: %s", exc)
            return

        # Обычный одиночный сценарий: корректно обновляем UI и данные
        try:
            if business:
                # Критично: инвалидируем кэш категорий раздела, иначе select_section
                # может взять устаревшие данные из categories_{section_id}
                try:
                    # внутренний метод, но безопасен для вызова из команды
                    business._invalidate_categories_cache(section_id)
                except Exception as exc:
                    logger.debug("DeleteCategoryCmd.redo: invalidate cache failed: %s", exc)
                business.section_selected.emit(section_id)
        except Exception as exc:
            logger.warning("DeleteCategoryCmd.redo: select_section failed: %s", exc)
        try:
            if business:
                # При удалении также сбрасываем кэш иконок категорий
                try:
                    clear_icon_cache()
                except Exception as exc:
                    logger.debug("DeleteCategoryCmd.redo: clear_icon_cache failed: %s", exc)
                business.item_deleted.emit("category", category_id)
                # Инкрементальное обновление — без полной перезагрузки
        except Exception as exc:
            logger.warning("DeleteCategoryCmd.redo: item_deleted emit failed: %s", exc)

    @log_command
    def undo(self):
        try:
            self.structure_service.import_category_tree(self._backup_tree)
            category_id = self.category.get("id")
            # После восстановления выбираем категорию через бизнес-логику (UI обновится через подписчиков)
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
            # Полной перезагрузки структуры не требуется: выше отправлены точечные сигналы и выполнены выборы
        except Exception as exc:
            # В случае сбоя восстановления — оставляем как есть
            logger.exception("DeleteCategoryCmd.undo: restore failed: %s", exc)


class DeleteCategoriesBatchCmd(BaseCommand):
    """Пакетное удаление нескольких категорий одной операцией.

    - Удаляет категории по списку ID через сервис одной транзакцией без промежуточных перезагрузок UI
    - Не эмитит per-item события удаления; выполняет одну финальную перезагрузку UI/плиток
    - Поддерживает undo через восстановление сохранённых бэкапов поддеревьев
    """

    def __init__(self, categories_data: list[Dict], main_window):
        super().__init__("Delete categories (batch)", main_window)
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
            except Exception as exc:
                logger.warning("DeleteCategoriesBatchCmd.__init__: export backup failed: %s", exc)
                backup = None
            self._backups.append(backup)

    @log_command
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
            ids_dbg = [c.get("id") for c in self.categories if c.get("id") is not None]
            logger.debug("[BatchRedo:start] cmd_id=%s items=%s", hex(id(self)), len(ids_dbg))
        except Exception as exc:
            logger.debug("DeleteCategoriesBatchCmd.redo: start logging failed: %s", exc, exc_info=True)
        try:
            struct = getattr(self.main, "structure", None)
            tree = getattr(struct, "tree", None)
            selection = getattr(struct, "selection_handler", None)
            if selection is not None:
                try:
                    selection.begin_suppress_selection()
                except Exception as exc:
                    logger.debug("DeleteCategoriesBatchCmd.redo: begin_suppress_selection failed: %s", exc, exc_info=True)
            if tree is not None:
                tree.blockSignals(True)
        except Exception as exc:
            tree = None
            logger.debug("DeleteCategoriesBatchCmd.redo: suppress selection failed: %s", exc)
        try:
            # 1) Удаляем все категории одной операцией БЕЗ per-item сигналов
            ids = [c.get("id") for c in self.categories if c.get("id") is not None]
            # Сохраним section_id для финального фокуса (берём последний валидный)
            for cat in self.categories:
                sid = cat.get("section_id")
                if sid is not None:
                    section_id_for_focus = sid
            try:
                self.structure_service.delete_categories_bulk(ids)
                logger.debug("[BatchRedo:deleted] cmd_id=%s bulk_ok ids=%s", hex(id(self)), len(ids))
            except Exception:
                # Если bulk не удался, пробуем поштучно как fallback
                for cid in ids:
                    try:
                        self.structure_service.delete_category(cid)
                    except Exception as exc2:
                        logger.warning("DeleteCategoriesBatchCmd.redo: delete_category failed for %s: %s", cid, exc2)
                logger.debug("[BatchRedo:deleted] cmd_id=%s fallback ids=%s", hex(id(self)), len(ids))
            # ВАЖНО: не эмитим per-item item_deleted, чтобы redo был пакетным, как undo
        finally:
            # 2) Одна финальная перезагрузка/фокус
            # ВАЖНО: перед финальными обновлениями возвращаем сигналы/обработку
            try:
                if tree is not None:
                    tree.blockSignals(False)
            except Exception as exc:
                logger.debug("DeleteCategoriesBatchCmd.redo: unblock tree signals failed: %s", exc, exc_info=True)
            try:
                if selection is not None:
                    selection.end_suppress_selection()
            except Exception as exc:
                logger.debug("DeleteCategoriesBatchCmd.redo: end_suppress_selection failed: %s", exc, exc_info=True)
        # Убираем ранний вызов select_section: фокус устанавливается ниже, после очистки кэша
        try:
            if business:
                try:
                    clear_icon_cache()
                except Exception as exc:
                    logger.debug("DeleteCategoriesBatchCmd.redo: clear_icon_cache failed: %s", exc)
                if section_id_for_focus is not None:
                    try:
                        business._invalidate_categories_cache(section_id_for_focus)
                    except Exception as exc:
                        logger.debug("DeleteCategoriesBatchCmd.redo: invalidate cache failed: %s", exc)
                    business.select_section(section_id_for_focus)
                # Единый батч-сигнал вместо per-item и вместо ручной глобальной перезагрузки
                try:
                    ids_payload = [c.get("id") for c in self.categories if c.get("id") is not None]
                    business.items_batch_deleted.emit("category", ids_payload)
                    logger.debug(
                        "[BatchRedo:signal] cmd_id=%s ids=%s section_focus=%s",
                        hex(id(self)),
                        len(ids_payload),
                        section_id_for_focus,
                    )
                except Exception as exc:
                    logger.warning("DeleteCategoriesBatchCmd.redo: items_batch_deleted emit failed: %s", exc)
        except Exception as exc:
            logger.warning("DeleteCategoriesBatchCmd.redo: final updates failed: %s", exc)
        logger.debug("[BatchRedo:done] cmd_id=%s section_focus=%s", hex(id(self)), section_id_for_focus)

    @log_command
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
            restored_cnt = len([b for b in self._backups if b])
            logger.debug("[BatchUndo:start] cmd_id=%s backups=%s", hex(id(self)), restored_cnt)
        except Exception as exc:
            logger.debug("DeleteCategoriesBatchCmd.undo: start logging failed: %s", exc, exc_info=True)
        try:
            struct = getattr(self.main, "structure", None)
            tree = getattr(struct, "tree", None)
            selection = getattr(struct, "selection_handler", None)
            if selection is not None:
                try:
                    selection.begin_suppress_selection()
                except Exception as exc:
                    logger.debug("DeleteCategoriesBatchCmd.undo: begin_suppress_selection failed: %s", exc, exc_info=True)
            if tree is not None:
                tree.blockSignals(True)
        except Exception as exc:
            tree = None
            logger.debug("DeleteCategoriesBatchCmd.undo: suppress selection failed: %s", exc, exc_info=True)
        try:
            # 1) Импорт всех деревьев в одной транзакции
            try:
                self.structure_service.import_category_trees_bulk(self._backups)
                logger.debug("[BatchUndo:imported] cmd_id=%s backups=%s", hex(id(self)), len(self._backups))
            except Exception as exc:
                # Если bulk не удался, частично ничего не делаем (UI продолжит жить)
                logger.warning("DeleteCategoriesBatchCmd.undo: import bulk failed: %s", exc)
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
                business.section_selected.emit(section_id_for_focus)
        except Exception as exc:
            logger.debug("DeleteCategoriesBatchCmd.undo: section_selected emit failed: %s", exc, exc_info=True)

        try:
            if business:
                # По аналогии с redo: инвалидация кэша категорий выбранного раздела
                if section_id_for_focus is not None:
                    try:
                        business._invalidate_categories_cache(section_id_for_focus)
                    except Exception as exc:
                        logger.debug("DeleteCategoriesBatchCmd.undo: invalidate cache failed: %s", exc, exc_info=True)
                    business.section_selected.emit(section_id_for_focus)
                # ВАЖНО: также выберем одну из восстановленных категорий, чтобы таблица ссылок обновилась сразу
                try:
                    if category_id_for_focus is not None:
                        business.select_category(category_id_for_focus)
                except Exception as exc:
                    logger.debug("DeleteCategoriesBatchCmd.undo: select_category failed: %s", exc, exc_info=True)
                # Инкрементальное обновление — без полной перезагрузки
        except Exception as exc:
            logger.debug("DeleteCategoriesBatchCmd.undo: final updates failed: %s", exc, exc_info=True)

        # ВАЖНО: дерево должно получить событие полной перезагрузки
        try:
            if business:
                try:
                    business._invalidate_structure_cache()
                except Exception as exc:
                    logger.debug("DeleteCategoriesBatchCmd.undo: invalidate structure cache failed: %s", exc, exc_info=True)
                # Немедленная перезагрузка структуры сферы -> придёт structure_loaded
                business._schedule_structure_reload(0)
                logger.debug(
                    "[BatchUndo:reload] cmd_id=%s section_focus=%s category_focus=%s",
                    hex(id(self)),
                    section_id_for_focus,
                    category_id_for_focus,
                )
        except Exception as exc:
            logger.debug("DeleteCategoriesBatchCmd.undo: schedule reload failed: %s", exc, exc_info=True)

        logger.debug(
            "[BatchUndo:done] cmd_id=%s section_focus=%s category_focus=%s",
            hex(id(self)),
            section_id_for_focus,
            category_id_for_focus,
        )
