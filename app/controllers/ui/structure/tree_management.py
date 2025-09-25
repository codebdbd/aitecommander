# app/controllers/structure/tree_management.py

import logging
from typing import Any, Optional

from PyQt6.QtCore import QModelIndex, QObject, Qt, pyqtSlot

from app.utils.ui.qt.roles import get_tree_tuple

from app.controllers.ui.types import (
    CategoryTilesControllerProtocol,
    StructureTreeModelProtocol,
)
from .tree_snapshot_service import TreeSnapshotService
from .tree_state_service import TreeStateService
from .tree_tiles_service import TreeTilesService
from .tree_update_service import TreeUpdateService

logger = logging.getLogger(__name__)


class TreeManagement(QObject):
    def __init__(self, controller, category_tiles_controller):
        parent = controller if isinstance(controller, QObject) else None
        super().__init__(parent=parent)
        self.controller = controller
        self.tree = controller.tree
        self.icon_handler = controller.icon_handler
        # Явная обязательная зависимость: контроллер плиток категорий
        if category_tiles_controller is None:
            raise ValueError(
                "TreeManagement requires a non-None category_tiles_controller"
            )
        if not isinstance(category_tiles_controller, CategoryTilesControllerProtocol):
            raise TypeError(
                "category_tiles_controller must implement CategoryTilesControllerProtocol"
            )
        self.tiles_controller: CategoryTilesControllerProtocol = category_tiles_controller

        # Явная ссылка на модель дерева и проверка контракта
        try:
            model_getter = getattr(self.tree, "model")
            raw_model = model_getter() if callable(model_getter) else None
        except AttributeError:
            raw_model = None
        if raw_model is None:
            raise ValueError("TreeManagement requires a valid tree model")
        if not isinstance(raw_model, StructureTreeModelProtocol):
            raise TypeError(
                "TreeManagement requires model implementing StructureTreeModelProtocol"
            )
        self.model: StructureTreeModelProtocol = raw_model
        self._state = TreeStateService(
            controller=controller,
            tree=self.tree,
            model=self.model,
        )
        self._snapshot = TreeSnapshotService(manager=self, model=self.model)
        self._tiles = TreeTilesService(manager=self)
        self._updates = TreeUpdateService(
            manager=self,
            tree=self.tree,
            model=self.model,
        )

    @pyqtSlot(list)
    def _on_structure_loaded(self, sections_data: list[dict[str, Any]]) -> None:
        # Сохраняем текущее выделение и состояние разворота до перезагрузки модели
        current_selection = self._state.capture_current_selection()
        expanded_state = self._state.capture_expanded_state()

        # Сортируем разделы по имени (без учета регистра) перед передачей в модель
        try:
            sections_data = sorted(
                sections_data or [],
                key=lambda s: str(s.get("name", "")).lower(),
            )
        except (TypeError, AttributeError, KeyError):
            logger.exception(
                "TreeManagement._on_structure_loaded: ошибка сортировки разделов"
            )

        # Обновляем модель одним снимком
        if sections_data is None:
            sections_data = []
        def _on_snapshot_error() -> None:
            logger.exception(
                "TreeManagement._on_structure_loaded: модель не смогла принять снапшот"
            )

        self._snapshot.schedule_snapshot(
            sections_data,
            on_success=lambda: self._after_snapshot_applied(
                expanded_state, current_selection
            ),
            on_error=_on_snapshot_error,
        )
        return

        # Если структура пуста (нет ни одного раздела) — очистим плитки категорий
        try:
            if not sections_data:
                self.clear_tiles()
        except Exception:
            logger.exception(
                "TreeManagement._on_structure_loaded: ошибка очистки плиток при пустой структуре"
            )
        self._after_snapshot_applied(expanded_state, current_selection)

        # Гарантированно сбросим одноразовый флаг подавления восстановления категории,
        # если он по какой-то причине остался установлен после обработки выше.
        try:
            sb = getattr(self.controller, "business", None) or getattr(
                self.controller, "structure_business", None
            )
            if sb and getattr(sb, "_suppress_category_restore_once", False):
                setattr(sb, "_suppress_category_restore_once", False)
        except Exception:
            pass

        # Иконки теперь обновляются событием modelReset в StructureUIController;
        # здесь дополнительных вызовов не делаем, чтобы избежать двойной работы.

        # После первой загрузки структуры обновляем отображение главного окна
        main = getattr(self.controller, "main", None)
        if main is not None and getattr(main, "_first_structure_load", False):
            setattr(main, "_first_structure_load", False)
            self.tree.updateGeometry()
            self.tree.update()

    @pyqtSlot(str, int, dict)
    def _on_item_added(self, item_type: str, parent_id: int, data: dict[str, Any]) -> None:
        # Инкрементальная вставка через модель
        # Примечание: при ошибке вставки требуется полная перезагрузка структуры —
        # ожидаемые ошибки модели (ValueError, RuntimeError) логируем и пробрасываем вверх,
        # неожиданные исключения также не подавляются.
        if item_type == "category" and not isinstance(parent_id, int):
            return
        self._updates.handle_item_added(item_type, parent_id, data)

    @pyqtSlot(str, int, dict)
    def _on_item_updated(self, item_type: str, item_id: int, data: dict[str, Any]) -> None:
        self._updates.handle_item_updated(item_type, item_id, data)

    @pyqtSlot(str, int)
    def _on_item_deleted(self, item_type: str, item_id: int) -> None:
        self._updates.handle_item_deleted(item_type, item_id)

    def clear_tiles(self) -> None:
        """Сбросить плитки категорий."""
        self._tiles.clear_tiles()

    def refresh_tiles_for_current_selection(self) -> None:
        """Обновить плитки в соответствии с текущим выбором дерева."""
        self._tiles.refresh_by_current_tree_selection()

    def refresh_section_tiles(self, section_id: int) -> None:
        """Обновить плитки раздела через переданный CategoryTilesController."""
        self._tiles.refresh_section_tiles(section_id)

    def get_current_category_id(self) -> Optional[int]:
        selection = self._state.capture_current_selection()
        if selection and selection[0] == "category" and isinstance(selection[1], int):
            return selection[1]
        return None

    def _find_item_by_id(self, item_type: str, item_id: int):
        """Возвращает QModelIndex элемента по типу ('section'|'category') и id.

        Совместимый хелпер для вызовов из `ItemOperations` и действий меню.
        """
        try:
            idx = self.model.index_for(item_type, int(item_id))
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
        # Сохраняем текущее выделение и развёрнутость
        current_selection = self._state.capture_current_selection()
        expanded_state = self._state.capture_expanded_state()

        try:
            # Собираем текущий снапшот из модели
            sections_data: list[dict] = []
            root_rows = self.model.rowCount(QModelIndex())
            for r in range(root_rows):
                s_idx = self.model.index(r, 0, QModelIndex())
                if not s_idx or not s_idx.isValid():
                    continue
                t = get_tree_tuple(s_idx, 0)
                if not t or t[0] != "section":
                    continue
                s_id = t[1]
                s_name = self.model.data(s_idx, Qt.ItemDataRole.DisplayRole) or ""
                s_icon = self.model.data(s_idx, Qt.ItemDataRole.DecorationRole)

                # Собираем категории раздела
                cats: list[dict] = []
                child_rows = self.model.rowCount(s_idx)
                for i in range(child_rows):
                    c_idx = self.model.index(i, 0, s_idx)
                    if not c_idx or not c_idx.isValid():
                        continue
                    ct = get_tree_tuple(c_idx, 0)
                    if not ct or ct[0] != "category":
                        continue
                    c_id = ct[1]
                    c_name = self.model.data(c_idx, Qt.ItemDataRole.DisplayRole) or ""
                    c_icon = self.model.data(c_idx, Qt.ItemDataRole.DecorationRole)
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

            def _restore_sort_state() -> None:
                self._state.restore_expanded_state(expanded_state)
                if current_selection:
                    self._state.restore_selection(current_selection)

            self._snapshot.schedule_snapshot(
                sections_data,
                on_success=_restore_sort_state,
                on_error=lambda: logger.debug(
                    "TreeManagement._sort_tree: snapshot update failed; fallback to no-op",
                    exc_info=True,
                ),
            )
        except Exception:
            logger.debug(
                "TreeManagement._sort_tree: snapshot preparation failed",
                exc_info=True,
            )

    def on_structure_item_changed(
        self, item_type: str, item_id: int, data: dict
    ) -> None:
        self._on_item_updated(item_type, item_id, data)

    # --- Вспомогательные методы ----------------------------------------

    def _after_structure_loaded_snapshot(
        self,
        expanded_state: dict,
        current_selection: Optional[tuple[str, int]],
        has_sections: bool,
    ) -> None:
        # Если структура пуста — очищаем плитки
        if not has_sections:
            try:
                self.clear_tiles()
            except Exception:
                logger.exception(
                    "TreeManagement._after_structure_loaded_snapshot: ошибка очистки плиток"
                )

        # Восстанавливаем развёрнутость
        self._state.restore_expanded_state(expanded_state)

        # Восстанавливаем выделение, если оно существовало
        if current_selection:
            item_type, item_id = current_selection
            if item_type in ("section", "category") and isinstance(item_id, int):
                if item_type == "category":
                    sb = None
                    try:
                        sb = getattr(self.controller, "business", None) or getattr(
                            self.controller, "structure_business", None
                        )
                    except Exception:
                        sb = None
                    if sb and getattr(sb, "_suppress_category_restore_once", False):
                        try:
                            setattr(sb, "_suppress_category_restore_once", False)
                        except Exception:
                            pass
                        self._state.select_first_item()
                        self._finalize_first_load()
                        return
                self._state.restore_selection(current_selection)
        else:
            self._state.select_first_item()

        self._finalize_first_load()

    def _finalize_first_load(self) -> None:
        # Гарантированно сбросим одноразовый флаг подавления восстановления категории
        try:
            sb = getattr(self.controller, "business", None) or getattr(
                self.controller, "structure_business", None
            )
            if sb and getattr(sb, "_suppress_category_restore_once", False):
                setattr(sb, "_suppress_category_restore_once", False)
        except Exception:
            pass

        # После первой загрузки структуры обновляем отображение главного окна
        main = getattr(self.controller, "main", None)
        if main is not None and getattr(main, "_first_structure_load", False):
            setattr(main, "_first_structure_load", False)
            self.tree.updateGeometry()
            self.tree.update()

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
        self._tiles.refresh_after_category_edit()

    def _update_section_tiles_after_edit(
        self, _section_index: QModelIndex | None = None
    ) -> None:
        """Обновляет плитки категорий после редактирования раздела."""
        self._tiles.refresh_after_section_edit()
