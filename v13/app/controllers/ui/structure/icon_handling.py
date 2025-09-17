# app/controllers/structure/icon_handling.py

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from app.utils.ui.icon.icon_operations.creators import create_icon_from_path
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link


class IconHandling:
    def __init__(self, controller):
        self.controller = controller
        self.tree = controller.tree
        self.business = controller.business
        # Кэш последних путей иконок, чтобы не трогать неизменившиеся узлы
        # Ключ: (item_type, item_id), Значение: строка icon_path или None
        self._last_icon_paths: dict[tuple[str, int], str | None] = {}

    def _get_icon_for_item(self, item_type: str, icon_name: str) -> QIcon:
        # Централизованный резолвер: учитывает и заданный icon_name, и тип
        try:
            resolved = resolve_icon_for_link(
                {"type": item_type, "icon_path": icon_name or ""}
            )
            if resolved:
                return create_icon_from_path(resolved)
        except Exception:
            pass
        # Пустая иконка, если ничего не найдено
        return QIcon()

    def reload_icons(self) -> None:
        """Переустанавливает иконки для всех элементов дерева.

        Обходим модель QTreeView и выставляем иконки через DecorationRole.
        """
        # Ветвь для QTreeView — обходим модель и выставляем DecorationRole
        try:
            model = getattr(self.tree, "model", lambda: None)()
            if not model:
                return

            # Локальная рекурсивная функция обхода
            def iter_indexes(parent_index=None):
                from PyQt6.QtCore import QModelIndex

                if parent_index is None:
                    parent_index = QModelIndex()
                rows = model.rowCount(parent_index)
                for r in range(rows):
                    idx = model.index(r, 0, parent_index)
                    if idx.isValid():
                        yield idx
                        yield from iter_indexes(idx)

            from app.utils.ui.qt.roles import get_tree_tuple

            for idx in iter_indexes():
                t = get_tree_tuple(idx, 0)
                if not t:
                    # Сбрасываем иконку, если нет валидных данных
                    try:
                        model.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                    except Exception:
                        pass
                    continue
                item_type, item_id = t
                try:
                    if item_type == "section":
                        data = self.business.get_section_data(item_id)
                    elif item_type == "category":
                        data = self.business.get_category_data(item_id)
                    else:
                        data = None

                    # Текущий вычисленный путь
                    new_path = data.get("icon_path") if data else None
                    key = (item_type, int(item_id)) if isinstance(item_id, int) else None

                    # Сравниваем с последним известным путём; если не изменился — пропускаем перезапись
                    if key is not None:
                        last_path = self._last_icon_paths.get(key)
                        if last_path == new_path:
                            continue

                    # Обновляем иконку только при изменении пути
                    icon = self._get_icon_for_item(item_type, new_path or "")
                    model.setData(idx, icon, Qt.ItemDataRole.DecorationRole)

                    # Запоминаем последний путь
                    if key is not None:
                        self._last_icon_paths[key] = new_path
                except Exception:
                    try:
                        model.setData(idx, QIcon(), Qt.ItemDataRole.DecorationRole)
                    except Exception:
                        pass
        except Exception:
            # В случае любой ошибки не прерываем UI
            pass

    def update_icon_for_item(self, item_type: str, item_id: int, icon_path: str | None) -> None:
        """Точечное обновление иконки элемента без полного обхода дерева.

        - Резолвит QIcon для переданного пути
        - Обновляет модель через DecorationRole и update_item API, если доступен
        - Синхронизирует кэш последнего пути
        """
        try:
            model = getattr(self.tree, "model", lambda: None)()
            if not model:
                return
            # Подготовим QIcon
            icon = self._get_icon_for_item(item_type, icon_path or "")
            # Используем удобный API модели, если он есть (update_item)
            if hasattr(model, "update_item") and callable(getattr(model, "update_item")):
                try:
                    model.update_item(item_type, int(item_id), {"icon": icon, "icon_path": icon_path})
                except Exception:
                    # Fallback — прямое setData по индексу
                    idx = getattr(model, "index_for", lambda *_: None)(item_type, int(item_id))
                    if idx and getattr(idx, "isValid", lambda: False)():
                        model.setData(idx, icon, Qt.ItemDataRole.DecorationRole)
            else:
                # Fallback — прямое setData по индексу
                idx = getattr(model, "index_for", lambda *_: None)(item_type, int(item_id))
                if idx and getattr(idx, "isValid", lambda: False)():
                    model.setData(idx, icon, Qt.ItemDataRole.DecorationRole)

            # Обновляем кэш пути
            self._last_icon_paths[(item_type, int(item_id))] = icon_path
        except Exception:
            # Безопасный no-op
            pass

    def set_cached_icon_path(self, item_type: str, item_id: int, icon_path: str | None) -> None:
        """Синхронизировать кэш для узла (используется после insert)."""
        try:
            self._last_icon_paths[(str(item_type), int(item_id))] = icon_path
        except Exception:
            pass
