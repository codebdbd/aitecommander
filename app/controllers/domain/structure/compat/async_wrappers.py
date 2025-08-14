from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
import logging


class AsyncWrappers:
    """
    Совместимость: эмуляторы асинхронных методов. 
    Здесь нет реального асинхрона — только делегирование синхронным функциям.
    """

    # Загрузка и выбор
    def load_spheres_async(
        self,
        get_spheres: Callable[[], List[Dict[str, Any]]],
        emit_spheres_loaded: Callable[[List[Dict[str, Any]]], None],
    ) -> None:
        spheres = get_spheres()
        emit_spheres_loaded(spheres)

    def load_structure_async(
        self,
        load_structure: Callable[[Optional[int]], None],
        sphere_id: Optional[int] = None,
    ) -> None:
        load_structure(sphere_id)

    def load_sections_async(
        self,
        get_sections: Callable[[int], List[Dict[str, Any]]],
        sphere_id: int,
    ) -> None:
        _ = get_sections(sphere_id)

    def load_categories_async(
        self,
        get_categories: Callable[[int], List[Dict[str, Any]]],
        section_id: int,
    ) -> None:
        _ = get_categories(section_id)

    # CRUD
    def create_section_async(
        self,
        create_section: Callable[[Dict[str, Any]], bool],
        data: Dict[str, Any],
    ) -> None:
        create_section(data)

    def create_category_async(
        self,
        create_category: Callable[[Dict[str, Any]], bool],
        data: Dict[str, Any],
    ) -> None:
        create_category(data)

    def update_section_async(
        self,
        update_section: Callable[[int, Dict[str, Any]], bool],
        section_id: int,
        data: Dict[str, Any],
    ) -> None:
        update_section(section_id, data)

    def update_category_async(
        self,
        update_category: Callable[[int, Dict[str, Any]], bool],
        category_id: int,
        data: Dict[str, Any],
    ) -> None:
        update_category(category_id, data)

    def delete_section_async(
        self,
        delete_section: Callable[[int], Any],
        section_id: int,
    ) -> None:
        delete_section(section_id)

    def delete_category_async(
        self,
        delete_category: Callable[[int], Any],
        category_id: int,
    ) -> None:
        delete_category(category_id)

    # Прочее
    def count_nested_objects_async(
        self,
        get_categories: Callable[[int], List[Dict[str, Any]]],
        section_id: int,
    ) -> None:
        _ = get_categories(section_id)

    def get_first_category_id_async(
        self,
        get_first_category_id: Callable[[], Optional[int]],
        logger: Optional[logging.Logger] = None,
    ) -> None:
        cid = get_first_category_id()
        if logger:
            logger.debug(f"Получена первая категория асинхронно: {cid}")
