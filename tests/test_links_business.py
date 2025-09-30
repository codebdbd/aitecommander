"""Тесты для бизнес-логики ссылок (LinksBusinessLogic)."""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from PyQt6.QtCore import QObject


@pytest.fixture
def mock_db():
    """Mock базы данных."""
    db = Mock()
    db.links = Mock()
    db.links.get_links_by_category = Mock(return_value=[
        {'id': 1, 'name': 'Link 1', 'category_id': 10},
        {'id': 2, 'name': 'Link 2', 'category_id': 10},
    ])
    db.links.get_all_links = Mock(return_value=[])
    db.links.search_links = Mock(return_value=[])
    db.links.get_favorite_links = Mock(return_value=[])
    db.links.get_recent_links = Mock(return_value=[])
    db.links.count_favorites = Mock(return_value=5)
    db.links.create_or_update_link = Mock(return_value=1)
    db.links.delete_link = Mock(return_value=True)
    db.links.get_link_by_id = Mock(return_value={'id': 1, 'is_favorite': False})
    return db


@pytest.fixture
def business_logic(mock_db):
    """Fixture для LinksBusinessLogic с mock зависимостями."""
    from app.controllers.business.links_business import LinksBusinessLogic
    
    # Патчим run_db чтобы выполнялось синхронно
    with patch('app.controllers.business.links_business.run_db') as mock_run_db:
        # Настраиваем run_db для синхронного выполнения
        def sync_run_db(func, on_finished=None, on_error=None, **kwargs):
            try:
                result = func()
                if on_finished:
                    on_finished(result)
            except Exception as e:
                if on_error:
                    on_error(e)
        
        mock_run_db.side_effect = sync_run_db
        
        business = LinksBusinessLogic(mock_db)
        business._run_db_mock = mock_run_db  # Сохраняем для проверок
        
        yield business


class TestLinksBusinessLogic:
    """Тесты для LinksBusinessLogic."""
    
    def test_initialization(self, business_logic):
        """Тест инициализации бизнес-логики."""
        assert business_logic is not None
        assert business_logic.db is not None
        assert hasattr(business_logic, 'links_loaded')
        assert hasattr(business_logic, 'search_results_ready')
    
    def test_load_links_valid_category(self, business_logic, mock_db):
        """Тест загрузки ссылок для валидной категории."""
        category_id = 10
        
        # Подключаем обработчик сигнала
        received_links = []
        business_logic.links_loaded.connect(lambda links: received_links.append(links))
        
        # Загружаем ссылки
        business_logic.load_links(category_id)
        
        # Проверяем, что БД вызвана
        mock_db.links.get_links_by_category.assert_called_once_with(category_id)
        
        # Проверяем, что сигнал испущен
        assert len(received_links) == 1
        assert len(received_links[0]) == 2
    
    def test_load_links_invalid_category_id(self, business_logic):
        """Тест загрузки с невалидным category_id."""
        # Проверяем, что выбрасывается исключение или обрабатывается
        with pytest.raises(ValueError):
            business_logic.load_links(0)
        
        with pytest.raises(ValueError):
            business_logic.load_links(-1)
    
    def test_search_links_with_query(self, business_logic, mock_db):
        """Тест поиска ссылок с запросом."""
        query = "python"
        mock_db.links.search_links.return_value = [
            {'id': 1, 'name': 'Python Docs'},
        ]
        
        results = []
        business_logic.search_results_ready.connect(lambda r: results.append(r))
        
        business_logic.search_links(query)
        
        mock_db.links.search_links.assert_called_once_with(query)
        assert len(results) == 1
        assert len(results[0]) == 1
    
    def test_search_links_empty_query(self, business_logic, mock_db):
        """Тест поиска с пустым запросом (должен вернуть все ссылки)."""
        mock_db.links.get_all_links.return_value = [
            {'id': 1}, {'id': 2}, {'id': 3}
        ]
        
        results = []
        business_logic.search_results_ready.connect(lambda r: results.append(r))
        
        business_logic.search_links("")
        
        mock_db.links.get_all_links.assert_called_once()
        assert len(results) == 1
        assert len(results[0]) == 3
    
    def test_get_favorite_links(self, business_logic, mock_db):
        """Тест получения избранных ссылок (синхронный)."""
        mock_db.links.get_favorite_links.return_value = [
            {'id': 1, 'is_favorite': True},
            {'id': 2, 'is_favorite': True},
        ]
        
        favorites = business_logic.get_favorite_links()
        
        assert len(favorites) == 2
        mock_db.links.get_favorite_links.assert_called_once()
    
    def test_load_favorite_links_async(self, business_logic, mock_db):
        """Тест асинхронной загрузки избранного."""
        mock_db.links.get_favorite_links.return_value = [
            {'id': 1, 'is_favorite': True}
        ]
        
        results = []
        business_logic.favorite_links_loaded.connect(lambda r: results.append(r))
        
        business_logic.load_favorite_links()
        
        assert len(results) == 1
        assert len(results[0]) == 1
    
    def test_get_recent_links(self, business_logic, mock_db):
        """Тест получения недавних ссылок."""
        mock_db.links.get_recent_links.return_value = [
            {'id': 1, 'last_used': '2025-09-30'},
        ]
        
        recent = business_logic.get_recent_links(limit=10)
        
        assert len(recent) == 1
        mock_db.links.get_recent_links.assert_called_once_with(10)
    
    def test_count_favorites(self, business_logic, mock_db):
        """Тест подсчёта избранных."""
        mock_db.links.count_favorites.return_value = 15
        
        counts = []
        business_logic.favorite_count_changed.connect(
            lambda count, links, link: counts.append(count)
        )
        
        business_logic.count_favorites()
        
        assert len(counts) == 1
        assert counts[0] == 15
    
    def test_delete_link(self, business_logic, mock_db):
        """Тест удаления ссылки."""
        link_id = 42
        
        deleted_ids = []
        business_logic.link_deleted.connect(lambda id_: deleted_ids.append(id_))
        
        business_logic.delete_link(link_id)
        
        mock_db.links.delete_link.assert_called_once_with(link_id)
        assert link_id in deleted_ids
    
    def test_delete_link_invalid_id(self, business_logic):
        """Тест удаления с невалидным ID."""
        # Невалидные ID должны вызывать ошибку или игнорироваться
        with pytest.raises(ValueError):
            business_logic.delete_link(0)
        
        with pytest.raises(ValueError):
            business_logic.delete_link(-1)
    
    def test_toggle_favorite(self, business_logic, mock_db):
        """Тест переключения избранного."""
        link = {'id': 1, 'name': 'Test Link', 'is_favorite': False}
        
        # Mock get_link_by_id для чтения текущего состояния
        mock_db.links.get_link_by_id.return_value = {
            'id': 1,
            'is_favorite': False,
            'name': 'Test Link'
        }
        
        mock_db.links.create_or_update_link.return_value = 1
        
        updated = []
        business_logic.link_updated.connect(lambda l: updated.append(l))
        
        business_logic.toggle_favorite(link)
        
        # Проверяем, что статус изменился
        assert len(updated) > 0 or mock_db.links.create_or_update_link.called
    
    def test_save_link_async(self, business_logic, mock_db):
        """Тест асинхронного сохранения ссылки."""
        link_data = {
            'name': 'New Link',
            'url': 'https://example.com',
            'category_id': 10,
            'type': 'web'
        }
        
        mock_db.links.create_or_update_link.return_value = 123
        
        saved = []
        business_logic.link_updated.connect(lambda l: saved.append(l))
        
        business_logic.save_link_async(link_data)
        
        assert len(saved) == 1
        assert saved[0]['id'] == 123
    
    def test_cache_invalidation(self, business_logic, mock_db):
        """Тест инвалидации кеша при изменениях."""
        # Загружаем ссылки (попадают в кеш)
        business_logic.load_links(10)
        
        # Изменяем ссылку (должен инвалидировать кеш)
        link_data = {'id': 1, 'name': 'Updated', 'category_id': 10}
        business_logic.save_link_async(link_data)
        
        # Кеш должен быть очищен
        assert business_logic._cache == {} or len(business_logic._cache) == 0


class TestLinksBusinessValidation:
    """Тесты валидации в бизнес-логике."""
    
    def test_validate_link_id_positive(self, business_logic):
        """Позитивные ID валидны."""
        assert business_logic._validate_link_id(1) is True
        assert business_logic._validate_link_id(9999) is True
    
    def test_validate_link_id_zero(self, business_logic):
        """ID = 0 невалиден."""
        assert business_logic._validate_link_id(0) is False
    
    def test_validate_link_id_negative(self, business_logic):
        """Отрицательные ID невалидны."""
        assert business_logic._validate_link_id(-1) is False
        assert business_logic._validate_link_id(-100) is False
    
    def test_validate_category_id_positive(self, business_logic):
        """Позитивные category_id валидны."""
        assert business_logic._validate_category_id(1) is True
    
    def test_validate_category_id_zero(self, business_logic):
        """category_id = 0 невалиден."""
        assert business_logic._validate_category_id(0) is False


class TestLinksBusinessErrors:
    """Тесты обработки ошибок."""
    
    def test_error_signal_on_db_failure(self, business_logic, mock_db):
        """При ошибке БД испускается error_occurred."""
        mock_db.links.get_links_by_category.side_effect = Exception("DB Error")
        
        errors = []
        business_logic.error_occurred.connect(lambda e: errors.append(e))
        
        business_logic.load_links(10)
        
        assert len(errors) == 1
        assert "DB Error" in str(errors[0]) or "error" in str(errors[0]).lower()
    
    def test_graceful_handling_of_none_results(self, business_logic, mock_db):
        """Graceful обработка None от БД."""
        mock_db.links.get_links_by_category.return_value = None
        
        results = []
        business_logic.links_loaded.connect(lambda r: results.append(r))
        
        business_logic.load_links(10)
        
        # Должен вернуть пустой список вместо None
        assert len(results) == 1
        assert results[0] == [] or results[0] is not None
