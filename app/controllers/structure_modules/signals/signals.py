# app/controllers/structure_modules/signals.py

"""Сигналы для асинхронных операций структуры.

Переведён на новый фасад `run_db` вместо легаси-воркеров из
`app.utils.db.db_workers`. Для сохранения совместимости определён локальный
класс сигналов с тем же интерфейсом, что и `StructureWorkerSignals`.
"""

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from ..models.types import (
    SphereData,
    SectionData,
    CategoryData,
    LinkData,
    SearchResultItem,
    AnyItemData,
)

logger = logging.getLogger(__name__)


class StructureSignals(QObject):
    """Сигналы для асинхронных операций со структурой (совместимы с легаси).

    Повторяет интерфейс `StructureWorkerSignals` из app.utils.db.db_workers.
    """

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

    # Загрузка данных - строгая типизация для PyQt6
    spheres_loaded: pyqtSignal = pyqtSignal(list)  # List[SphereData]
    structure_loaded: pyqtSignal = pyqtSignal(list, int)  # List[SectionData], sphere_id
    sections_loaded: pyqtSignal = pyqtSignal(list, int)  # List[SectionData], sphere_id
    categories_loaded: pyqtSignal = pyqtSignal(list, int)  # List[CategoryData], section_id
    links_loaded: pyqtSignal = pyqtSignal(list, int, int)  # List[LinkData], category_id, task_id

    # Поиск
    search_results: pyqtSignal = pyqtSignal(list)  # List[SearchResultItem]

    # Подсчет
    count_finished: pyqtSignal = pyqtSignal(int, list, object)

    # CRUD - строгая типизация payload
    item_created: pyqtSignal = pyqtSignal(str, int, dict)  # item_type, parent_id, AnyItemData
    item_updated: pyqtSignal = pyqtSignal(str, int, dict)  # item_type, item_id, AnyItemData
    item_deleted: pyqtSignal = pyqtSignal(str, int, dict)  # item_type, item_id, AnyItemData

    # Состояние операций
    operation_started: pyqtSignal = pyqtSignal(str)
    operation_finished: pyqtSignal = pyqtSignal(str)
    loading_started: pyqtSignal = pyqtSignal()

    # Обновление UI
    update_ui: pyqtSignal = pyqtSignal(int)

    # Информация о ссылках
    link_info_finished: pyqtSignal = pyqtSignal(dict)

    # Ошибки - строгая типизация
    error: pyqtSignal = pyqtSignal(str, str)  # title, message
    simple_error: pyqtSignal = pyqtSignal(str)  # message
