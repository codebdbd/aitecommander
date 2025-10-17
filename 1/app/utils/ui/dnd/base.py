# app/utils/ui/dnd/base.py

import logging

logger = logging.getLogger(__name__)


class TreeHandlerBase:
    """Base class for StructureTreeView handlers.
    Encapsulates common initialization: widget reference and logger.
    """

    def __init__(self, tree_widget):
        self.tree_widget = tree_widget
