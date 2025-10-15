# app/controllers/structure_modules/signals.py

"""Signals for asynchronous structure operations."""

from PyQt6.QtCore import QObject, pyqtSignal


class StructureSignals(QObject):
    """Signals for asynchronous structure operations (legacy compatible).

    Replicates interface of `StructureWorkerSignals` from app.utils.db.db_workers.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    # Data loading signals
    spheres_loaded = pyqtSignal(list)  # List[SphereData]
    structure_loaded = pyqtSignal(list, int)  # List[SectionData], sphere_id
    sections_loaded = pyqtSignal(list, int)  # List[SectionData], sphere_id
    categories_loaded = pyqtSignal(list, int)  # List[CategoryData], section_id
    links_loaded = pyqtSignal(list, int, int)  # List[LinkData], category_id, task_id

    # Search signals
    search_results = pyqtSignal(list)  # List[SearchResultItem]

    # Count signals
    count_finished = pyqtSignal(int, list, object)

    # CRUD signals
    item_created = pyqtSignal(str, int, dict)  # item_type, parent_id, AnyItemData
    item_updated = pyqtSignal(str, int, dict)  # item_type, item_id, AnyItemData
    item_deleted = pyqtSignal(str, int, dict)  # item_type, item_id, AnyItemData

    # Operation state signals
    operation_started = pyqtSignal(str)
    operation_finished = pyqtSignal(str)
    loading_started = pyqtSignal()

    # UI Update signals
    update_ui = pyqtSignal(int)

    # Link information signals
    link_info_finished = pyqtSignal(dict)

    # Error signals
    error = pyqtSignal(str, str)  # title, message
    simple_error = pyqtSignal(str)  # message
