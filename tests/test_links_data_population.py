from typing import Dict, List, Optional

from PyQt6.QtCore import Qt

from app.views.link.data_management import DataManagementMixin
from app.views.link.population_manager import PopulationManagerMixin
from app.views.link.row_operations import RowOperationsMixin


class DummyIndex:
    def __init__(self, row: int, column: int):
        self._row = row
        self._column = column

    def row(self) -> int:
        return self._row

    def column(self) -> int:
        return self._column


class DummyModel:
    """Простая модель, которая хранит список ссылок (dict) и поддерживает нужные методы."""

    def __init__(self, links: Optional[List[Dict]] = None):
        self._links: List[Dict] = list(links or [])

    # Методы, используемые DataManagementMixin и PopulationManagerMixin
    def rowCount(self) -> int:
        return len(self._links)

    def index(self, row: int, column: int) -> DummyIndex:
        return DummyIndex(row, column)

    def data(self, index: DummyIndex, role: int):
        if role == Qt.ItemDataRole.UserRole and 0 <= index.row() < len(self._links):
            return self._links[index.row()]
        return None

    # Методы, используемые RowOperationsMixin
    def insert_link(self, row: int, link: Dict) -> bool:
        if row < 0 or row > len(self._links):
            return False
        self._links.insert(row, dict(link))
        return True

    def update_link(self, row: int, link: Dict) -> bool:
        if row < 0 or row >= len(self._links):
            return False
        self._links[row] = dict(link)
        return True

    def remove_row(self, row: int) -> bool:
        if row < 0 or row >= len(self._links):
            return False
        del self._links[row]
        return True

    def set_links(self, links: List[Dict]) -> None:
        self._links = list(links or [])


class DummySelectionModel:
    def __init__(self, selected_rows: Optional[List[int]] = None):
        self._selected = list(selected_rows or [])

    def selectedRows(self) -> List[DummyIndex]:
        return [DummyIndex(r, 0) for r in self._selected]


class DummyScrollBar:
    def __init__(self):
        self._v = 0

    def value(self) -> int:
        return self._v

    def setValue(self, v: int) -> None:
        self._v = v


class DummyHeader:
    def __init__(
        self, sort_col: int = -1, sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ):
        self._sort_col = sort_col
        self._sort_order = sort_order
        self._blocked = False

    def sortIndicatorSection(self) -> int:
        return self._sort_col

    def sortIndicatorOrder(self) -> Qt.SortOrder:
        return self._sort_order

    def blockSignals(self, block: bool) -> None:
        self._blocked = bool(block)


class DummyViewport:
    def update(self):
        pass


class DummyView(DataManagementMixin, PopulationManagerMixin, RowOperationsMixin):
    """Минимальный вид таблицы ссылок, реализующий необходимые методы для миксинов."""

    def __init__(self, model: DummyModel):
        self._model = model
        self._current_links: Dict[int, Dict] = {}
        self._current_mode = "normal"
        self._sort_col = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._updates_enabled = True
        self._selection_model = DummySelectionModel()
        self._vscroll = DummyScrollBar()
        self._header = DummyHeader()
        self._viewport = DummyViewport()

    # API, с которым работают миксины
    def model(self) -> DummyModel:
        return self._model

    def setUpdatesEnabled(self, enabled: bool) -> None:
        self._updates_enabled = bool(enabled)

    def selectionModel(self) -> DummySelectionModel:
        return self._selection_model

    def verticalScrollBar(self) -> DummyScrollBar:
        return self._vscroll

    def horizontalHeader(self) -> DummyHeader:
        return self._header

    def sortByColumn(self, column: int, order: Qt.SortOrder) -> None:
        # Для целей тестов сортировка фактически не выполняется, только сохраняем состояние
        self._sort_col = column
        self._sort_order = order

    def viewport(self) -> DummyViewport:
        return self._viewport


def _cache_to_list(cache: Dict[int, Dict]) -> List[Dict]:
    return [cache[i] for i in sorted(cache.keys())]


def test_validate_cache_integrity_correct_and_incorrect():
    model = DummyModel(
        [
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B"},
        ]
    )
    view = DummyView(model)

    # Корректный кэш после перестроения
    view.rebuild_cache_from_items()
    assert view.validate_cache_integrity() is True

    # Некорректный размер кэша
    view._current_links = {0: {"id": 1}}  # размер 1 вместо 2
    assert view.validate_cache_integrity() is False

    # Некорректные индексы
    view._current_links = {0: {"id": 1}, 2: {"id": 999}}  # индекс 2 вне диапазона
    assert view.validate_cache_integrity() is False


def test_populate_incremental_add_update_remove_cache_matches_model():
    # Исходные данные: 2 ссылки
    initial = [
        {
            "id": 1,
            "name": "A",
            "is_favorite": False,
            "notes": "",
            "icon_path": "",
            "args": {},
        },
        {
            "id": 2,
            "name": "B",
            "is_favorite": False,
            "notes": "",
            "icon_path": "",
            "args": {},
        },
    ]
    model = DummyModel(initial)
    view = DummyView(model)

    # Первичное заполнение (вызовет _full_populate из populate)
    view.populate(initial, mode="normal")

    # Проверяем кэш соответствует модели
    view_cache_as_list = _cache_to_list(view._current_links)
    assert view_cache_as_list == initial

    # Изменения: 1) id=2 -> обновить имя; 2) id=3 -> добавить; 3) id=1 -> удалить
    updated = [
        {
            "id": 2,
            "name": "B2",
            "is_favorite": False,
            "notes": "",
            "icon_path": "",
            "args": {},
        },
        {
            "id": 3,
            "name": "C",
            "is_favorite": False,
            "notes": "",
            "icon_path": "",
            "args": {},
        },
    ]

    # Инкрементальное обновление
    view.populate(updated, mode="normal")

    # Ожидаемое состояние модели и кэша: [ {id:2,name:B2}, {id:3,name:C} ]
    expected_after = updated

    # Проверяем модель
    assert model.rowCount() == 2
    assert model.data(model.index(0, 0), Qt.ItemDataRole.UserRole)["id"] == 2
    assert model.data(model.index(0, 0), Qt.ItemDataRole.UserRole)["name"] == "B2"
    assert model.data(model.index(1, 0), Qt.ItemDataRole.UserRole)["id"] == 3

    # Проверяем кэш соответствует модели
    view_cache_as_list = _cache_to_list(view._current_links)
    assert view_cache_as_list == expected_after
