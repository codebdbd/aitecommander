# app/controllers/structure_modules/sphere_operations.py

"""Модуль для операций со сферами."""

import logging
from typing import Any, Callable, Dict, List, Optional

from app.models.structure_model import StructureModel

from .normalization import normalize_rows
from .base import BaseOperations


class SphereOperations(BaseOperations):
    """Класс для операций со сферами."""
    
    def get_spheres(self) -> List[Dict[str, Any]]:
        """Получает список всех сфер с гарантированной нормализацией."""
        def _get_spheres_operation():
            spheres_data = self.structure_model.get_spheres()
            result = spheres_data if spheres_data else []
            self.logger.debug(f"Загружено {len(result)} сфер")
            return result
        
        return self._exec_with_norm(
            _get_spheres_operation,
            "загрузить список сфер",
            default_return=[]
        )
    
    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные сферы по ID с гарантированной нормализацией."""
        def _get_sphere_operation():
            sphere_data = self.structure_model.get_sphere_by_id(sphere_id)
            if sphere_data:
                self.logger.debug(f"Найдена сфера {sphere_id}")
                return sphere_data
            else:
                self.logger.warning(f"Сфера {sphere_id} не найдена")
                return None
        
        return self._exec_with_norm(
            _get_sphere_operation,
            f"загрузить данные сферы {sphere_id}",
            default_return=None
        )
    
    def get_next_sphere_id(self, current_sphere_id: Optional[int]) -> Optional[int]:
        """Определяет и возвращает ID следующей сферы в списке (циклически)."""
        try:
            spheres = self.get_spheres()  # Теперь гарантированно возвращает List[Dict[str, Any]]
            if not spheres or len(spheres) < 2:
                self.logger.warning("Недостаточно сфер для переключения.")
                return None

            current_id = current_sphere_id
            if current_id is None:
                # spheres[0] гарантированно dict благодаря нормализации в get_spheres()
                return spheres[0]['id']

            # Все элементы spheres гарантированно dict благодаря нормализации
            sphere_ids = [s['id'] for s in spheres]
            try:
                current_index = sphere_ids.index(current_id)
                next_index = (current_index + 1) % len(sphere_ids)
                next_sphere_id = sphere_ids[next_index]
                self.logger.info(f"Следующая сфера для переключения: {next_sphere_id}")
                return next_sphere_id
            except ValueError:
                self.logger.warning(f"Текущая сфера с ID {current_id} не найдена в списке.")
                return spheres[0]['id']

        except Exception as e:
            self.logger.error(f"Ошибка получения сфер: Не удалось определить следующую сферу: {e}")
            return None
    
    def get_target_section_id(self, current_sphere_id: Optional[int]) -> Optional[int]:
        """Получает ID первого доступного раздела в текущей сфере."""
        if current_sphere_id is None:
            return None
        
        def _get_target_section_operation():
            sections_data = self.structure_model.get_sections(current_sphere_id)
            if sections_data:
                # Модель уже возвращает нормализованные Dict, можно обращаться напрямую
                section_id = sections_data[0]['id']
                self.logger.debug(f"Найден целевой раздел {section_id}")
                return section_id
            return None
        
        return self._execute_with_error_handling(
            _get_target_section_operation,
            "получить целевой раздел",
            default_return=None
        )
