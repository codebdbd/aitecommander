"""Строитель контекстного меню для дерева структуры."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

from PyQt6.QtWidgets import QMenu

# Сервис бизнес-логики контекстного меню
from app.services.structure_context_service import StructureContextService
from app.utils.ui.icon.cache_manager import clear_icon_cache
from app.utils.ui.menu_builders.menu_actions import (
    ActionBuilder,
    Shortcuts,
    StructureItemType,
)
from app.utils.ui.qt.roles import get_tree_tuple

from .base import get_menu_icon

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
        # Инициализация сервиса бизнес-логики
        dc = getattr(self.main_window, "database_controller", None)
        db = getattr(dc, "db", None)
        self._svc = StructureContextService(db)

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
        if self._svc.clipboard_has_pastable_category():
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
                    logger.exception("[CtxMenu] Ошибка пакетного удаления выбранных категорий")
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
        if self._svc.clipboard_has_text():
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
                logger.exception("[CtxMenu] Не удалось получить выделенные категории для удаления; одиночное удаление")
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
                    logger.exception("[CtxMenu] Ошибка пакетного удаления выбранных категорий")
            # Иначе — одиночное удаление конкретного элемента
            delete_item_cb(item)

        action_text = "Удалить категорию"
        try:
            # Меняем подпись, если выделено больше одной категории
            selected_count = len(self._get_selected_category_nodes())
            if selected_count > 1:
                action_text = "Удлаить выбранное"
        except Exception:
            logger.exception("[CtxMenu] Не удалось вычислить количество выделенных категорий")

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
    # Проксирующие методы для читаемости прежних вызовов (минимально-инвазивный рефакторинг)
    def _clipboard_has_text(self) -> bool:
        return self._svc.clipboard_has_text()

    def _clipboard_has_pastable_category(self) -> bool:
        return self._svc.clipboard_has_pastable_category()

    def _copy_category_tree_to_clipboard(self, item: Any, cat_id: Any) -> None:
        """Копирует в буфер одно дерево категории либо, при множественном выборе, сразу несколько."""
        try:
            selected = self._get_selected_category_nodes()
        except Exception:
            logger.exception("[Clipboard] Не удалось получить список выделенных категорий; копируем одиночную")
            selected = []
        if len(selected) > 1:
            ids: list[int] = []
            for it in selected:
                t = get_tree_tuple(it, 0)
                if not t:
                    continue
                _, cid = t
                try:
                    ids.append(int(cid))
                except Exception:
                    logger.exception("[Clipboard] Некорректный идентификатор категории в выделении: %r", cid)
                    continue
            if ids:
                self._svc.copy_categories_to_clipboard(ids)
                return
        # одиночная категория
        try:
            self._svc.copy_category_tree_to_clipboard(int(cat_id))
        except Exception:
            logger.exception("[Clipboard] Ошибка копирования дерева категории id=%r в буфер", cat_id)

    def _copy_selected_categories_to_clipboard(self, items: list[Any]) -> None:
        """Копирует несколько выделенных категорий по их id через сервис."""
        ids: list[int] = []
        for it in items:
            t = get_tree_tuple(it, 0)
            if not t:
                continue
            typ, cat_id = t
            if typ != StructureItemType.CATEGORY:
                continue
            try:
                ids.append(int(cat_id))
            except Exception:
                logger.exception("[Clipboard] Некорректный идентификатор категории в выделении: %r", cat_id)
                continue
        if ids:
            try:
                self._svc.copy_categories_to_clipboard(ids)
            except Exception:
                logger.exception("[Clipboard] Ошибка пакетного копирования категорий в буфер: %r", ids)

    def _paste_category_from_clipboard_to_section(self, section_id: Any) -> None:
        """Вставляет одну или несколько категорий из буфера в раздел, делегируя бизнес-логику сервису."""
        try:
            logger.debug("[PasteCategories] start paste into section_id=%s", section_id)

            business = getattr(self.main_window, "structure_business", None)
            struct = getattr(self.main_window, "structure", None)
            tree_widget = getattr(struct, "tree", None)
            selection = getattr(struct, "selection_handler", None)

            # Подавляем сигналы выбора/дерева на время пакетной операции
            try:
                try:
                    setattr(self.main_window, "_suppress_deletes", True)
                    logger.debug("[PasteCategories] _suppress_deletes set=True")
                except Exception:
                    logger.exception("[PasteCategories] Не удалось установить _suppress_deletes=True")
                if selection is not None:
                    try:
                        selection.begin_suppress_selection()
                    except Exception:
                        logger.exception("[PasteCategories] Не удалось начать подавление выбора")
                if tree_widget is not None:
                    tree_widget.blockSignals(True)
            except Exception:
                logger.exception("[PasteCategories] Не удалось заблокировать сигналы/начать подавление событий UI")

            created_categories: list[dict] = []
            try:
                created_categories = self._svc.paste_from_clipboard_to_section(int(section_id))
            finally:
                # Возвращаем сигналы
                try:
                    if tree_widget is not None:
                        tree_widget.blockSignals(False)
                except Exception:
                    logger.exception("[PasteCategories] Не удалось разблокировать сигналы дерева")
                try:
                    if selection is not None:
                        selection.end_suppress_selection()
                except Exception:
                    logger.exception("[PasteCategories] Не удалось завершить подавление выбора")
                try:
                    setattr(self.main_window, "_suppress_deletes", False)
                    logger.debug("[PasteCategories] _suppress_deletes set=False")
                except Exception:
                    logger.exception("[PasteCategories] Не удалось установить _suppress_deletes=False")

            # Инкрементальное обновление UI без полной перезагрузки
            if created_categories:
                try:
                    if business:
                        try:
                            clear_icon_cache()
                        except Exception:
                            logger.exception("[PasteCategories] Не удалось очистить кэш иконок")
                        try:
                            business._invalidate_categories_cache(int(section_id))
                        except Exception:
                            logger.exception("[PasteCategories] Не удалось инвалидацировать кэш категорий секции %r", section_id)
                        try:
                            business._schedule_structure_reload(0)
                            logger.debug("[PasteCategories] scheduled structure reload (debounced)")
                        except Exception:
                            logger.exception("[PasteCategories] Не удалось запланировать перезагрузку структуры")
                        business.select_section(int(section_id))
                except Exception:
                    logger.exception("[PasteCategories] Ошибка обновления UI после вставки категорий")
            logger.debug("[PasteCategories] done, created=%s items", len(created_categories))
        except Exception:
            # Не роняем UI из-за ошибок вставки — но логируем
            logger.exception("[PasteCategories] Ошибка вставки категорий в раздел %r", section_id)

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
            logger.exception("[SelectAll] Ошибка выделения всех категорий в разделе")

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
            logger.exception("[Selection] Ошибка получения выделенных узлов категорий")
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
