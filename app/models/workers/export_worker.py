"""Worker для экспорта структуры данных в фоновом потоке."""
import logging
from typing import Dict, List

from .base_worker import DatabaseWorker

logger = logging.getLogger(__name__)


class ExportStructureWorker(DatabaseWorker):
    """Worker для выполнения export_full_structure() в фоновом потоке.
    
    Экспортирует полную структуру данных из БД в формате словаря.
    """
    
    def do_work(self, connection) -> Dict[str, List]:
        """Выполняет экспорт структуры.
        
        Returns:
            Словарь с ключами spheres, sections, categories, links
        """
        self.emit_progress(0, 4, "Экспорт сфер...")
        
        # Экспорт сфер
        spheres_rows = connection.execute(
            "SELECT * FROM sphere ORDER BY position"
        ).fetchall()
        spheres = [dict(row) for row in spheres_rows]
        
        if self.is_cancelled:
            return {}
        
        self.emit_progress(1, 4, "Экспорт разделов...")
        
        # Экспорт разделов
        sections_rows = connection.execute(
            "SELECT * FROM section ORDER BY sphere_id, position"
        ).fetchall()
        sections = [dict(row) for row in sections_rows]
        
        if self.is_cancelled:
            return {}
        
        self.emit_progress(2, 4, "Экспорт категорий...")
        
        # Экспорт категорий
        categories_rows = connection.execute(
            "SELECT * FROM category ORDER BY section_id, position"
        ).fetchall()
        categories = [dict(row) for row in categories_rows]
        
        if self.is_cancelled:
            return {}
        
        self.emit_progress(3, 4, "Экспорт ссылок...")
        
        # Экспорт ссылок
        links_rows = connection.execute(
            "SELECT * FROM link ORDER BY category_id, position"
        ).fetchall()
        links = [dict(row) for row in links_rows]
        
        self.emit_progress(4, 4, "Экспорт завершен")
        
        return {
            "spheres": spheres,
            "sections": sections,
            "categories": categories,
            "links": links
        }
