# app/controllers/structure_modules/sphere_operations.py

"""Модуль для операций со сферами."""

from typing import Any, Dict, List, Optional

from .base import BaseOperations


class SphereOperations(BaseOperations):
    """Класс для операций со сферами."""
    
    def get_spheres(self) -> List[Dict[str, Any]]:
        """Получает список всех сфер с гарантированной нормализацией."""
        def _load_spheres():
            result = self.structure_model.get_spheres() or []
            self.logger.debug(f"Загружено {len(result)} сфер")
            return result

        return self._exec_with_norm(
            _load_spheres,
            "загрузить список сфер",
            default_return=[]
        )
    
    def get_sphere_by_id(self, sphere_id: int) -> Optional[Dict[str, Any]]:
        """Получает данные сферы по ID с гарантированной нормализацией."""
        # Валидация входных данных
        if not isinstance(sphere_id, int) or sphere_id <= 0:
            self.logger.warning(f"Некорректный ID сферы: {sphere_id}")
            return None
        
        def _get_sphere():
            sphere_data = self.structure_model.get_sphere_by_id(sphere_id)
            if sphere_data:
                self.logger.debug(f"Найдена сфера {sphere_id}")
                return sphere_data
            else:
                self.logger.warning(f"Сфера {sphere_id} не найдена")
                return None
        
        return self._exec_with_norm(
            _get_sphere,
            f"загрузить данные сферы {sphere_id}",
            default_return=None
        )
    
    def get_next_sphere_id(self, current_sphere_id: Optional[int]) -> Optional[int]:
        """Определяет и возвращает ID следующей сферы в списке (циклически).
        
        Args:
            current_sphere_id: ID текущей сферы или None для получения первой сферы
            
        Returns:
            ID следующей сферы или None если недостаточно сфер для переключения
        """
        def _get_next_sphere():
            spheres = self.structure_model.get_spheres()
            if not spheres:
                return None

            # Данные из StructureModel уже представляют собой dict
            MIN_SPHERES_FOR_SWITCHING = 2
            if len(spheres) < MIN_SPHERES_FOR_SWITCHING:
                self.logger.warning("Недостаточно сфер для переключения.")
                return None

            if current_sphere_id is None:
                first_sphere_id = spheres[0]['id']
                self.logger.debug(f"Возвращена первая сфера: {first_sphere_id}")
                return first_sphere_id

            sphere_ids = []
            current_found = False

            for sphere in spheres:
                sphere_id = sphere['id']
                sphere_ids.append(sphere_id)
                if sphere_id == current_sphere_id:
                    current_found = True

            if not current_found:
                self.logger.warning(f"Текущая сфера с ID {current_sphere_id} не найдена в списке.")
                fallback_sphere_id = sphere_ids[0]
                self.logger.debug(f"Возвращена fallback сфера: {fallback_sphere_id}")
                return fallback_sphere_id

            current_index = sphere_ids.index(current_sphere_id)
            next_index = (current_index + 1) % len(sphere_ids)
            next_sphere_id = sphere_ids[next_index]

            self.logger.info(f"Следующая сфера для переключения: {next_sphere_id}")
            return next_sphere_id
        
        return self._exec_with_norm(
            _get_next_sphere,
            "определить следующую сферу",
            default_return=None
        )
    
    def get_target_section_id(self, current_sphere_id: Optional[int]) -> Optional[int]:
        """Получает ID первого доступного раздела в текущей сфере.
        
        Args:
            current_sphere_id: ID сферы для поиска разделов
            
        Returns:
            ID первого раздела или None если раздела нет или сфера не задана
        """
        if current_sphere_id is None:
            self.logger.debug("ID сферы не задан, целевой раздел не может быть определён")
            return None
            
        # Валидация входных данных
        if not isinstance(current_sphere_id, int) or current_sphere_id <= 0:
            self.logger.warning(f"Некорректный ID сферы: {current_sphere_id}")
            return None
        
        def _get_target_section():
            sections_data = self.structure_model.get_sections(current_sphere_id)
            if not sections_data:
                self.logger.debug(f"Разделы в сфере {current_sphere_id} не найдены")
                return None

            # Данные из StructureModel уже dict; берём первый раздел
            section_id = sections_data[0]['id']
            self.logger.debug(f"Найден целевой раздел {section_id} в сфере {current_sphere_id}")
            return section_id
        
        return self._exec_with_norm(
            _get_target_section,
            f"получить целевой раздел в сфере {current_sphere_id}",
            default_return=None
        )
    
    def _validate_sphere_id(self, sphere_id: Any) -> bool:
        """Валидирует корректность ID сферы.
        
        Args:
            sphere_id: Значение для проверки
            
        Returns:
            True если ID корректный, False иначе
        """
        return isinstance(sphere_id, int) and sphere_id > 0