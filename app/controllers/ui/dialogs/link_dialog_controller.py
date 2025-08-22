# app/controllers/link_dialog_controller.py

import logging
from typing import Any, Dict, List, Optional

from app.controllers.business.links_business import LinksBusinessLogic
from app.models.db import Database
from app.utils.browser.browser_profiles import get_profile_manager

logger = logging.getLogger(__name__)


class LinkDialogController:
    """Контроллер для управления бизнес-логикой диалога ссылок."""
    
    def __init__(self, database: Database):
        self.database = database
        self.links_business = LinksBusinessLogic(database)
        self.result_data: List[Dict[str, Any]] = []
        # Единый менеджер профилей через фабрику — исключаем повторные сканы профилей
        self.profile_manager = get_profile_manager()
    
    def get_initialization_data(self, category_id: Optional[int] = None, link: Optional[Dict] = None) -> Dict[str, Any]:
        """Получает данные для инициализации диалога."""
        # Получаем сферы
        spheres = self.database.spheres.get_spheres()
        
        # Определяем иерархию категории
        category_hierarchy = None
        if category_id:
            category_hierarchy = self._get_category_hierarchy(category_id)
        elif link and link.get("category_id"):
            category_hierarchy = self._get_category_hierarchy(link["category_id"])
        
        # Получаем Chrome профили
        chrome_profiles = self._get_chrome_profiles()
        
        # Миграция старых Chrome-профилей в универсальный формат
        if link and link.get("args", "").startswith("--profile-directory"):
            from app.utils.browser.browser_profiles import UniversalProfileProcessor
            processor = UniversalProfileProcessor(self.database)
            browser_key, profiles = processor.parse_existing_profile(link)
            if browser_key and profiles:
                # Добавляем browser_key в каждый профиль для совместимости
                for profile in profiles:
                    profile['browser_key'] = browser_key
                    if 'browser_name' not in profile:
                        from app.utils.browser.browser_profiles.utils import (
                            get_browser_display_name,
                        )
                        finder = self.profile_manager.finders.get(browser_key)
                        if finder:
                            profile['browser_name'] = get_browser_display_name(finder, browser_key)
                link['migrated_profiles'] = profiles
        
        return {
            'spheres': spheres,
            'category_hierarchy': category_hierarchy,
            'chrome_profiles': chrome_profiles,
            'selected_category_id': category_id,
            'form_data': link
        }
    
    def _get_category_hierarchy(self, category_id: int) -> Optional[Dict[str, int]]:
        """Получает иерархию для категории (сфера -> раздел -> категория)."""
        return self.database.categories.get_category_hierarchy(category_id)
    
    def _get_chrome_profiles(self) -> List[Dict[str, Any]]:
        """Получает список Chrome профилей."""
        try:
            return self.profile_manager.get_browser_profiles('chrome')
        except Exception:
            return []
    
    def get_sections_for_sphere(self, sphere_id: int) -> List[Dict[str, Any]]:
        """Получает разделы для сферы."""
        return self.database.sections.get_sections(sphere_id)
    
    def get_categories_for_section(self, section_id: int) -> List[Dict[str, Any]]:
        """Получает категории для раздела."""
        return self.database.categories.get_categories(section_id)
    
    def validate_and_save(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидирует данные формы и подготавливает для сохранения."""
        # Базовая валидация
        validation_result = self._validate_form_data(form_data)
        if not validation_result['is_valid']:
            return validation_result
        
        # Подготавливаем данные для сохранения
        self.result_data = self._prepare_links_data(form_data)
        
        return {'is_valid': True, 'errors': []}
    
    def _validate_form_data(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Валидирует данные формы."""
        errors = []
        
        # Проверяем обязательные поля
        if not form_data.get('name', '').strip():
            errors.append("Имя ссылки не может быть пустым.")
        
        if not form_data.get('url', '').strip():
            errors.append("URL/Путь не может быть пустым.")
        
        if not form_data.get('link_type'):
            errors.append("Выберите тип ссылки.")
        
        if not form_data.get('category_id'):
            errors.append("Выберите категорию.")
        
        # Проверяем файловые пути
        link_type = form_data.get('link_type')
        url = form_data.get('url', '').strip()
        if link_type in ('file', 'folder') and url:
            import os
            if not os.path.exists(url):
                errors.append("Указанный путь не существует.")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors
        }
    
    def _prepare_links_data(self, form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготавливает данные ссылок для сохранения."""
        links_data = []
        
        # Обработка Chrome профилей
        if (form_data.get('link_type') == 'web' and 
            form_data.get('selected_profiles')):
            links_data.extend(self._prepare_profile_links(form_data))
        else:
            # Обычная ссылка
            links_data.append(self._prepare_regular_link(form_data))
        
        return links_data
    
    def _prepare_profile_links(self, form_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Подготавливает ссылки с профилями любых браузеров."""
        from app.utils.browser.browser_profiles import (
            UniversalProfileProcessor,
        )
        
        processor = UniversalProfileProcessor(self.database)
        is_edit = form_data.get('link_id') is not None
        existing_link = None
        if is_edit:
            # Передаем все необходимые поля для правильного сравнения профилей
            existing_link = {
                'id': form_data['link_id'],
                'args': form_data.get('args', ''),  # Ключевое поле для сравнения профилей
                'last_used': form_data.get('last_used'),
                'position': form_data.get('position', 0)
            }
        
        # Обрабатываем выбранные профили
        selected_profiles = form_data['selected_profiles']
        if not selected_profiles:
            return []
        
        # Разделяем профили по браузерам (используем единый менеджер на контроллер)
        manager = self.profile_manager
        profiles_by_browser = {}
        
        for profile in selected_profiles:
            # Определяем browser_key для каждого профиля
            browser_key = profile.get('browser_key')
            if not browser_key:
                # Fallback 1: попытка по args
                browser_key = manager.detect_browser_from_args(profile.get('args', ''))
                if not browser_key:
                    # Fallback 2: перебираем finders и валидируем профиль
                    for key, finder in manager.finders.items():
                        try:
                            if hasattr(finder, 'validate_profile_data') and finder.validate_profile_data(profile):
                                browser_key = key
                                break
                        except Exception:
                            continue
                if not browser_key:
                    logger.debug(f"_prepare_profile_links: пропущен профиль без определённого браузера: {profile}")
                    continue  # Пропускаем профиль, если не можем определить браузер
            
            # Группируем профили по browser_key
            if browser_key not in profiles_by_browser:
                profiles_by_browser[browser_key] = []
            profiles_by_browser[browser_key].append(profile)
            
        # Логируем информацию о профилях для отладки
        try:
            summary = {bk: len(ps) for bk, ps in profiles_by_browser.items()}
            logger.info(f"_prepare_profile_links: сгруппировано профилей по браузерам: {summary}")
        except Exception:
            logger.debug(f"Profiles by browser: {profiles_by_browser}")
        for browser_key, profiles in profiles_by_browser.items():
            logger.debug(f"Browser {browser_key}: {len(profiles)} profiles")
            for i, profile in enumerate(profiles):
                logger.debug(f"  Profile {i}: {profile.get('name', 'Unknown')} - args: {profile.get('args', 'None')} - directory: {profile.get('directory', 'None')}")
        
        if not profiles_by_browser:
            return []
        
        # Обрабатываем профили для каждого браузера отдельно
        result_links = []
        
        # Для редактирования определяем текущий browser_key из существующей ссылки
        current_browser_key = None
        if existing_link and existing_link.get('args'):
            current_browser_key = manager.detect_browser_from_args(existing_link.get('args', ''))
        
        # Определяем, изменил ли пользователь аргументы вручную (для первого браузера)
        first_browser_key = next(iter(profiles_by_browser))
        first_profiles = profiles_by_browser[first_browser_key]
        user_args = self._get_user_args_if_modified(form_data, existing_link, first_profiles, first_browser_key)
        
        # Получаем все существующие ссылки в категории для проверки дубликатов
        existing_links_in_category = []
        if form_data.get('category_id'):
            existing_links_in_category = list(self.database.links.get_links(form_data['category_id']))
        
        # Обрабатываем профили для каждого браузера
        for browser_key, profiles in profiles_by_browser.items():
            # Для каждого браузера создаем отдельные ссылки
            browser_links = processor.process_profile_links(
                name=form_data['name'],
                url=form_data['url'],
                link_type=form_data['link_type'],
                icon_name=form_data.get('icon_name', ''),
                notes=form_data.get('notes', ''),
                category_id=form_data['category_id'],
                browser_key=browser_key,
                selected_profiles=profiles,
                existing_link=existing_link if browser_key == current_browser_key else None,
                user_args=user_args if browser_key == first_browser_key else None,
                existing_links_in_category=existing_links_in_category
            )
            result_links.extend(browser_links)
            logger.info(f"_prepare_profile_links: для браузера {browser_key} создано ссылок: {len(browser_links)}")
        
        logger.info(f"_prepare_profile_links: всего создано ссылок: {len(result_links)}")
        return result_links
    
    def _get_user_args_if_modified(self, form_data: Dict[str, Any], existing_link: Dict, 
                                   selected_profiles: List[Dict], browser_key: str) -> Optional[str]:
        """
        Определяет, изменил ли пользователь аргументы вручную.
        
        Args:
            form_data: Данные формы
            existing_link: Существующая ссылка (для редактирования)
            selected_profiles: Выбранные профили
            browser_key: Ключ браузера
            
        Returns:
            str: Пользовательские аргументы, если они отличаются от автогенерированных
            None: Если аргументы не изменены или это новая ссылка
        """
        current_args = form_data.get('args', '').strip()
        
        # Для новых ссылок: если пользователь ввел аргументы, используем их
        if not existing_link:
            return current_args if current_args else None
        
        # Для редактирования: сравниваем с автогенерированными аргументами
        try:
            manager = self.profile_manager
            finder = manager.finders.get(browser_key)
            
            if not finder or not selected_profiles:
                return current_args if current_args else None
            
            # Генерируем ожидаемые аргументы для первого выбранного профиля
            first_profile = selected_profiles[0]
            expected_args = finder.get_profile_argument(first_profile)
            
            # Сравниваем текущие аргументы с ожидаемыми
            if current_args != expected_args:
                # ВАЖНО: считаем, что пользователь переопределил аргументы
                # только если они НЕ пустые. Пустые не должны глушить автогенерацию.
                return current_args if current_args else None
            
            return None
            
        except Exception:
            # В случае ошибки возвращаем пользовательские аргументы, если они есть
            return current_args if current_args else None
    
    def _prepare_regular_link(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Подготавливает обычную ссылку."""
        from app.utils.links.link_factory import make_link_record
        
        return make_link_record(
            name=form_data['name'],
            url=form_data['url'],
            link_type=form_data['link_type'],
            icon_name=form_data.get('icon_name', ''),
            notes=form_data.get('notes', ''),
            last_used=form_data.get('last_used'),
            position=form_data.get('position', 0),
            category_id=form_data['category_id'],
            args=form_data.get('args', ''),
            is_favorite=int(form_data.get('is_favorite', False)),
            link_id=form_data.get('link_id')
        )
    
    def get_result_data(self) -> List[Dict[str, Any]]:
        """Возвращает результирующие данные после сохранения."""
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"get_result_data: returning {len(self.result_data) if self.result_data else 0} links")
        if self.result_data:
            for i, link in enumerate(self.result_data):
                logger.debug(f"get_result_data: link {i}: name={link.get('name')}, browser_key={link.get('browser_key')}")
        return self.result_data
