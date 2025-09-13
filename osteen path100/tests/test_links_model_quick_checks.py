from __future__ import annotations

from typing import Any, Dict, List

from PyQt6.QtCore import QCoreApplication, Qt

from app.utils.ui.dnd.link import extract_source_rows_from_mime
from app.utils.ui.dnd.mime import MimeDataParser, get_link_mime
from app.views.link.links_model import LinksTableModel


def _ensure_qcoreapp():
    # Минимальный цикл приложения Qt (без GUI), чтобы корректно работали модели/сигналы
    return QCoreApplication.instance() or QCoreApplication([])


def _mk_links(ids: List[int]) -> List[Dict[str, Any]]:
    return [
        {
            "id": i,
            "name": f"Name {i}",
            "last_used": i,
            "notes": f"n{i}",
            "is_favorite": bool(i % 2),
        }
        for i in ids
    ]


def _ids_from_model(model: LinksTableModel) -> List[int]:
    ids: List[int] = []
    for row in range(model.rowCount()):
        idx = model.index(row, 0)
        data = model.data(idx, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            ids.append(int(data.get("id")))
    return ids


def test_move_rows_contiguous_and_sparse():
    _ensure_qcoreapp()

    # Непрерывный диапазон
    model = LinksTableModel(_mk_links([1, 2, 3, 4, 5]))
    model.move_rows([1, 2], 5)  # переносим [2,3] в конец
    assert _ids_from_model(model) == [1, 4, 5, 2, 3]

    # Разрежённый набор
    model = LinksTableModel(_mk_links([1, 2, 3, 4, 5]))
    model.move_rows([0, 2, 4], 1)  # переносим 1,3,5 к позиции 1, сохраняя порядок
    assert _ids_from_model(model) == [2, 1, 3, 5, 4]


def test_sort_and_order_by_name():
    _ensure_qcoreapp()

    links = _mk_links([5, 3, 1, 4, 2])
    model = LinksTableModel(links)

    # По имени (Name X) — по возрастанию: 1..5
    model.sort(1, Qt.SortOrder.AscendingOrder)
    assert _ids_from_model(model) == [1, 2, 3, 4, 5]

    # По убыванию
    model.sort(1, Qt.SortOrder.DescendingOrder)
    assert _ids_from_model(model) == [5, 4, 3, 2, 1]


def test_mime_round_trip_extract_rows():
    _ensure_qcoreapp()

    # Готовим модель и таблицу-стаб
    model = LinksTableModel(_mk_links([10, 20, 30, 40]))

    class _FakeTable:
        def __init__(self, m):
            self._m = m

        def model(self):
            return self._m

        def get_link_at(self, row: int):
            idx = self._m.index(row, 0)
            data = self._m.data(idx, Qt.ItemDataRole.UserRole)
            return data if isinstance(data, dict) else None

    table = _FakeTable(model)

    # Создаём MIME с id 20 и 40 и проверяем, что восстановим правильные строки
    mime_type = get_link_mime()
    md = MimeDataParser.create_mime_data([20, 40], mime_type)

    class _FakeEvent:
        def __init__(self, mime):
            self._mime = mime

        def mimeData(self):
            return self._mime

    event = _FakeEvent(md)
    rows = extract_source_rows_from_mime(table, event, mime_type)
    # id 20 => row 1, id 40 => row 3
    assert rows == [1, 3]
