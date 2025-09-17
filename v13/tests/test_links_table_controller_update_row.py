import types

import pytest

from app.controllers.ui.links.table_controller import LinksTableController


class DummyCategoryProvider:
    def __init__(self, current_category_id=1):
        self.current_category_id = current_category_id


class FakeTableMissingMethod:
    """Не реализует update_link_by_id — должен привести к явной ошибке при создании контроллера."""

    def populate(self, links, mode: str = "default"):
        pass


class FakeTableTypeError:
    def update_link_by_id(self, link):
        # Симулируем проблему неверных данных
        raise TypeError("bad link_dict")

    def populate(self, links, mode: str = "default"):
        pass


class FakeTableRuntimeError:
    def update_link_by_id(self, link):
        # Неожиданная ошибка — должна пробрасываться
        raise RuntimeError("unexpected failure")

    def populate(self, links, mode: str = "default"):
        pass


def test_update_row_missing_method_raises_on_init():
    main = types.SimpleNamespace()
    category_provider = DummyCategoryProvider()
    with pytest.raises(TypeError):
        LinksTableController(
            main,
            table=FakeTableMissingMethod(),
            links_business=object(),
            category_provider=category_provider,
        )


def test_update_row_catches_typeerror_valueerror_and_does_not_raise():
    main = types.SimpleNamespace()
    category_provider = DummyCategoryProvider()
    ctrl = LinksTableController(
        main,
        table=FakeTableTypeError(),
        links_business=object(),
        category_provider=category_provider,
    )
    # Должно отработать без исключения
    ctrl.update_row({"id": 1})


def test_update_row_unexpected_exception_propagates():
    main = types.SimpleNamespace()
    category_provider = DummyCategoryProvider()
    ctrl = LinksTableController(
        main,
        table=FakeTableRuntimeError(),
        links_business=object(),
        category_provider=category_provider,
    )
    with pytest.raises(RuntimeError):
        ctrl.update_row({"id": 1})
