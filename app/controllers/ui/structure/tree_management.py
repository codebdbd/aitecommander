# app/controllers/structure/tree_management.py

from PyQt6.QtCore import QModelIndex, Qt
import logging

from app.controllers.ui.state.task_scheduler import schedule_selection_restore, schedule_focus
from app.utils.ui.qt.roles import get_tree_tuple


logger = logging.getLogger(__name__)


class TreeManagement:
    def __init__(self, controller, category_tiles_controller):
        self.controller = controller
        self.tree = controller.tree
        self.icon_handler = controller.icon_handler
        # Явная обязательная зависимость: контроллер плиток категорий
        if category_tiles_controller is None:
            raise ValueError("TreeManagement requires a non-None category_tiles_controller")
        self.tiles_controller = category_tiles_controller

    def _on_structure_loaded(self, sections_data: list) -> None:
        # Сохраняем текущее выделение и состояние разворота до перезагрузки модели
        cur_index = self.tree.currentIndex()
        current_selection = (
            get_tree_tuple(cur_index, 0) if cur_index and cur_index.isValid() else None
        )

        expanded_state = self._save_expanded_state_model()

        # Сортируем разделы по имени (без учета регистра) перед передачей в модель
        try:
            sections_data = sorted(
                sections_data or [], key=lambda s: (s.get("name") or "").lower()
            )
        except Exception:
            logger.exception("TreeManagement._on_structure_loaded: ошибка сортировки разделов")

        # Обновляем модель одним снимком
        model = self.tree.model()
        if model and hasattr(model, "set_snapshot"):
            model.set_snapshot(sections_data or [])

        # Восстанавливаем развёрнутость
        self._restore_expanded_state_model(expanded_state)

        # Восстанавливаем выделение, если оно существовало
        if current_selection:
            item_type, item_id = current_selection
            if item_type in ("section", "category") and isinstance(item_id, int):
                self.controller.selection_handler._restore_selection_after_load(
                    item_type, item_id
                )
        else:
            self.controller.selection_handler._select_first_item_if_needed()

        # После обновления модели проставляем иконки через IconHandling для QTreeView
        try:
            if hasattr(self.controller, "icon_handler") and self.controller.icon_handler:
                self.controller.icon_handler.reload_icons()
        except Exception:
            logger.exception("TreeManagement._on_structure_loaded: ошибка перезагрузки иконок")

        # После первой загрузки структуры обновляем отображение главного окна
        if hasattr(self.controller, "main") and getattr(
            self.controller.main, "_first_structure_load", False
        ):
            self.controller.main._first_structure_load = False
            self.tree.updateGeometry()
            self.tree.update()

    def _on_item_added(self, item_type: str, parent_id: int, data: dict) -> None:
        # Инкрементальная вставка через модель
        # Примечание: при ошибке вставки требуется полная перезагрузка структуры —
        # ожидаемые ошибки модели (ValueError, RuntimeError) логируем и пробрасываем вверх,
        # неожиданные исключения также не подавляются.
        model = getattr(self.tree, "model", lambda: None)()
        if not model:
            return
        if item_type == "section":
            # Вставляем раздел в конец (или позицию из data.get('row'))
            row = int(data.get("row")) if isinstance(data.get("row"), int) else -1
            try:
                model.insert_sections(row, [data])
            except (ValueError, RuntimeError):
                logger.exception(
                    "TreeManagement._on_item_added: ошибка инкрементальной вставки section"
                )
                raise
        elif item_type == "category" and isinstance(parent_id, int):
            row = int(data.get("row")) if isinstance(data.get("row"), int) else -1
            try:
                model.insert_categories(parent_id, row, [data])
            except (ValueError, RuntimeError):
                logger.exception(
                    "TreeManagement._on_item_added: ошибка инкрементальной вставки category"
                )
                raise
            # Обновим плитки выбранного раздела, если это не Undo вставка
            # Флаг '__from_undo__' добавляется отправителем сигнала, чтобы избежать смены фокуса
            if not bool(data.get("__from_undo__")):
                self.refresh_section_tiles(parent_id)

        # Сфокусируемся на новом элементе
        item_id = data.get("id")
        if isinstance(item_id, int):
            schedule_selection_restore(
                lambda: self.controller.selection_handler._set_focus_on_new_item_by_id(
                    item_type, item_id
                ),
                f"new_{item_type}_{item_id}",
            )
            # Дополнительно восстановим фокус на дереве
            try:
                schedule_focus(lambda: self.tree.setFocus(), "structure_tree")
            except Exception:
                pass

    def _on_item_updated(self, item_type: str, item_id: int, data: dict) -> None:
        # Инкрементальное обновление
        model = getattr(self.tree, "model", lambda: None)()
        if model:
            try:
                model.update_item(item_type, item_id, data or {})
            except Exception:
                logger.exception(
                    "TreeManagement._on_item_updated: ошибка обновления элемента %s #%s",
                    item_type,
                    item_id,
                )
        # Сохраняем UX восстановления выделения категории
        if item_type == "category" and isinstance(item_id, int):
            schedule_selection_restore(
                lambda: self.controller.selection_handler._restore_category_selection(
                    item_id
                ),
                f"restore_cat_{item_id}",
            )
            # Дополнительно восстановим фокус на дереве
            try:
                schedule_focus(lambda: self.tree.setFocus(), "structure_tree")
            except Exception:
                pass

    def _on_item_deleted(self, item_type: str, item_id: int) -> None:
        # Инкрементальное удаление
        model = getattr(self.tree, "model", lambda: None)()
        if model:
            try:
                if item_type == "section":
                    model.remove_sections([int(item_id)])
                elif item_type == "category":
                    model.remove_categories([int(item_id)])
            except Exception:
                logger.exception(
                    "TreeManagement._on_item_deleted: ошибка удаления элемента %s #%s",
                    item_type,
                    item_id,
                )
        # Если удалили категорию и сейчас выбран раздел — обновим плитки для него.
        if item_type == "category":
            try:
                cur = self.tree.currentIndex()
                t = get_tree_tuple(cur, 0) if cur and cur.isValid() else None
                if t and t[0] == "section":
                    section_id = t[1]
                    self.refresh_section_tiles(section_id)
            except Exception:
                logger.exception("TreeManagement._on_item_deleted: ошибка обновления плиток после удаления категории")
        # Гарантируем восстановление фокуса на дереве после удаления
        try:
            schedule_focus(lambda: self.tree.setFocus(), "structure_tree")
        except Exception:
            pass

    def refresh_section_tiles(self, section_id: int) -> None:
        """Обновить плитки раздела через переданный CategoryTilesController."""
        try:
            self.tiles_controller.refresh(int(section_id))
        except (ValueError, RuntimeError):
            # Ожидаемые ошибки контроллера плиток логируем и продолжаем работу UI
            logger.exception("TreeManagement.refresh_section_tiles: controller refresh failed (expected)")
        # Неожиданные исключения — не подавляем, пусть упадут до тестов/CI

    def _iter_indexes(self, parent: QModelIndex = QModelIndex()):
        model = self.tree.model()
        if not model:
            return
        rows = model.rowCount(parent)
        for r in range(rows):
            idx = model.index(r, 0, parent)
            if idx.isValid():
                yield idx
                yield from self._iter_indexes(idx)

    def _save_expanded_state_model(self) -> dict:
        expanded_state = {}
        try:
            for idx in self._iter_indexes():
                # Сохраняем только узлы, у которых есть дети
                model = self.tree.model()
                if model and model.rowCount(idx) > 0:
                    key = get_tree_tuple(idx, 0)
                    if key:
                        expanded_state[key] = self.tree.isExpanded(idx)
        except Exception:
            logger.exception(
                "TreeManagement._save_expanded_state_model: ошибка сохранения состояния разворота"
            )
        return expanded_state

    def _restore_expanded_state_model(self, expanded_state: dict) -> None:
        if not expanded_state:
            return
        model = self.tree.model()
        if not model or not hasattr(model, "index_for"):
            return
        try:
            for (typ, id_), state in expanded_state.items():
                idx = model.index_for(typ, id_)
                if idx and idx.isValid():
                    self.tree.setExpanded(idx, bool(state))
        except Exception:
            logger.exception(
                "TreeManagement._restore_expanded_state_model: ошибка восстановления состояния разворота"
            )

    def _find_item_by_id(self, item_type: str, item_id: int):
        """Возвращает QModelIndex элемента по типу ('section'|'category') и id.

        Совместимый хелпер для вызовов из `ItemOperations` и действий меню.
        """
        try:
            model = getattr(self.tree, "model", lambda: None)()
            if not model or not hasattr(model, "index_for"):
                return None
            idx = model.index_for(item_type, int(item_id))
            if idx and idx.isValid():
                return idx
        except Exception:
            logger.exception(
                "TreeManagement._find_item_by_id: ошибка поиска элемента %s #%s",
                item_type,
                item_id,
            )
        return None

    # Сортировка переносится в сборку снапшота модели; дополнительных действий во view не требуется

    def _sort_tree(self) -> None:
        """Сортирует категории внутри каждого раздела по имени (case-insensitive).

        Поддерживает QTreeView с моделью `StructureTreeModel`.
        Сохраняет текущее выделение и состояние разворота.
        """
        model = getattr(self.tree, "model", lambda: None)()
        if not model:
            return

        # Сохраняем текущее выделение и развёрнутость
        cur_index = self.tree.currentIndex()
        current_selection = (
            get_tree_tuple(cur_index, 0) if cur_index and cur_index.isValid() else None
        )
        expanded_state = self._save_expanded_state_model()

        try:
            # Собираем текущий снапшот из модели
            sections_data: list[dict] = []
            root_rows = model.rowCount(QModelIndex())
            for r in range(root_rows):
                s_idx = model.index(r, 0, QModelIndex())
                if not s_idx or not s_idx.isValid():
                    continue
                t = get_tree_tuple(s_idx, 0)
                if not t or t[0] != "section":
                    continue
                s_id = t[1]
                s_name = model.data(s_idx, Qt.ItemDataRole.DisplayRole) or ""
                s_icon = model.data(s_idx, Qt.ItemDataRole.DecorationRole)

                # Собираем категории раздела
                cats: list[dict] = []
                child_rows = model.rowCount(s_idx)
                for i in range(child_rows):
                    c_idx = model.index(i, 0, s_idx)
                    if not c_idx or not c_idx.isValid():
                        continue
                    ct = get_tree_tuple(c_idx, 0)
                    if not ct or ct[0] != "category":
                        continue
                    c_id = ct[1]
                    c_name = model.data(c_idx, Qt.ItemDataRole.DisplayRole) or ""
                    c_icon = model.data(c_idx, Qt.ItemDataRole.DecorationRole)
                    cats.append({"id": c_id, "name": c_name, "icon": c_icon})

                # Сортируем категории по имени без учета регистра
                try:
                    cats.sort(key=lambda c: (c.get("name") or "").lower())
                except Exception:
                    pass

                sections_data.append(
                    {
                        "id": s_id,
                        "name": s_name,
                        "icon": s_icon,
                        "categories": cats,
                    }
                )

            # Обновляем модель единым снапшотом
            if hasattr(model, "set_snapshot"):
                model.set_snapshot(sections_data)

            # Восстановление разворота и выделения
            self._restore_expanded_state_model(expanded_state)
            if current_selection:
                item_type, item_id = current_selection
                if item_type in ("section", "category") and isinstance(item_id, int):
                    self.controller.selection_handler._restore_selection_after_load(
                        item_type, item_id
                    )
        except Exception:
            # Безопасный fallback: ничего не делаем
            pass

    def on_structure_item_changed(
        self, item_type: str, item_id: int, data: dict
    ) -> None:
        self._on_item_updated(item_type, item_id, data)

    def on_structure_item_added(
        self, item_type: str, parent_id: int, data: dict
    ) -> None:
        self._on_item_added(item_type, parent_id, data)

    def _update_category_display(self, category_id: int, new_data: dict) -> None:
        """Отображение обновится после перезагрузки модели; плитки обновим через бизнес-логику."""
        if hasattr(self.controller, "business"):
            try:
                hier = self.controller.business.get_category_hierarchy(category_id)
                if hier and "section_id" in hier:
                    self.refresh_section_tiles(int(hier["section_id"]))
            except Exception:
                logger.exception("TreeManagement._update_category_display: ошибка обновления плиток по иерархии категории #%s", category_id)

    def _update_category_tiles_after_edit(self, _category_index: QModelIndex | None = None) -> None:
        """Обновляет плитки категорий после редактирования категории."""
        # Определим текущий раздел по текущему индексу и обновим плитки
        try:
            cur = self.tree.currentIndex()
            if cur and cur.isValid():
                # Если выделена категория — берём её родителя (раздел)
                t = get_tree_tuple(cur, 0)
                if t and t[0] == "category":
                    parent = cur.parent()
                else:
                    parent = cur
                pt = get_tree_tuple(parent, 0)
                if pt and pt[0] == "section":
                    self.refresh_section_tiles(pt[1])
        except Exception:
            logger.exception("TreeManagement._update_category_tiles_after_edit: ошибка обновления плиток")

    def _update_section_tiles_after_edit(self, _section_index: QModelIndex | None = None) -> None:
        """Обновляет плитки категорий после редактирования раздела."""
        try:
            cur = self.tree.currentIndex()
            if cur and cur.isValid():
                t = get_tree_tuple(cur, 0)
                if t and t[0] == "section":
                    self.refresh_section_tiles(t[1])
        except Exception:
            logger.exception("TreeManagement._update_section_tiles_after_edit: ошибка обновления плиток")
