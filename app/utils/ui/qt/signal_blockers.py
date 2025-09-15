from contextlib import contextmanager
import logging
from PyQt6.QtCore import QSignalBlocker

logger = logging.getLogger(__name__)


@contextmanager
def block_tree_signals(tree):
    """Блокирует сигналы QTreeView/QAbstractItemView и его selectionModel на время операций.

    Гарантирует безопасное освобождение блокировщиков даже при исключениях и устойчив к среде
    тестов, где selectionModel может быть недоступен.
    """
    tree_blocker = None
    sel_blocker = None
    try:
        try:
            tree_blocker = QSignalBlocker(tree)
            try:
                sel_model = tree.selectionModel()
            except Exception:
                sel_model = None
            sel_blocker = QSignalBlocker(sel_model) if sel_model else None
        except Exception:
            logger.debug("block_tree_signals: setup failed", exc_info=True)
        yield
    finally:
        sel_blocker = None
        tree_blocker = None
