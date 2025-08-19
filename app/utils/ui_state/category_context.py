# app/utils/ui_state/category_context.py

from __future__ import annotations

from typing import Optional

from app.config_data import app_config
from app.utils.ui.qt.roles import get_tree_tuple


class CategoryContext:
    """Сервис для вычисления текущей категории в UI-контексте.
    Инкапсулирует логику определения активной категории, чтобы разгрузить MainWindow.
    """

    def __init__(self, window):
        # Храним ссылку на окно. Специальной абстракции пока не требуется.
        self.window = window

    def get_current_category_id(self) -> Optional[int]:
        """Определяет ID текущей категории по приоритету:
        1) Активная плитка в режиме плиток
        2) Сохранённое значение window.current_category_id
        3) Выбранный элемент дерева структуры (если это категория)
        4) Первый доступный ID категории из бизнес-логики структуры
        """
        w = self.window

        # 1) Режим плиток
        try:
            tiles_stack_index = app_config.get('ui.stack_indices.tiles', 0)
            if (
                hasattr(w, 'tiles') and w.tiles is not None and
                hasattr(w, 'stack') and w.stack is not None and
                hasattr(w, 'stack') and w.stack.currentIndex() == tiles_stack_index and
                hasattr(w.tiles, '_current_item_id') and w.tiles._current_item_id is not None
            ):
                return w.tiles._current_item_id
        except Exception:
            # Безопасный фолбэк, не прерываем вычисление
            pass

        # 2) Сохранённое значение
        if hasattr(w, 'current_category_id') and getattr(w, 'current_category_id'):
            return getattr(w, 'current_category_id')

        # 3) Выбор в дереве
        try:
            if hasattr(w, 'structure') and w.structure is not None and hasattr(w.structure, 'tree'):
                current_item = w.structure.tree.currentItem()
                if current_item:
                    t = get_tree_tuple(current_item, 0)
                    if t:
                        item_type, item_id = t
                        if item_type == 'category' and isinstance(item_id, int):
                            return item_id
        except Exception:
            pass

        # 4) Первый доступный ID из бизнес-логики
        try:
            if hasattr(w, 'structure_business') and w.structure_business is not None:
                return w.structure_business.get_first_category_id()
        except Exception:
            pass

        return None
