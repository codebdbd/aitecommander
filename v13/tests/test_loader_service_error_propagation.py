from __future__ import annotations

import pytest

from app.controllers.structure_services.loader import LoaderService


class DummyLogger:
    def __init__(self):
        self.last = None

    def error(self, *args, **kwargs):  # pragma: no cover (we just need it not to crash)
        self.last = (args, kwargs)


class DummyModelOK:
    def __init__(self, sections=None, cats=None):
        self._sections = sections or []
        self._cats = cats or {}

    def get_sections(self, sphere_id):
        return list(self._sections)

    def get_categories(self, section_id):
        return list(self._cats.get(section_id, []))


class DummyModelFailSections:
    def get_sections(self, sphere_id):  # raises
        raise RuntimeError("db connection failed")


class DummyModelFailCategories:
    def __init__(self):
        self._called = False

    def get_sections(self, sphere_id):
        return [{"id": 1}, {"id": 2}]

    def get_categories(self, section_id):  # raises on first call
        raise RuntimeError("db read error")


def test_loader_returns_empty_for_no_data():
    loader = LoaderService()
    logger = DummyLogger()
    model = DummyModelOK(sections=[], cats={})

    result = loader.load_structure_from_db(model, sphere_id=1, logger=logger)
    assert result == []


def test_loader_propagates_error_from_get_sections():
    loader = LoaderService()
    logger = DummyLogger()
    model = DummyModelFailSections()

    with pytest.raises(RuntimeError):
        loader.load_structure_from_db(model, sphere_id=1, logger=logger)


def test_loader_propagates_error_from_get_categories():
    loader = LoaderService()
    logger = DummyLogger()
    model = DummyModelFailCategories()

    with pytest.raises(RuntimeError):
        loader.load_structure_from_db(model, sphere_id=1, logger=logger)
