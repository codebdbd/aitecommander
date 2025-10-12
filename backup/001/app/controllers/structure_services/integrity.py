from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

# Модульный логгер для диагностических сообщений
logger = logging.getLogger(__name__)


class IntegrityService:
    """Сервис проверки целостности и статистики структуры."""

    def get_statistics(
        self,
        get_spheres: Callable[[], List[Dict[str, Any]]],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        current_sphere_id: Optional[int],
        logger,
    ) -> Dict[str, Any]:
        try:
            stats: Dict[str, Any] = {
                "spheres_count": 0,
                "sections_count": 0,
                "categories_count": 0,
                "current_sphere_sections": 0,
                "current_sphere_categories": 0,
            }

            spheres = get_spheres() or []
            stats["spheres_count"] = len(spheres)

            # Оптимизация: собираем статистику за один проход
            total_sections = 0
            total_categories = 0
            current_sphere_sections = 0
            current_sphere_categories = 0
            
            # Кэш для секций, чтобы не вызывать get_sections дважды для current_sphere
            sections_cache = {}
            
            for sphere in spheres:
                sphere_id = sphere.get("id")
                if sphere_id is None:
                    continue
                    
                sections = get_sections(sphere_id) or []
                sections_cache[sphere_id] = sections
                total_sections += len(sections)
                
                # Подсчитываем категории для всех секций сферы
                sphere_categories = sum(
                    len(get_categories(section.get("id")) or [])
                    for section in sections
                    if section.get("id") is not None
                )
                total_categories += sphere_categories
                
                # Если это текущая сфера, сохраняем статистику
                if sphere_id == current_sphere_id:
                    current_sphere_sections = len(sections)
                    current_sphere_categories = sphere_categories

            stats["sections_count"] = total_sections
            stats["categories_count"] = total_categories
            stats["current_sphere_sections"] = current_sphere_sections
            stats["current_sphere_categories"] = current_sphere_categories

            return stats
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Ошибка валидации данных при получении статистики: %s", e)
            return {
                "spheres_count": 0,
                "sections_count": 0,
                "categories_count": 0,
                "current_sphere_sections": 0,
                "current_sphere_categories": 0,
            }
        except Exception as e:
            if logger:
                logger.exception("Критическая ошибка получения статистики")
            raise  # Пробрасываем критические ошибки

    def validate_structure_integrity(
        self,
        get_spheres: Callable[[], List[Dict[str, Any]]],
        get_sections: Callable[[int], List[Dict[str, Any]]],
        get_categories: Callable[[int], List[Dict[str, Any]]],
        get_statistics: Callable[[], Dict[str, Any]],
        logger,
    ) -> Dict[str, Any]:
        try:
            integrity_report: Dict[str, Any] = {
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "statistics": {},
            }

            spheres = get_spheres() or []
            
            # Оптимизация: собираем все ошибки за один проход
            errors = []
            
            for sphere in spheres:
                sphere_id = sphere.get("id")
                if sphere_id is None:
                    continue
                    
                sections = get_sections(sphere_id)
                if not sections:
                    continue
                    
                # Проверяем связи секций со сферой
                invalid_sections = [
                    section for section in sections
                    if section.get("sphere_id") != sphere_id
                ]
                
                for section in invalid_sections:
                    errors.append(
                        f"Раздел {section.get('id')} имеет неверную связь со сферой"
                    )
                
                # Проверяем связи категорий с разделами
                for section in sections:
                    section_id = section.get("id")
                    if section_id is None:
                        continue
                        
                    categories = get_categories(section_id)
                    if not categories:
                        continue
                        
                    # Находим категории с неверными связями
                    invalid_categories = [
                        category for category in categories
                        if category.get("section_id") != section_id
                    ]
                    
                    for category in invalid_categories:
                        errors.append(
                            f"Категория {category.get('id')} имеет неверную связь с разделом"
                        )
            
            # Устанавливаем результаты
            integrity_report["errors"] = errors
            integrity_report["is_valid"] = len(errors) == 0
            integrity_report["statistics"] = get_statistics()
            
            return integrity_report
        except (ValueError, KeyError, AttributeError, TypeError) as e:
            if logger:
                logger.error("Ошибка валидации данных при проверке целостности: %s", e)
            return {
                "is_valid": False,
                "errors": [f"Ошибка валидации: {str(e)}"],
                "warnings": [],
                "statistics": {},
            }
        except Exception as e:
            if logger:
                logger.exception("Критическая ошибка проверки целостности структуры")
            raise  # Пробрасываем критические ошибки
