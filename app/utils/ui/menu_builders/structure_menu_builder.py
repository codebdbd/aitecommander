"""Строитель контекстного меню для дерева структуры."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtWidgets import QMenu, QTreeWidget
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

if TYPE_CHECKING:
    from app.main_window import MainWindow

logger = logging.getLogger(__name__)


class StructureMenuBuilder:
    """Строитель контекстного меню для дерева структуры."""

    def __init__(self, tree_widget: QTreeWidget, main_window: "MainWindow"):
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
            # Определим множественный выбор категорий
            try:
                selected = [
                    it
                    for it in self.tree_widget.selectedItems()
                    if get_tree_tuple(it, 0) and get_tree_tuple(it, 0)[0] == StructureItemType.CATEGORY
                ]
            except Exception:
                selected = []

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
                selected = [
                    it
                    for it in self.tree_widget.selectedItems()
                    if get_tree_tuple(it, 0) and get_tree_tuple(it, 0)[0] == StructureItemType.CATEGORY
                ]
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
            # Меняем подпись, если выделено больше одной категории (необязательно, но удобнее пользователю)
            selected_count = len([
                it
                for it in self.tree_widget.selectedItems()
                if get_tree_tuple(it, 0) and get_tree_tuple(it, 0)[0] == StructureItemType.CATEGORY
            ])
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
        # Поддержка двух форматов: старый (type=category,id,...) и новый (полный tree)
        if isinstance(data, dict) and {
            "category",
            "links",
        }.issubset(set(data.keys())):
            return True
        if data.get("type") == "category" and data.get("id"):
            return True
        if data.get("type") == "category_tree" and isinstance(data.get("tree"), dict):
            return True
        # Несколько категорий
        if data.get("type") == "category_trees" and isinstance(data.get("trees"), list):
            return True
        return False

    def _copy_category_tree_to_clipboard(self, item: Any, cat_id: Any) -> None:
        """Копирует в буфер полное поддерево категории (категория + ссылки)."""
        try:
            app = QApplication.instance()
            if not app:
                return
            # Экспортируем полную категорию через сервис
            ss = StructureService(self.main_window.db)
            # Если выделено несколько категорий — копируем их все одним действием
            try:
                selected = [
                    it
                    for it in self.tree_widget.selectedItems()
                    if get_tree_tuple(it, 0) and get_tree_tuple(it, 0)[0] == StructureItemType.CATEGORY
                ]
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
            ss = StructureService(self.main_window.db)
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
            data = self._clipboard_get_json()
            if not data:
                return

            def normalize_to_tree_list(payload: dict) -> list[dict]:
                ss_local = StructureService(self.main_window.db)
                # Уже полный формат
                if isinstance(payload, dict) and {"category", "links"}.issubset(set(payload.keys())):
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

            trees: list[dict] = normalize_to_tree_list(data)
            if not trees:
                return

            ss = StructureService(self.main_window.db)
            ls = LinksService(self.main_window.db)
            last_new_cat_id: Optional[int] = None

            for tree in trees:
                src_cat = dict(tree.get("category", {}))
                src_links = list(tree.get("links", []))

                new_cat_data = {k: v for k, v in src_cat.items() if k not in {"id", "section_id"}}
                new_cat_data["section_id"] = int(section_id)
                new_cat_id = ss.create_category(new_cat_data)
                if not new_cat_id:
                    continue

                last_new_cat_id = int(new_cat_id)

                for link in src_links:
                    src = dict(link)
                    # Обязательные поля
                    name = src.get("name") or ""
                    url = src.get("url") or ""
                    ltype = src.get("type") or "web"

                    # Пропускаем некорректные записи без URL или имени
                    if not url or not name:
                        continue

                    # Опциональные поля с дефолтами
                    notes = src.get("notes") or ""
                    is_favorite = int(src.get("is_favorite") or 0)
                    icon_path = src.get("icon_path") or "default.ico"
                    args = src.get("args") or ""
                    browser_key = src.get("browser_key")

                    link_data = {
                        "category_id": int(new_cat_id),
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
                    ls.create_or_update_link(link_data)

            # Обновляем UI: полная перезагрузка дерева. Выделяем последнюю созданную категорию, если есть.
            try:
                if hasattr(self.main_window, "structure") and self.main_window.structure:
                    if last_new_cat_id:
                        self.main_window.structure.load(item_to_select=("category", int(last_new_cat_id)))
                    else:
                        self.main_window.structure.load()
            except Exception:
                pass
        except Exception:
            # Не роняем UI из-за ошибок вставки
            pass

    def _select_all_categories_in_section(self, item: Any) -> None:
        try:
            parent = item.parent()
            if parent is None:
                # Если сам раздел выбран (на всякий случай), используем его
                parent = item
            # Снимаем текущее выделение и выделяем всех детей раздела
            self.tree_widget.clearSelection()
            for i in range(parent.childCount()):
                child = parent.child(i)
                # Выделяем только категории (дети раздела)
                child.setSelected(True)
        except Exception:
            pass

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
