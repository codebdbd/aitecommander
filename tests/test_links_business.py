"""Актуальные тесты для бизнес-логики ссылок (LinksBusinessLogic)."""

from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_db():
    db = Mock()
    db.links = Mock()
    db.links.get_links = Mock(return_value=[
        {"id": 1, "name": "Link 1", "category_id": 10},
        {"id": 2, "name": "Link 2", "category_id": 10},
    ])
    db.links.get_all_links = Mock(return_value=[])
    db.links.search_links = Mock(return_value=[])
    db.links.get_favorite_links = Mock(return_value=[])
    db.links.get_recent_links = Mock(return_value=[])
    db.links.count_favorites = Mock(return_value=5)
    db.links.create_or_update_link = Mock(return_value=1)
    db.links.delete_link = Mock(return_value=True)
    db.links.get_link_by_id = Mock(return_value={"id": 1, "is_favorite": False})
    return db


@pytest.fixture
def business_logic(mock_db, qtbot):
    from app.controllers.business.links_business import LinksBusinessLogic

    # Патчим run_db на синхронное выполнение, имитируя вызов из воркер-потока
    with patch("app.controllers.business.links_business.run_db") as mock_run_db:
        def sync_run_db(func, on_finished=None, on_error=None, **kwargs):
            try:
                result = func()
                if on_finished:
                    on_finished(result)
            except Exception as e:
                if on_error:
                    on_error(e)

        mock_run_db.side_effect = sync_run_db
        bl = LinksBusinessLogic(mock_db)
        qtbot.addWidget(bl) if hasattr(qtbot, "addWidget") else None  # QObject ownership
        yield bl


class TestLinksBusinessLogic:
    def test_initialization(self, business_logic):
        assert business_logic is not None
        assert business_logic.db is not None
        assert hasattr(business_logic, "links_loaded")
        assert hasattr(business_logic, "search_results_ready")

    def test_load_links_valid_category(self, business_logic, mock_db):
        category_id = 10
        received = []

        def on_loaded(links, cid, task_id):
            received.append((links, cid, task_id))

        business_logic.links_loaded.connect(on_loaded)
        business_logic.load_links(category_id)

        mock_db.links.get_links.assert_called_once_with(category_id)
        assert len(received) == 1
        assert received[0][1] == category_id
        assert isinstance(received[0][2], int)
        assert len(received[0][0]) == 2

    def test_search_links_with_query(self, business_logic, mock_db):
        query = "python"
        mock_db.links.search_links.return_value = [{"id": 1, "name": "Python Docs"}]

        results = []
        business_logic.search_results_ready.connect(lambda r: results.append(r))

        business_logic.search_links(query)

        mock_db.links.search_links.assert_called_once_with(query)
        assert len(results) == 1 and len(results[0]) == 1

    def test_search_links_empty_query(self, business_logic, mock_db):
        mock_db.links.get_all_links.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
        results = []
        business_logic.search_results_ready.connect(lambda r: results.append(r))
        business_logic.search_links("")
        mock_db.links.get_all_links.assert_called_once()
        assert len(results) == 1 and len(results[0]) == 3

    def test_get_favorite_links_sync(self, business_logic, mock_db):
        mock_db.links.get_favorite_links.return_value = [
            {"id": 1, "is_favorite": True},
            {"id": 2, "is_favorite": True},
        ]
        favorites = business_logic.get_favorite_links()
        assert len(favorites) == 2
        mock_db.links.get_favorite_links.assert_called_once()

    def test_load_favorite_links_async(self, business_logic, mock_db):
        mock_db.links.get_favorite_links.return_value = [{"id": 1, "is_favorite": True}]
        results = []
        business_logic.favorite_links_loaded.connect(lambda r: results.append(r))
        business_logic.load_favorite_links()
        assert len(results) == 1 and len(results[0]) == 1

    def test_get_recent_links_sync(self, business_logic, mock_db):
        mock_db.links.get_recent_links.return_value = [{"id": 1, "last_used": "2025-09-30"}]
        recent = business_logic.get_recent_links(limit=10)
        assert len(recent) == 1
        mock_db.links.get_recent_links.assert_called_once_with(10)

    def test_count_favorites_signal(self, business_logic, mock_db):
        mock_db.links.count_favorites.return_value = 15
        payloads = []

        def on_counted(count, links, link):
            payloads.append((count, links, link))

        business_logic.favorites_counted.connect(on_counted)
        business_logic.count_favorites()
        assert len(payloads) == 1 and payloads[0][0] == 15

    def test_delete_link_valid(self, business_logic, mock_db):
        link_id = 42
        deleted_ids = []
        business_logic.link_deleted.connect(lambda id_: deleted_ids.append(id_))
        business_logic.delete_link(link_id)
        mock_db.links.delete_link.assert_called_once_with(link_id)
        assert link_id in deleted_ids

    def test_delete_link_invalid_is_ignored(self, business_logic, mock_db):
        business_logic.delete_link(0)
        business_logic.delete_link(-1)
        mock_db.links.delete_link.assert_not_called()

    def test_toggle_favorite(self, business_logic, mock_db):
        link = {"id": 1, "name": "Test Link", "is_favorite": False}
        mock_db.links.get_link_by_id.return_value = {"id": 1, "is_favorite": False, "name": "Test Link"}
        mock_db.links.create_or_update_link.return_value = 1
        # Сигнал link_updated приходит после save_link_async/_on_link_saved; здесь достаточно убедиться, что сервис вызван
        business_logic.toggle_favorite(link)
        assert mock_db.links.create_or_update_link.called

    def test_save_link_async_emits_updated(self, business_logic, mock_db):
        link_data = {"name": "New Link", "url": "https://example.com", "category_id": 10, "type": "web"}
        mock_db.links.create_or_update_link.return_value = 123
        saved = []
        business_logic.link_updated.connect(lambda ld: saved.append(ld))
        business_logic.save_link_async(link_data)
        assert len(saved) == 1 and saved[0]["id"] == 123

    def test_cache_invalidation_on_save(self, business_logic):
        # Непосредственно проверяем, что инвалидация очищает локальный кеш
        business_logic._cache["recent_links_10"] = [1]
        assert business_logic._cache
        business_logic._invalidate_cache()
        assert not business_logic._cache


class TestLinksBusinessErrors:
    def test_error_signal_on_db_failure_and_pending_cleanup(self, business_logic, mock_db):
        # Провоцируем исключение в get_links
        mock_db.links.get_links.side_effect = Exception("DB Error")
        errors = []
        business_logic.error_occurred.connect(lambda e: errors.append(e))
        # Запускаем
        business_logic.load_links(10)
        # error_occurred должен сработать, pending_tasks очищен
        assert len(errors) == 1
        assert business_logic.pending_tasks == {}

    def test_graceful_handling_of_none_results(self, business_logic, mock_db):
        mock_db.links.get_links.return_value = None
        results = []
        business_logic.links_loaded.connect(lambda links, cid, tid: results.append(links))
        business_logic.load_links(10)
        assert len(results) == 1 and results[0] == []
