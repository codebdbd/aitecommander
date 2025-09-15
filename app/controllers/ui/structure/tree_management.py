# app/controllers/structure/tree_management.py

import logging
import copy

from PyQt6.QtCore import QModelIndex, Qt, QSignalBlocker

from app.controllers.ui.state.task_scheduler import (
    schedule_focus,
    schedule_selection_restore,
)
from app.utils.ui.qt.roles import get_tree_tuple
from app.utils.ui.updates import suspend_updates
from app.utils.ui.qt.signal_blockers import block_tree_signals
from app.controllers.ui.structure.icon_handling import prepare_icons_snapshot

logger = logging.getLogger(__name__)


class TreeManagement:
    def __init__(self, controller, category_tiles_controller):
        self.controller = controller
        self.tree = controller.tree
        self.icon_handler = controller.icon_handler
        # Явная обязательная зависимость: контроллер плиток категорий
        if category_tiles_controller is None:
            raise ValueError(
                "TreeManagement requires a non-None category_tiles_controller"
            )
        self.tiles_controller = category_tiles_controller

        # Явная ссылка на модель дерева и проверка контракта
        try:
            model_getter = getattr(self.tree, "model")
            self.model = model_getter() if callable(model_getter) else None
        except Exception:
            self.model = None
        if not self.model:
            raise ValueError("TreeManagement requires a valid tree model")
        # Проверяем наличие ключевых методов модели, используемых для инкрементальных операций
        required_methods = [
            "insert_sections",
            "insert_categories",
            "update_item",
        ]
        for m in required_methods:
            if not hasattr(self.model, m) or not callable(getattr(self.model, m)):
                raise ValueError(
                    f"TreeManagement requires a model providing methods: {', '.join(required_methods)}"
                )

    def _on_structure_loaded(self, sections_data: list | dict, *args) -> None:
        # Поддержка инкрементальных патчей: если передан dict с ключом 'op' == 'patch',
        # применяем изменения через инкрементальные методы модели без полной перезагрузки.
        if isinstance(sections_data, dict) and sections_data.get("op") == "patch":
            try:
                self._apply_patch(sections_data)
            except Exception:
                logger.debug("TreeManagement._on_structure_loaded: patch path failed", exc_info=True)
            return
        # Новый порядок: применяем снапшот немедленно, иконки обновляем отдельно асинхронно
        state = self._save_view_state()
        snapshot = self._prepare_snapshot(sections_data)

        # Применение структуры и восстановление UI сразу
        self._apply_snapshot(snapshot)
        self._restore_state(state)
        self._ensure_selection(state)
        self._notify_selection_handler()

        # Асинхронная установка иконок без блокировки UI
        try:
            ih = getattr(self.controller, "icon_handler", None)
            if ih and hasattr(ih, "reload_icons"):
                ih.reload_icons()
        except Exception:
            logger.debug("TreeManagement._on_structure_loaded: schedule icon reload failed", exc_info=True)


    def _save_view_state(self):
        """Сохраняет состояние дерева (развороты, скролл, выделение)."""
        try:
            return self.tree.saveState()
        except Exception:
            return None

    def _prepare_snapshot(self, sections_data: list | dict):
        """Готовит снапшот для модели: сортировка разделов и категорий (без подготовки иконок).

        ВАЖНО: не мутируем входные данные, полученные из бизнес-слоя — работаем на глубокой копии.
        """
        try:
            data = copy.deepcopy(sections_data) if sections_data is not None else []
        except Exception:
            # Fallback: создаём новый список с копиями словарей и вложенных категорий
            data = []
            try:
                for s in list(sections_data or []):
                    # Копия раздела
                    try:
                        s_copy = dict(s) if isinstance(s, dict) else s
                    except Exception:
                        s_copy = s
                    # Копия списка категорий (каждая категория — копия словаря)
                    cats = []
                    try:
                        raw_cats = s.get("categories") if isinstance(s, dict) else []
                        for c in list(raw_cats or []):
                            try:
                                cats.append(dict(c) if isinstance(c, dict) else c)
                            except Exception:
                                cats.append(c)
                    except Exception:
                        cats = []
                    if isinstance(s_copy, dict):
                        s_copy["categories"] = cats
                    data.append(s_copy)
            except Exception:
                data = []
        # Сортировка разделов по имени (case-insensitive)
        try:
            data = sorted(data or [], key=lambda s: (s.get("name") or "").lower())
        except Exception:
            logger.exception(
                "TreeManagement._on_structure_loaded: ошибка сортировки разделов"
            )
        # Сортировка категорий каждого раздела по имени (case-insensitive)
        try:
            if isinstance(data, list):
                for s in data:
                    try:
                        cats = s.get("categories") or []
                        if isinstance(cats, list) and cats:
                            s["categories"] = sorted(
                                cats, key=lambda c: (c.get("name") or "").lower()
                            )
                    except Exception:
                        # Не блокируем подготовку, просто продолжаем
                        continue
        except Exception:
            logger.debug(
                "TreeManagement._on_structure_loaded: ошибка сортировки категорий",
                exc_info=True,
            )
        return data

    def _apply_snapshot(self, snapshot: list | dict) -> None:
        """Применяет снапшот к модели и обновляет плитки при пустой структуре."""
        self._update_model_snapshot(snapshot)
        try:
            if not snapshot:
                self.tiles_controller.clear()
        except Exception:
            logger.exception(
                "TreeManagement._on_structure_loaded: ошибка очистки плиток при пустой структуре"
            )

    def _restore_state(self, state) -> None:
        """Безопасное восстановление состояния вида (если оно есть)."""
        if state:
            self._restore_view_state(state)

    def _ensure_selection(self, state) -> None:
        """Делегирует гарантию корректного выделения в SelectionHandling."""
        try:
            sh = getattr(self.controller, "selection_handler", None)
            if sh and hasattr(sh, "ensure_selection_after_load"):
                sh.ensure_selection_after_load(state)
            else:
                # Fallback: выбрать первый элемент при отсутствии состояния
                if not state and sh and hasattr(sh, "_select_first_item_if_needed"):
                    sh._select_first_item_if_needed()
        except Exception:
            # Не мешаем остальной последовательности, логируем в DEBUG
            logger.debug("TreeManagement._ensure_selection: delegate failed", exc_info=True)

        # После первой загрузки структуры обновляем отображение главного окна
        if hasattr(self.controller, "main") and getattr(
            self.controller.main, "_first_structure_load", False
        ):
            self.controller.main._first_structure_load = False
            with suspend_updates(self.tree):
                self.tree.updateGeometry()
                self.tree.update()

    def _apply_patch(self, patch: dict) -> None:
        """Применяет инкрементальные изменения к модели на основе словаря patch.

        Подавляет обновления UI и сигналы на время массовых операций. По завершении
        вручную уведомляет обработчик выбора, так как сигналы были заблокированы.
        """
        model = self.model
        if not model:
            return
        with suspend_updates(self.tree):
            # Подавляем сигналы на время массовых операций
            with block_tree_signals(self.tree):
                # Операции патча: удаление, вставка, обновление
                self._patch_remove(patch)
                self._patch_insert(patch)
                self._patch_update(patch)

        # После патча вручную уведомим обработчик выбора (сигналы были подавлены)
        self._notify_selection_handler()

    def _patch_remove(self, patch: dict) -> None:
        """Удаляет разделы и категории согласно секции 'remove' в patch."""
        model = self.model
        if not model:
            return
        try:
            removes = patch.get("remove") or {}
            secs_to_remove = list(removes.get("sections") or [])
            cats_to_remove = list(removes.get("categories") or [])
            if secs_to_remove:
                try:
                    model.remove_sections([int(x) for x in secs_to_remove])
                except Exception:
                    logger.debug("patch: remove_sections failed", exc_info=True)
            if cats_to_remove:
                try:
                    model.remove_categories([int(x) for x in cats_to_remove])
                except Exception:
                    logger.debug("patch: remove_categories failed", exc_info=True)
        except Exception:
            logger.debug("patch: remove phase failed", exc_info=True)

    def _patch_insert(self, patch: dict) -> None:
        """Вставляет разделы и категории согласно секции 'insert' в patch."""
        model = self.model
        if not model:
            return
        inserts = patch.get("insert") or {}

        # Разделы
        sec_inserts = list(inserts.get("sections") or [])
        if sec_inserts:
            for sec in list(sec_inserts):
                try:
                    _rv = sec.get("row") if isinstance(sec, dict) else None
                    row = _rv if isinstance(_rv, int) else -1
                    model.insert_sections(row, [sec])
                except Exception:
                    logger.debug("patch: insert_sections failed for section %s", getattr(sec, "get", lambda *_: None)("id") if isinstance(sec, dict) else None, exc_info=True)

        # Категории: { section_id: [ {data...}, ... ] }
        cat_inserts = inserts.get("categories") or {}
        try:
            for sid, items in (cat_inserts.items() if hasattr(cat_inserts, "items") else []):
                # Собираем пары (row, cat) и сортируем по row; -1 трактуем как append
                pairs = []
                for cat in list(items or []):
                    try:
                        _rv = cat.get("row") if isinstance(cat, dict) else None
                        row = _rv if isinstance(_rv, int) else -1
                    except Exception:
                        row = -1
                    pairs.append((row, cat))

                if not pairs:
                    continue

                def _row_key(rc):
                    r, _ = rc
                    return r if isinstance(r, int) and r >= 0 else 10**9

                pairs.sort(key=_row_key)
                ordered_cats = [c for (_r, c) in pairs]
                # first_row: минимальный неотрицательный, иначе -1 (append)
                nonneg = [r for (r, _c) in pairs if isinstance(r, int) and r >= 0]
                first_row = min(nonneg) if nonneg else -1
                try:
                    model.insert_categories(int(sid), first_row, ordered_cats)
                except Exception:
                    logger.debug(
                        "patch: insert_categories batch failed for section %s",
                        sid,
                        exc_info=True,
                    )
        except Exception:
            logger.debug("patch: iter cat inserts failed", exc_info=True)

    def _patch_update(self, patch: dict) -> None:
        """Обновляет разделы и категории согласно секции 'update' в patch."""
        model = self.model
        if not model:
            return
        updates = patch.get("update") or {}
        try:
            for sec in list(updates.get("sections") or []):
                try:
                    model.update_item("section", int(sec.get("id")), sec)
                except Exception:
                    logger.debug("patch: update section failed", exc_info=True)
            for cat in list(updates.get("categories") or []):
                try:
                    model.update_item("category", int(cat.get("id")), cat)
                except Exception:
                    logger.debug("patch: update category failed", exc_info=True)
        except Exception:
            logger.debug("patch: apply updates failed", exc_info=True)

    def _update_model_snapshot(self, sections_data: list | dict) -> None:
        """Обновляет снапшот модели с подавлением перерисовок и сигналов."""
        model = self.tree.model()
        if model and (hasattr(model, "update_snapshot") or hasattr(model, "set_snapshot")):
            with suspend_updates(self.tree):
                with block_tree_signals(self.tree):
                    if hasattr(model, "update_snapshot"):
                        model.update_snapshot(sections_data or [])
                    else:
                        model.set_snapshot(sections_data or [])

    def _restore_view_state(self, state) -> None:
        """Восстанавливает состояние дерева и обрабатывает одноразовый флаг подавления восстановления категории."""
        try:
            with suspend_updates(self.tree):
                with block_tree_signals(self.tree):
                    self.tree.restoreState(state)
                    # Особый случай: если бизнес-слой просил не восстанавливать выделение категории,
                    # не оставляем восстановленное выделение — очистим его здесь, под блокировкой сигналов
                    try:
                        sb = getattr(self.controller, "business", None) or getattr(
                            self.controller, "structure_business", None
                        )
                    except Exception:
                        sb = None
                    if sb and getattr(sb, "_suppress_category_restore_once", False):
                        try:
                            sel_model = self.tree.selectionModel()
                        except Exception:
                            sel_model = None
                        if sel_model:
                            try:
                                sel_model.clearSelection()
                            except Exception:
                                pass
                        try:
                            setattr(sb, "_suppress_category_restore_once", False)
                        except Exception:
                            pass
        except Exception:
            logger.debug("TreeManagement._on_structure_loaded: restoreState failed", exc_info=True)

    def _notify_selection_handler(self) -> None:
        """Ручное уведомление обработчика выбора о текущем элементе (currentChanged)."""
        try:
            from PyQt6.QtCore import QModelIndex as _QI
            cur = self.tree.currentIndex()
            prev = _QI()
            if hasattr(self.controller, "selection_handler") and cur is not None:
                self.controller.selection_handler._on_current_changed(cur, prev)
        except Exception:
            logger.debug(
                "TreeManagement._on_structure_loaded: manual currentChanged notify failed",
                exc_info=True,
            )

    def _on_item_added(self, item_type: str, parent_id: int, data: dict) -> None:
        # Инкрементальная вставка через модель
        # Примечание: при ошибке вставки требуется полная перезагрузка структуры —
        # ожидаемые ошибки модели (ValueError, RuntimeError) логируем и пробрасываем вверх,
        # неожиданные исключения также не подавляются.
        model = self.model
        if item_type == "section":
            # Вставляем раздел в конец (или позицию из data.get('row'))
            _row_val = data.get("row")
            row = _row_val if isinstance(_row_val, int) else -1
            try:
                model.insert_sections(row, [data])
            except (ValueError, RuntimeError):
                logger.exception(
                    "TreeManagement._on_item_added: ошибка инкрементальной вставки section"
                )
                raise
        elif item_type == "category" and isinstance(parent_id, int):
            _row_val = data.get("row")
            row = _row_val if isinstance(_row_val, int) else -1
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
                logger.debug(
                    "TreeManagement._on_item_added: schedule_focus failed",
                    exc_info=True,
                )

    def _on_item_updated(self, item_type: str, item_id: int, data: dict) -> None:
        # Инкрементальное обновление
        model = self.model
        try:
            model.update_item(item_type, item_id, data or {})
        except (ValueError, RuntimeError):
            logger.exception(
                "TreeManagement._on_item_updated: ошибка обновления элемента %s #%s",
                item_type,
                item_id,
            )
            raise
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
        model = self.model
        if not model:
            logger.error("TreeManagement._on_item_deleted: model is not available")
            return
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
        # Обновление плиток в зависимости от типа удалённого элемента
        if item_type == "category":
            # Если удалили категорию и сейчас выбран раздел — обновим плитки для него.
            try:
                cur = self.tree.currentIndex()
                t = get_tree_tuple(cur, 0) if cur and cur.isValid() else None
                if t and t[0] == "section":
                    section_id = t[1]
                    self.refresh_section_tiles(section_id)
            except Exception:
                logger.exception(
                    "TreeManagement._on_item_deleted: ошибка обновления плиток после удаления категории"
                )
        elif item_type == "section":
            # Если удалили раздел(ы):
            # - когда дерево стало пустым — очищаем плитки;
            # - если выбран какой-то раздел — обновим плитки по текущему разделу;
            # - иначе (нет выбранного раздела) — очищаем плитки.
            try:
                model = self.tree.model()
                if model and hasattr(model, "rowCount"):
                    if int(model.rowCount(QModelIndex())) == 0:
                        self.tiles_controller.clear()
                        # Больше делать нечего
                        pass
                    else:
                        cur = self.tree.currentIndex()
                        t = get_tree_tuple(cur, 0) if cur and cur.isValid() else None
                        if t and t[0] == "section":
                            self.refresh_section_tiles(t[1])
                        else:
                            # Нет выбранного раздела — сбрасываем плитки
                            self.tiles_controller.clear()
            except Exception:
                logger.exception(
                    "TreeManagement._on_item_deleted: ошибка обновления плиток после удаления раздела"
                )
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
            logger.exception(
                "TreeManagement.refresh_section_tiles: controller refresh failed (expected)"
            )
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

    def _find_item_by_id(self, item_type: str, item_id: int):
        """Возвращает QModelIndex элемента по типу ('section'|'category') и id.

        Совместимый хелпер для вызовов из `ItemOperations` и действий меню.
        """
        try:
            model = self.model
            if not model or not hasattr(model, "index_for"):
                logger.error(
                    "TreeManagement._find_item_by_id: model is not available or has no index_for"
                )
                return None
            idx = model.index_for(item_type, int(item_id))
            if idx and hasattr(idx, "isValid") and idx.isValid():
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

        # 1) Сохранить состояние
        state = self._save_view_state()

        # 2) Сортировка под подавлением перерисовок и сигналов
        try:
            with suspend_updates(self.tree):
                with block_tree_signals(self.tree):
                    model.sort(0, Qt.SortOrder.AscendingOrder)
        except Exception:
            logger.debug("TreeManagement._sort_tree: model.sort failed", exc_info=True)

        # 3) Восстановить состояние
        if state:
            self._restore_view_state(state)

        # 4) Уведомить обработчик выбора
        self._notify_selection_handler()

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
                logger.exception(
                    "TreeManagement._update_category_display: ошибка обновления плиток по иерархии категории #%s",
                    category_id,
                )

    def _update_category_tiles_after_edit(
        self, _category_index: QModelIndex | None = None
    ) -> None:
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
            logger.exception(
                "TreeManagement._update_category_tiles_after_edit: ошибка обновления плиток"
            )

    def _update_section_tiles_after_edit(
        self, _section_index: QModelIndex | None = None
    ) -> None:
        """Обновляет плитки категорий после редактирования раздела."""
        try:
            cur = self.tree.currentIndex()
            if cur and cur.isValid():
                t = get_tree_tuple(cur, 0)
                if t and t[0] == "section":
                    self.refresh_section_tiles(t[1])
        except Exception:
            logger.exception(
                "TreeManagement._update_section_tiles_after_edit: ошибка обновления плиток"
            )
