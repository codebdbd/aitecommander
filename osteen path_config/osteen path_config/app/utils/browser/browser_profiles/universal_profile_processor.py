"""
Универсальный процессор для обработки профилей любых браузеров.
"""

import logging
from typing import Dict, List, Optional

from app.utils.links.link_factory import make_profile_link_record
from app.utils.validators import (
    extract_base_name_from_profile_name,
    validate_chrome_profile_name,
)

from .profile_manager import get_profile_manager
from .utils import get_browser_display_name

logger = logging.getLogger(__name__)


class UniversalProfileProcessor:
    """Универсальный процессор для обработки профилей любых браузеров."""
    
    def __init__(self, database):
        """
        Инициализация процессора.
        
        Args:
            database: Объект базы данных для работы с ссылками
        """
        self.database = database
        self.profile_manager = get_profile_manager()
        logger.info("Инициализирован универсальный процессор профилей")
    
    def process_profile_links(self, name: str, url: str, link_type: str,
                            icon_name: str, notes: str, category_id: int,
                            browser_key: str, selected_profiles: List[Dict],
                            existing_link: Dict = None, user_args: str = None,
                            existing_links_in_category: List[Dict] = None) -> List[Dict]:
        """
        Обрабатывает профили браузера и создает соответствующие ссылки.
        
        Args:
            name: Базовое имя ссылки
            url: URL ссылки
            link_type: Тип ссылки
            icon_name: Имя иконки
            notes: Заметки
            category_id: ID категории
            browser_key: Ключ браузера
            selected_profiles: Список выбранных профилей
            existing_link: Существующая ссылка (при редактировании)
            user_args: Пользовательские аргументы (если заданы вручную)
            existing_links_in_category: Существующие ссылки в категории (для проверки дубликатов)
            
        Returns:
            List[Dict]: Список созданных записей ссылок
        """
        # Логируем сразу при входе в метод
        logger.debug(f"ENTER process_profile_links: browser_key={browser_key}, selected_profiles_count={len(selected_profiles)}")
        # Логируем входные параметры для отладки
        logger.debug(f"process_profile_links called with: name='{name}', url='{url}', link_type='{link_type}', "
                   f"browser_key='{browser_key}', selected_profiles_count={len(selected_profiles)}, "
                   f"existing_link={'present' if existing_link else 'None'}, user_args={'present' if user_args else 'None'}")
        
        logger.debug(f"process_profile_links: name={name}, browser_key={browser_key}, selected_profiles count={len(selected_profiles)}")
        
        if not selected_profiles:
            logger.warning("Не выбрано ни одного профиля")
            return []
        
        finder = self.profile_manager.finders.get(browser_key)
        if not finder:
            logger.error(f"Неизвестный браузер: {browser_key}")
            return []
        
        logger.info(f"Обработка {len(selected_profiles)} профилей {get_browser_display_name(finder, browser_key)}")
        logger.debug(f"Selected profiles: {selected_profiles}")
        
        # Извлекаем базовое имя
        base_name = extract_base_name_from_profile_name(name)
        
        # Получаем существующие ссылки в категории
        if existing_links_in_category is not None:
            existing_links = [dict(link) for link in existing_links_in_category]
        else:
            existing_links = [dict(link) for link in self.database.links.get_links(category_id)]
        # Предварительно строим хэш-ключи для ускоренной проверки дубликатов
        # Ключ: (url, type, args)
        try:
            existing_keys = {
                (
                    link_item.get('url'),
                    link_item.get('type'),
                    (
                        link_item.get('args')
                        if (hasattr(link_item, 'get') and link_item.get('args') is not None)
                        else link_item.get('args') if isinstance(link_item, dict) else ''
                    ),
                )
                for link_item in existing_links
            }
        except Exception:
            existing_keys = set()
        
        result_links = []
        is_edit = existing_link is not None
        
        for profile in selected_profiles:
            try:
                logger.debug(f"Processing profile: {profile}")
                
                # Форматируем имя профиля
                prof_name = self._format_profile_name(finder, profile)
                logger.debug(f"Formatted profile name: {prof_name}")
                
                # Определяем аргументы: пользовательские или автогенерированные
                if user_args is not None:
                    # Используем пользовательские аргументы
                    prof_args = user_args
                    logger.debug(f"Using user-provided args: '{prof_args}'")
                else:
                    # Генерируем аргументы через finder
                    prof_args = finder.get_profile_argument(profile)
                    logger.debug(f"Using auto-generated args: '{prof_args}'")
                
                # Проверяем, что аргументы не пустые
                if not prof_args:
                    logger.info(f"Пропускаем профиль '{prof_name}' — пустые аргументы (browser={browser_key})")
                    continue
                
                # Определяем, является ли это текущим редактируемым профилем
                existing_args = existing_link.get("args", "") if existing_link else ""
                existing_id = existing_link.get("id") if existing_link else None
                is_current = (is_edit and prof_args == existing_args)
                
                # Для профилей другого браузера при редактировании проверяем по ID
                if is_edit and not is_current and existing_id:
                    # Проверяем, есть ли уже ссылка с таким ID в результатах
                    # Это нужно для корректной обработки смешанных профилей
                    is_current = any(link.get("id") == existing_id for link in result_links)
                
                logger.debug(f"Profile check: prof_args='{prof_args}', existing_args='{existing_args}', "
                           f"is_edit={is_edit}, is_current={is_current}")
                
                # Генерируем имя ссылки
                link_name = self._generate_link_name(
                    base_name, prof_name, 
                    len(selected_profiles) == 1, 
                    is_current, name
                )
                
                logger.debug(f"Generated link_name='{link_name}' for profile '{prof_name}'")
                
                # Проверяем на дубликаты
                
                # При редактировании смешанных профилей не проверяем на дубликаты профили другого браузера
                skip_duplicate_check = False
                if is_edit and not is_current and existing_link:
                    # Это профиль другого браузера при редактировании - пропускаем проверку дубликатов
                    skip_duplicate_check = True
                    logger.debug(f"Пропускаем проверку дубликатов для профиля другого браузера: {prof_name}")
                
                logger.debug(f"Проверка дубликатов для {link_name}: skip={skip_duplicate_check}, url={url}, type={link_type}, args={prof_args}")
                if skip_duplicate_check:
                    duplicate_check_result = False
                elif is_current:
                    # Текущая редактируемая запись не считается дубликатом самой себя
                    duplicate_check_result = False
                else:
                    duplicate_check_result = (url, link_type, prof_args) in existing_keys
                logger.debug(f"Результат проверки дубликатов: {duplicate_check_result}")
                
                if not skip_duplicate_check and duplicate_check_result:
                    logger.info(f"Пропускаем дубликат: name='{link_name}', args='{prof_args}' (browser={browser_key})")
                    continue
                
                # Создаем запись ссылки
                link_record = make_profile_link_record(
                    link_name=link_name,
                    url=url,
                    link_type=link_type,
                    icon_name=icon_name,
                    prof_args=prof_args,
                    notes=notes,
                    category_id=category_id,
                    last_used=existing_link.get("last_used") if existing_link else None,
                    position=existing_link.get("position", 0) if existing_link else 0,
                    link_id=existing_link.get("id") if is_current else None,
                    browser_key=browser_key  # Добавляем browser_key для правильного запуска
                )
                
                result_links.append(link_record)
                logger.debug(f"Создана ссылка: {link_name} с аргументами {prof_args}")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке профиля {profile}: {e}")
                continue
        
        logger.info(f"Создано {len(result_links)} ссылок для {get_browser_display_name(finder, browser_key)}")
        return result_links
    
    def _format_profile_name(self, finder, profile: Dict) -> str:
        """Форматирует имя профиля для отображения."""
        if hasattr(finder, 'format_profile_display_name'):
            return finder.format_profile_display_name(profile)
        
        # Fallback для совместимости
        profile_name = (
            profile.get("email")
            or profile.get("name")
            or getattr(finder, 'get_browser_name', lambda: 'Browser')()
        )
        return validate_chrome_profile_name(profile_name)
    
    def _generate_link_name(self, base_name: str, profile_name: str, 
                          is_single_profile: bool, is_current_profile: bool, 
                          original_name: str) -> str:
        """Генерирует имя ссылки для профиля."""
        logger.debug(f"_generate_link_name: base_name='{base_name}', profile_name='{profile_name}', "
                    f"is_single_profile={is_single_profile}, is_current_profile={is_current_profile}, "
                    f"original_name='{original_name}'")
        
        # При редактировании текущего профиля всегда сохраняем пользовательское имя
        if is_current_profile:
            logger.debug(f"_generate_link_name: returning original_name='{original_name}' (current profile)")
            return original_name
        
        # Для новых ссылок используем стандартную логику генерации имени
        if profile_name == "Chrome" or profile_name == "Firefox":
            logger.debug(f"_generate_link_name: returning base_name='{base_name}' (default browser)")
            return base_name
        
        generated_name = f"{base_name} ({profile_name})"
        logger.debug(f"_generate_link_name: returning generated_name='{generated_name}' (new profile)")
        return generated_name
    
    def parse_existing_profile(self, link: Dict) -> tuple[Optional[str], List[Dict]]:
        """
        Парсит существующий профиль из ссылки и определяет браузер.
        
        Args:
            link: Данные ссылки
            
        Returns:
            tuple: (browser_key, [profile_data]) или (None, [])
        """
        logger.debug(f"parse_existing_profile: link={link}")
        
        if not (link.get("id") and 
                link.get("type") == "web" and 
                link.get("args")):
            logger.debug("parse_existing_profile: missing required fields")
            return None, []
        
        args = link.get("args", "")
        logger.debug(f"parse_existing_profile: args={args}")
        
        # Определяем браузер по аргументам
        browser_key = self.profile_manager.detect_browser_from_args(args)
        logger.debug(f"parse_existing_profile: detected browser_key={browser_key}")
        
        if not browser_key:
            logger.debug(f"Не удалось определить браузер по аргументам: {args}")
            return None, []
        
        finder = self.profile_manager.finders[browser_key]
        logger.debug(f"parse_existing_profile: finder={finder}")
        
        parsed_profile = finder.parse_profile_from_args(args)
        logger.debug(f"parse_existing_profile: parsed_profile={parsed_profile}")
        
        if parsed_profile:
            logger.debug(f"Определен профиль {browser_key}: {parsed_profile}")
            return browser_key, [parsed_profile]
        
        logger.debug("parse_existing_profile: could not parse profile")
        return None, []
    
    def validate_profiles(self, browser_key: str, selected_profiles: List[Dict]) -> bool:
        """Валидирует выбранные профили."""
        if not selected_profiles:
            return False
        
        finder = self.profile_manager.finders.get(browser_key)
        if not finder:
            return False
        
        # Проверяем, что все профили имеют необходимые поля
        for profile in selected_profiles:
            if not isinstance(profile, dict):
                return False
            if not finder.validate_profile_data(profile):
                return False
        
        return True
