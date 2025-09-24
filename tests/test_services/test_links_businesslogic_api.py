import pytest
from PyQt6.QtCore import QObject
from app.controllers.business.links_business import LinksBusinessLogic
from app.models.db import Database

class DummyDB:
    class links:
        @staticmethod
        def get_links(category_id):
            return [{"id": 1, "name": "Test", "category_id": category_id}]
        @staticmethod
        def get_all_links():
            return [{"id": 1, "name": "Test"}]
        @staticmethod
        def create_or_update_link(link_data):
            return 42
        @staticmethod
        def delete_link(link_id):
            return True
        @staticmethod
        def get_link_by_id(link_id):
            return {"id": link_id, "name": "Test"}
        @staticmethod
        def get_recent_links(limit):
            return [{"id": 1, "name": "Test"}]
        @staticmethod
        def get_favorite_links():
            return [{"id": 1, "name": "Fav"}]
        @staticmethod
        def clear_favorites():
            return True
        @staticmethod
        def count_favorites():
            return 1
        @staticmethod
        def search_links(q):
            return [{"id": 1, "name": "Test", "url": q}]
        @staticmethod
        def batch_update(data):
            return True
        @staticmethod
        def reorder(ids):
            return True
        @staticmethod
        def update_last_used(link_id):
            return True
        @staticmethod
        def get_next_position(category_id):
            return 5

@pytest.fixture
def logic():
    return LinksBusinessLogic(db=DummyDB())

def test_get_links(logic):
    res = logic._get_links(1)
    assert isinstance(res, list)
    assert res[0]["category_id"] == 1

def test_save_link(logic):
    link = {"name": "Test", "url": "http://x", "type": "url", "category_id": 1}
    result = logic._save_link(link)
    assert result == 42

def test_get_link_by_id(logic):
    res = logic._get_link_by_id(10)
    assert res["id"] == 10

def test_get_recent_links(logic):
    res = logic._get_recent_links(5)
    assert isinstance(res, list)

def test_get_favorite_links(logic):
    res = logic._get_favorite_links()
    assert isinstance(res, list)

def test_clear_favorites(logic):
    assert logic._clear_favorites() is True

def test_batch_update_links(logic):
    data = [{"id": 1, "name": "A", "category_id": 1, "url": "u", "type": "url"}]
    assert logic._batch_update_links(data) is True

def test_get_next_position(logic):
    assert logic._get_next_position(1) == 5
