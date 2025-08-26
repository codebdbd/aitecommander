"""Строитель контекстного меню для дерева структуры."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtWidgets import QMenu
from PyQt6.QtWidgets import QApplication
import json

from app.utils.ui.menu_builders.menu_actions import (
    ActionBuilder,
    Shortcuts,
    StructureItemType,
)
from app.utils.ui.qt.roles import get_tree_tuple

from .base import get_menu_icon

# Сервисы для работы с деревом и ссылками
from app.services.structure_service import StructureService
from app.services.links_service import LinksService
from app.utils.ui.icon.cache_manager import clear_icon_cache

if TYPE_CHECKING:
    from app.main_window import MainWindow

logger = logging.getLogger(__name__)


class StructureMenuBuilder:
    """Строитель контекстного меню для дерева структуры."""

    def __init__(self, tree_widget, main_window: "MainWindow"):
        self.tree_widget = tree_widget
        self.main_window = main_window
        self.actions = ActionBuilder(tree_widget)
        self.theme = main_window.settings.get_theme()

    def build(
        self,
        item: Optional[Any],
        delete_item_cb: Callable,
        add_new_section_cb: Callable,
        sort_tree_cb: Callable,
    ) -> QMenu:
        """Создаёт контекстное меню для дерева структуры."""
        menu = QMenu(self.tree_widget)

        if item:
            self._add_item_actions(menu, item, delete_item_cb)
        else:
            self._add_root_actions(menu, add_new_section_cb, sort_tree_cb)

        return menu

    def _add_item_actions(self, menu: QMenu, item: Any, delete_item_cb: Callable):
        """Добавляет действия для выбранного элемента."""
        t = get_tree_tuple(item, 0)
        if not t:
            logger.warning("Invalid item data in context menu: None")
            return
        typ, id_ = t
        if typ not in (StructureItemType.SECTION, StructureItemType.CATEGORY):
            logger.warning(f"Unknown item type in context menu: {typ}")
            return

        if typ == StructureItemType.SECTION:
            self._add_section_actions(menu, item, id_, delete_item_cb)
        elif typ == StructureItemType.CATEGORY:
            self._add_category_actions(menu, item, id_, delete_item_cb)

    def _add_section_actions(self, menu: QMenu, item: Any, section_id: Any, delete_item_cb: Callable):
        """Добавляет действия для раздела."""
        menu.addAction(
            self.actions.create(
                "Редактировать раздел",
                lambda: self.main_window.edit_structure_item(item),
                Shortcuts.EDIT,
                get_menu_icon("edit", self.theme),
            )
        )

        menu.addAction(
            self.actions.create(
                "Добавить категорию",
                self.main_window.add_new_category,
                Shortcuts.ADD_CATEGORY,
                get_menu_icon("add_category", self.theme),
            )
        )

        # Вставить категорию (если в буфере корректные данные категории)
        if self._clipboard_has_pastable_category():
            menu.addAction(
                self.actions.create(
                    "Вставить",
                    lambda: self._paste_category_from_clipboard_to_section(section_id),
                    Shortcuts.CTRL_V,
                    get_menu_icon("paste", self.theme),
                )
            )

        menu.addSeparator()

        menu.addAction(
            self.actions.create(
                "Удалить раздел",
                lambda: delete_item_cb(item),
                Shortcuts.DELETE,
                get_menu_icon("delete", self.theme),
            )
        )

    def _add_category_actions(
        self, menu: QMenu, item: Any, id_: Any, delete_item_cb: Callable
    ):
        """Добавляет действия для категории."""
        menu.addAction(
            self.actions.create(
                "Редактировать категорию",
                lambda: self.main_window.edit_structure_item(item),
                Shortcuts.EDIT,
                get_menu_icon("edit", self.theme),
            )
        )

        menu.addAction(
            self.actions.create(
                "Добавить ссылку",
                lambda: self.main_window.links_actions.show_link_dialog(
                    category_id=id_
                ),
                Shortcuts.ADD_LINK,
                get_menu_icon("add_link", self.theme),
            )
        )

        menu.addSeparator()

        # 3. Копировать
        menu.addAction(
            self.actions.create(
                "Копировать",
                lambda: self._copy_category_tree_to_clipboard(item, id_),
                Shortcuts.CTRL_C,
                get_menu_icon("copy", self.theme),
            )
        )

        # 4. Вырезать (одиночно/массово)
        def _cut_action():
            # Определим множественный выбор категорий (QTreeView)
            selected = self._get_selected_category_nodes()
            if len(selected) > 1:
                # Массово: сначала скопировать все выбранные категории в буфер, потом пакетно удалить
                self._copy_selected_categories_to_clipboard(selected)
                try:
                    if hasattr(self.main_window, "structure") and self.main_window.structure:
                        self.main_window.structure.delete_selected_item()
                        return
                except Exception:
                    pass
            else:
                # Одиночная категория
                self._copy_category_tree_to_clipboard(item, id_)
                # Затем удалить текущий элемент
                # Используем тот же callback, что и для "Удалить категорию"
                delete_item_cb(item)

        menu.addAction(
            self.actions.create(
                "Вырезать",
                _cut_action,
                Shortcuts.CTRL_X,
                get_menu_icon("cut", self.theme),
            )
        )

        # 5. Вставить (только если в буфере есть текст)
        if self._clipboard_has_text():
            menu.addAction(
                self.actions.create(
                    "Вставить",
                    self.main_window.add_new_category,
                    Shortcuts.CTRL_V,
                    get_menu_icon("paste", self.theme),
                )
            )

        # 6. Удалить категорию / Удлаить выбранное (если выделено несколько)
        def _delete_action():
            try:
                selected = self._get_selected_category_nodes()
            except Exception:
                selected = []
            # Если в выделении несколько категорий — используем пакетное удаление
            if len(selected) > 1:
                logger.debug("[CtxMenu] Batch delete for %s selected categories", len(selected))
                try:
                    # Контроллер доступен как main_window.structure
                    if hasattr(self.main_window, "structure") and self.main_window.structure:
                        self.main_window.structure.delete_selected_item()
                        return
                except Exception:
                    pass
            # Иначе — одиночное удаление конкретного элемента
            delete_item_cb(item)

        action_text = "Удалить категорию"
        try:
            # Меняем подпись, если выделено больше одной категории
            selected_count = len(self._get_selected_category_nodes())
            if selected_count > 1:
                action_text = "Удлаить выбранное"
        except Exception:
            pass

        menu.addAction(
            self.actions.create(
                action_text,
                _delete_action,
                Shortcuts.DELETE,
                get_menu_icon("delete", self.theme),
            )
        )

        menu.addSeparator()

        # 7. Выделить все (категории раздела)
        menu.addAction(
            self.actions.create(
                "Выделить все",
                lambda: self._select_all_categories_in_section(item),
                Shortcuts.CTRL_A,
                get_menu_icon("select_all", self.theme),
            )
        )

        menu.addSeparator()

        # 7-8. Отменить/Повторить, если есть в главном окне
        if hasattr(self.main_window, "undo_action") and self.main_window.undo_action:
            menu.addAction(self.main_window.undo_action)
        if hasattr(self.main_window, "redo_action") and self.main_window.redo_action:
            menu.addAction(self.main_window.redo_action)

    # --- Helpers ---
    def _clipboard_has_text(self) -> bool:
        try:
            app = QApplication.instance()
            if not app:
                return False
            md = app.clipboard().mimeData()
            return bool(md and md.hasText() and md.text())
        except Exception:
            return False

    def _clipboard_get_json(self) -> Optional[dict]:
        """Возвращает JSON из буфера обмена, если он корректен."""
        if not self._clipboard_has_text():
            return None
        try:
            app = QApplication.instance()
            if not app:
                return None
            txt = app.clipboard().text()
            return json.loads(txt) if txt else None
        except Exception:
            return None

    def _clipboard_has_pastable_category(self) -> bool:
        """Проверяет, есть ли в буфере данные категории для вставки."""
        data = self._clipboard_get_json()
        if not data:
            return False
        # Поддержка словаря и списка
        if isinstance(data, dict):
            # Полный формат дерева
            if {"category", "links"}.issubset(set(data.keys())):
                return True
            # Старый формат по id
            if data.get("type") == "category" and data.get("id"):
                return True
            # Один tree по ключу tree
            if data.get("type") == "category_tree" and isinstance(data.get("tree"), dict):
                return True
            # Несколько деревьев по ключу trees
            if data.get("type") == "category_trees" and isinstance(data.get("trees"), list):
                return True
        elif isinstance(data, list):
            # Список полных деревьев
            return any(
                isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys()))
                for t in data
            )
        return False

    def _copy_category_tree_to_clipboard(self, item: Any, cat_id: Any) -> None:
        """Копирует в буфер полное поддерево категории (категория + ссылки)."""
        try:
            app = QApplication.instance()
            if not app:
                return
            dc = getattr(self.main_window, "database_controller", None)
            db = getattr(dc, "db", None)
            ss = StructureService(db)
            # Если выделено несколько категорий — копируем их все одним действием
            try:
                selected = self._get_selected_category_nodes()
            except Exception:
                selected = []

            if len(selected) > 1:
                trees: list[dict] = []
                for it in selected:
                    t = get_tree_tuple(it, 0)
                    if not t:
                        continue
                    _, cid = t
                    try:
                        trees.append(ss.export_category_tree(int(cid)))
                    except Exception:
                        continue
                if trees:
                    payload = {"type": "category_trees", "trees": trees}
                    app.clipboard().setText(json.dumps(payload, ensure_ascii=False))
                    return

            # Иначе — одиночная категория
            tree = ss.export_category_tree(int(cat_id))
            payload = {"type": "category_tree", "tree": tree}
            app.clipboard().setText(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    def _copy_selected_categories_to_clipboard(self, items: list[Any]) -> None:
        """Копирует несколько выделенных категорий (каждую с её ссылками) в буфер обмена."""
        try:
            app = QApplication.instance()
            if not app:
                return
            dc = getattr(self.main_window, "database_controller", None)
            db = getattr(dc, "db", None)
            ss = StructureService(db)
            trees: list[dict] = []
            for it in items:
                t = get_tree_tuple(it, 0)
                if not t:
                    continue
                typ, cat_id = t
                if typ != StructureItemType.CATEGORY:
                    continue
                try:
                    trees.append(ss.export_category_tree(int(cat_id)))
                except Exception:
                    continue
            if not trees:
                return
            payload = {"type": "category_trees", "trees": trees}
            app.clipboard().setText(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    def _paste_category_from_clipboard_to_section(self, section_id: Any) -> None:
        """Вставляет одну или несколько скопированных категорий в указанный раздел.
        Поддерживаются форматы: {category,links}, {type:category_tree,tree}, {type:category,id}, {type:category_trees,trees:[...]}
        """
        try:
            logger.debug("[PasteCategories] start paste into section_id=%s", section_id)
            data = self._clipboard_get_json()
            if not data:
                return

            def normalize_to_tree_list(payload: object) -> list[dict]:
                """Нормализует данные буфера в список деревьев категорий.
                Поддерживает dict-форматы и список полных деревьев. Для {type:category,id} делает экспорт через сервис.
                """
                ss_local = StructureService(self.main_window.database_controller.db)
                if isinstance(payload, dict):
                    if {"category", "links"}.issubset(set(payload.keys())):
                        return [payload]
                    if payload.get("type") == "category_tree" and isinstance(payload.get("tree"), dict):
                        return [payload.get("tree")]
                    if payload.get("type") == "category" and payload.get("id"):
                        return [ss_local.export_category_tree(int(payload["id"]))]
                    if payload.get("type") == "category_trees" and isinstance(payload.get("trees"), list):
                        out: list[dict] = []
                        for t in payload.get("trees", []):
                            if isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys())):
                                out.append(t)
                        return out
                    return []
                if isinstance(payload, list):
                    return [t for t in payload if isinstance(t, dict) and {"category", "links"}.issubset(set(t.keys()))]
                return []

            trees: list[dict] = normalize_to_tree_list(data)
            if not trees:
                return
            try:
                logger.debug("[PasteCategories] normalized trees count=%s", len(trees))
            except Exception:
                pass

            dc2 = getattr(self.main_window, "database_controller", None)
            db2 = getattr(dc2, "db", None)
            ss = StructureService(db2)
            ls = LinksService(db2)

            business = getattr(self.main_window, "structure_business", None)
            struct = getattr(self.main_window, "structure", None)
            tree_widget = getattr(struct, "tree", None)
            selection = getattr(struct, "selection_handler", None)

            # Подавляем сигналы выбора/дерева на время пакетной операции
            try:
                # ВАЖНО: на время вставки подавляем любые попытки удаления (горячие клавиши/хендлеры)
                try:
                    setattr(self.main_window, "_suppress_deletes", True)
                    logger.debug("[PasteCategories] _suppress_deletes set=True")
                except Exception:
                    pass
                if selection is not None:
                    try:
                        selection.begin_suppress_selection()
                    except Exception:
                        pass
                if tree_widget is not None:
                    tree_widget.blockSignals(True)
            except Exception:
                pass

            created_any = False
            created_categories: list[dict] = []
            try:
                # 1) Пакетно создаём категории
                batch_cats: list[dict] = []
                for tree in trees:
                    try:
                        src_cat_name = (tree.get("category") or {}).get("name")
                    except Exception:
                        src_cat_name = None
                    logger.debug("[PasteCategories] processing category '%s'", src_cat_name)
                    src_cat = dict(tree.get("category", {}))
                    new_cat_data = {k: v for k, v in src_cat.items() if k not in {"id", "section_id"}}
                    new_cat_data["section_id"] = int(section_id)
                    batch_cats.append(new_cat_data)

                if batch_cats:
                    try:
                        created_list = ss.create_categories_bulk(batch_cats) or []
                        # Построим индекс по именам (с учётом возможных дублей — списки)
                        index_by_name: dict[str, list[dict]] = {}
                        for c in created_list:
                            nm = c.get("name")
                            if nm is None:
                                continue
                            index_by_name.setdefault(nm, []).append(c)

                        # 2) Собираем все ссылки в один батч, сопоставляя категории по имени
                        all_links: list[dict] = []
                        for tree in trees:
                            src_cat = dict(tree.get("category", {}))
                            src_links = list(tree.get("links", []))
                            nm = src_cat.get("name")
                            cat_row: Optional[dict] = None
                            if nm in index_by_name and index_by_name[nm]:
                                cat_row = index_by_name[nm].pop(0)
                            if not cat_row:
                                # На крайний случай — пропускаем эту категорию
                                continue
                            created_any = True
                            created_categories.append(dict(cat_row))
                            new_cat_id = int(cat_row.get("id"))

                            for link in src_links:
                                src = dict(link)
                                name = src.get("name") or ""
                                url = src.get("url") or ""
                                ltype = src.get("type") or "web"
                                if not url or not name:
                                    continue
                                notes = src.get("notes") or ""
                                is_favorite = int(src.get("is_favorite") or 0)
                                icon_path = src.get("icon_path") or "default.ico"
                                args = src.get("args") or ""
                                browser_key = src.get("browser_key")

                                link_data = {
                                    "category_id": new_cat_id,
                                    "name": name,
                                    "url": url,
                                    "type": ltype,
                                    "notes": notes,
                                    "is_favorite": is_favorite,
                                    "icon_path": icon_path,
                                    "args": args,
                                }
                                if browser_key is not None:
                                    link_data["browser_key"] = browser_key
                                all_links.append(link_data)

                        if all_links:
                            try:
                                logger.debug("[PasteCategories] upserting total %s links in single batch", len(all_links))
                                ls.batch_create_or_update_links(all_links)
                            except Exception:
                                pass
                    except Exception:
                        # В случае ошибки пакетного создания — fallback не выполняем, чтобы сохранить атомарность
                        pass
            finally:
                # Возвращаем сигналы
                try:
                    if tree_widget is not None:
                        tree_widget.blockSignals(False)
                except Exception:
                    pass
                try:
                    if selection is not None:
                        selection.end_suppress_selection()
                except Exception:
                    pass
                # Снимаем флаг подавления удалений
                try:
                    setattr(self.main_window, "_suppress_deletes", False)
                    logger.debug("[PasteCategories] _suppress_deletes set=False")
                except Exception:
                    pass

            # Инкрементальное обновление UI без полной перезагрузки
            if created_any:
                try:
                    if business:
                        # Очистим кэш иконок один раз, если требуется обновление плиток
                        try:
                            clear_icon_cache()
                        except Exception:
                            pass
                        # Инвалидируем кэш категорий раздела и выполним единственное перечитывание раздела
                        try:
                            business._invalidate_categories_cache(int(section_id))
                        except Exception:
                            pass
                        # Планируем единственную перезагрузку структуры, чтобы обновилось дерево слева
                        try:
                            business._schedule_structure_reload(0)
                            logger.debug("[PasteCategories] scheduled structure reload (debounced)")
                        except Exception:
                            pass
                        business.select_section(int(section_id))
                except Exception:
                    pass
            logger.debug("[PasteCategories] done, created=%s items", len(created_categories))
        except Exception:
            # Не роняем UI из-за ошибок вставки
            pass

    def _select_all_categories_in_section(self, item: Any) -> None:
        """Выделить все категории внутри раздела (QTreeView-only)."""
        try:
            if not (hasattr(self.tree_widget, "selectionModel") and hasattr(self.tree_widget, "model")):
                return
            model = self.tree_widget.model()
            sel_model = self.tree_widget.selectionModel()
            if not (model and sel_model):
                return
            # item — QModelIndex категории или раздела
            idx = item if getattr(item, "isValid", lambda: False)() else None
            if idx is None:
                return
            t = get_tree_tuple(idx, 0)
            if not t:
                return
            typ, _ = t
            section_index = idx if typ == StructureItemType.SECTION else idx.parent()
            if not (section_index and section_index.isValid()):
                return
            # Снимаем выделение
            sel_model.clearSelection()
            # Выделяем все дочерние элементы раздела (категории)
            row_count = model.rowCount(section_index)
            for r in range(row_count):
                child = model.index(r, 0, section_index)
                if child and child.isValid():
                    tchild = get_tree_tuple(child, 0)
                    if tchild and tchild[0] == StructureItemType.CATEGORY:
                        sel_model.select(child, sel_model.SelectionFlag.Select | sel_model.SelectionFlag.Rows)
        except Exception:
            pass

    # --- Универсальные хелперы выбора категорий ---
    def _get_selected_category_nodes(self) -> list[Any]:
        """Возвращает список выделенных узлов категорий для QTreeView (QModelIndex)."""
        try:
            if hasattr(self.tree_widget, "selectionModel") and hasattr(self.tree_widget, "model"):
                sel_model = self.tree_widget.selectionModel()
                if not sel_model:
                    return []
                rows = sel_model.selectedRows(0) or []
                return [idx for idx in rows if (get_tree_tuple(idx, 0) and get_tree_tuple(idx, 0)[0] == StructureItemType.CATEGORY)]
        except Exception:
            return []
        return []

    def _add_root_actions(
        self, menu: QMenu, add_new_section_cb: Callable, sort_tree_cb: Callable
    ):
        """Добавляет действия для корневого уровня."""
        menu.addAction(
            self.actions.create(
                "Добавить раздел",
                add_new_section_cb,
                Shortcuts.ADD_SECTION,
                get_menu_icon("add_section", self.theme),
            )
        )

        menu.addSeparator()

        menu.addAction(
            self.actions.create(
                "Сортировать категории",
                sort_tree_cb,
                Shortcuts.SORT,
                get_menu_icon("sort", self.theme),
            )
        )
