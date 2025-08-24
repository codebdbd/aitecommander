# app/utils/ui/dnd/base.py

import logging

logger = logging.getLogger(__name__)


class TreeHandlerBase:
    """Базовый класс для обработчиков дерева StructureTreeWidget.
    Инкапсулирует общую инициализацию: ссылку на виджет и логгер.
    """

    def __init__(self, tree_widget):
        self.tree_widget = tree_widget
