import logging
from types import SimpleNamespace

import pytest

from app.controllers.ui.category_tiles_controller import CategoryTilesController


class BusinessMock:
    def __init__(self, categories=None, raise_err: Exception | None = None):
        self.calls = []
        self._cats = categories if categories is not None else []
        self._err = raise_err

    def get_categories(self, section_id: int):
        self.calls.append(("get_categories", section_id))
        if self._err:
            raise self._err
        return list(self._cats)


class UIStateMock:
    def __init__(self, raise_err: Exception | None = None):
        self.calls = []
        self._err = raise_err

    def switch_to_category_tiles(self, categories):
        self.calls.append(("switch", list(categories)))
        if self._err:
            raise self._err


def test_refresh_success(caplog):
    caplog.set_level(logging.DEBUG)
    ui_state = UIStateMock()
    business = BusinessMock(categories=[{"id": 1}, {"id": 2}])
    main = SimpleNamespace(ui_state=ui_state)

    ctrl = CategoryTilesController(
        main_window=main, ui_state=ui_state, structure_business=business
    )
    ctrl.refresh(10)

    assert business.calls == [("get_categories", 10)]
    assert ui_state.calls == [("switch", [{"id": 1}, {"id": 2}])]


def test_refresh_invalid_section_id(caplog):
    caplog.set_level(logging.WARNING)
    ui_state = UIStateMock()
    business = BusinessMock(categories=[{"id": 1}])
    main = SimpleNamespace(ui_state=ui_state)

    ctrl = CategoryTilesController(
        main_window=main, ui_state=ui_state, structure_business=business
    )
    ctrl.refresh(0)
    ctrl.refresh(None)  # type: ignore[arg-type]

    # Ничего не вызывается
    assert business.calls == []
    assert ui_state.calls == []


def test_refresh_missing_ui_state(caplog):
    caplog.set_level(logging.WARNING)
    business = BusinessMock(categories=[{"id": 1}])
    main = SimpleNamespace(ui_state=None)
    with pytest.raises(ValueError):
        CategoryTilesController(
            main_window=main, ui_state=None, structure_business=business
        )


def test_refresh_missing_business(caplog):
    caplog.set_level(logging.WARNING)
    ui_state = UIStateMock()
    # main.structure_business существует, но мы передаём None, контроллер возьмёт из main, которого нет
    main = SimpleNamespace(ui_state=ui_state, structure_business=None)
    with pytest.raises(ValueError):
        CategoryTilesController(
            main_window=main, ui_state=ui_state, structure_business=None
        )  # type: ignore[arg-type]


def test_refresh_logs_on_business_error(caplog):
    caplog.set_level(logging.ERROR)
    ui_state = UIStateMock()
    business = BusinessMock(raise_err=RuntimeError("boom"))
    main = SimpleNamespace(ui_state=ui_state)

    ctrl = CategoryTilesController(
        main_window=main, ui_state=ui_state, structure_business=business
    )
    ctrl.refresh(3)

    # Ошибка не выбрасывается наружу, но логируется
    assert any(
        "CategoryTilesController.refresh" in rec.getMessage() for rec in caplog.records
    )


def test_clear_success(caplog):
    ui_state = UIStateMock()
    main = SimpleNamespace(ui_state=ui_state)

    ctrl = CategoryTilesController(
        main_window=main, ui_state=ui_state, structure_business=BusinessMock()
    )
    ctrl.clear()

    assert ui_state.calls == [("switch", [])]


def test_clear_logs_when_ui_missing(caplog):
    caplog.set_level(logging.WARNING)
    main = SimpleNamespace(ui_state=None)
    with pytest.raises(ValueError):
        CategoryTilesController(
            main_window=main, ui_state=None, structure_business=BusinessMock()
        )


def test_clear_logs_on_error(caplog):
    caplog.set_level(logging.ERROR)
    ui_state = UIStateMock(raise_err=RuntimeError("boom"))
    main = SimpleNamespace(ui_state=ui_state)

    ctrl = CategoryTilesController(
        main_window=main, ui_state=ui_state, structure_business=BusinessMock()
    )
    ctrl.clear()

    assert any(
        "CategoryTilesController.clear" in rec.getMessage() for rec in caplog.records
    )
