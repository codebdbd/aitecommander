"""
Тесты для проверки исправлений функции import_full_structure():
1. Потокобезопасность (использование db_lock)
2. Неизменность входных данных (использование copy.deepcopy)
"""

import copy
import threading
import time
import unittest
from unittest.mock import patch, MagicMock, PropertyMock


from app.models.db import Database


class TestImportFullStructureFixes(unittest.TestCase):
    """Тесты исправлений функции import_full_structure()."""

    def setUp(self):
        """Настройка тестового окружения."""
        self.db = Database()
        # Используем in-memory БД, чтобы не затрагивать файловую
        self.db.db_path = ":memory:"
        
        # Тестовые данные для импорта
        self.test_data = [
            {
                "id": 1,
                "name": "Тестовая сфера",
                "position": 0,
                "sections": [
                    {
                        "id": 1,
                        "name": "Тестовый раздел",
                        "sphere_id": 1,
                        "position": 0,
                        "categories": [
                            {
                                "id": 1,
                                "name": "Тестовая категория",
                                "section_id": 1,
                                "position": 0,
                                "links": [
                                    {
                                        "id": 1,
                                        "name": "Тестовая ссылка",
                                        "url": "https://example.com",
                                        "type": "web",
                                        "category_id": 1,
                                        "position": 0
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]

    def test_input_data_immutability(self):
        """Тест: исходные данные остаются неизменными после импорта."""
        # Создаем глубокую копию исходных данных для сравнения
        original_data = copy.deepcopy(self.test_data)
        
        # Мокаем методы базы данных, чтобы избежать реальных операций с БД
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_conn.execute.return_value = MagicMock()

        with patch('app.models.db.Database.connection', new_callable=PropertyMock, return_value=mock_conn), \
             patch.object(self.db.spheres, 'upsert_sphere') as mock_sphere, \
             patch.object(self.db.sections, 'upsert_section') as mock_section, \
             patch.object(self.db.categories, 'upsert_category') as mock_category, \
             patch.object(self.db.links, 'upsert_link') as mock_link, \
             patch.object(self.db, 'backup') as mock_backup, \
             patch('app.models.db.db_lock'):

            # Выполняем импорт
            self.db.import_full_structure(self.test_data)
            
            # Проверяем, что исходные данные не изменились
            self.assertEqual(self.test_data, original_data, 
                           "Исходные данные были изменены функцией import_full_structure")
            
            # Проверяем, что все вложенные структуры остались на месте
            self.assertIn("sections", self.test_data[0], 
                         "Ключ 'sections' был удален из исходных данных")
            self.assertIn("categories", self.test_data[0]["sections"][0], 
                         "Ключ 'categories' был удален из исходных данных")
            self.assertIn("links", self.test_data[0]["sections"][0]["categories"][0], 
                         "Ключ 'links' был удален из исходных данных")

    def test_thread_safety_with_db_lock(self):
        """Тест: функция использует db_lock для потокобезопасности."""
        lock_acquired = []
        
        # Мокаем db_lock для отслеживания его использования
        class MockLock:
            def __enter__(self):
                lock_acquired.append(True)
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
        
        mock_lock = MockLock()
        
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_conn.execute.return_value = MagicMock()

        with patch('app.models.db.Database.connection', new_callable=PropertyMock, return_value=mock_conn), \
             patch.object(self.db.spheres, 'upsert_sphere'), \
             patch.object(self.db.sections, 'upsert_section'), \
             patch.object(self.db.categories, 'upsert_category'), \
             patch.object(self.db.links, 'upsert_link'), \
             patch.object(self.db, 'backup'), \
             patch('app.models.db.db_lock', mock_lock):

            # Выполняем импорт
            self.db.import_full_structure(self.test_data)
            
            # Проверяем, что db_lock был использован
            self.assertTrue(lock_acquired, "db_lock не был использован в import_full_structure")

    def test_concurrent_access_safety(self):
        """Тест: корректная работа при параллельных вызовах."""
        results = []
        errors = []

        # Общие моки для всех потоков, чтобы избежать гонок при установке патчей
        shared_conn = MagicMock()
        shared_conn.__enter__.return_value = shared_conn
        shared_conn.__exit__.return_value = None
        shared_conn.execute.return_value = MagicMock()

        def import_worker(worker_id):
            """Воркер для параллельного импорта."""
            try:
                # Создаем уникальные данные для каждого воркера
                worker_data = copy.deepcopy(self.test_data)
                worker_data[0]["name"] = f"Сфера воркера {worker_id}"

                # Имитируем небольшую задержку для создания условий гонки
                time.sleep(0.01)

                self.db.import_full_structure(worker_data)

                # Фиксируем имя, которое импортировалось в воркере
                results.append(worker_data[0]["name"])
                    
            except Exception as e:
                errors.append(f"Воркер {worker_id}: {e}")
        
        # Запускаем несколько потоков одновременно под общими патчами
        with patch('app.models.db.Database.connection', new_callable=PropertyMock, return_value=shared_conn), \
             patch.object(self.db.spheres, 'upsert_sphere'), \
             patch.object(self.db.sections, 'upsert_section'), \
             patch.object(self.db.categories, 'upsert_category'), \
             patch.object(self.db.links, 'upsert_link'), \
             patch.object(self.db, 'backup'), \
             patch('app.models.db.db_lock'):

            threads = []
            num_workers = 5

            for i in range(num_workers):
                thread = threading.Thread(target=import_worker, args=(i,))
                threads.append(thread)
                thread.start()

            # Ждем завершения всех потоков
            for thread in threads:
                thread.join()
        
        # Проверяем результаты
        self.assertEqual(len(errors), 0, f"Ошибки при параллельном выполнении: {errors}")
        self.assertEqual(len(results), num_workers, 
                        f"Не все воркеры завершились успешно. Получено результатов: {len(results)}")
        
        # Проверяем, что каждый воркер обработал свои уникальные данные
        expected_names = [f"Сфера воркера {i}" for i in range(num_workers)]
        self.assertEqual(sorted(results), sorted(expected_names), 
                        "Воркеры обработали неправильные данные")

    def test_deepcopy_usage(self):
        """Тест: функция использует copy.deepcopy для создания копии данных."""
        # Подготовим эталонную копию до мокирования deepcopy, чтобы не увеличивать счётчик вызовов
        expected_copy = copy.deepcopy(self.test_data)
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_conn.execute.return_value = MagicMock()

        with patch('app.models.db.copy.deepcopy') as mock_deepcopy, \
             patch('app.models.db.Database.connection', new_callable=PropertyMock, return_value=mock_conn), \
             patch.object(self.db.spheres, 'upsert_sphere'), \
             patch.object(self.db.sections, 'upsert_section'), \
             patch.object(self.db.categories, 'upsert_category'), \
             patch.object(self.db.links, 'upsert_link'), \
             patch.object(self.db, 'backup'), \
             patch('app.models.db.db_lock'):

            mock_deepcopy.return_value = expected_copy
            
            # Выполняем импорт
            self.db.import_full_structure(self.test_data)
            
            # Проверяем, что deepcopy был вызван с исходными данными
            mock_deepcopy.assert_called_once_with(self.test_data)

    def test_error_handling_preserves_input_data(self):
        """Тест: при ошибке исходные данные остаются неизменными."""
        original_data = copy.deepcopy(self.test_data)
        
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_conn.execute.side_effect = Exception("Тестовая ошибка БД")

        with patch('app.models.db.Database.connection', new_callable=PropertyMock, return_value=mock_conn), \
             patch('app.models.db.db_lock'):
            # Имитируем ошибку в процессе импорта через execute
            with patch.object(self.db, 'backup'):

                # Проверяем, что исключение поднимается
                with self.assertRaises(Exception):
                    self.db.import_full_structure(self.test_data)
            
            # Проверяем, что исходные данные не изменились даже при ошибке
            self.assertEqual(self.test_data, original_data, 
                           "Исходные данные были изменены даже при ошибке импорта")


if __name__ == '__main__':
    unittest.main()
