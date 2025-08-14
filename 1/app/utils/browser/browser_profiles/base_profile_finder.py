"""Базовый интерфейс для поиска профилей браузеров."""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class BaseBrowserProfileFinder(ABC):
    """Базовый класс для поиска профилей браузеров."""
    
    @abstractmethod
    def find_profiles(self) -> List[Dict[str, str]]:
        """Находит профили браузера."""
        pass
    
    @abstractmethod
    def get_browser_name(self) -> str:
        """Возвращает читаемое имя браузера."""
        pass
    
    @abstractmethod
    def get_profile_argument(self, profile_data: Dict) -> str:
        """Генерирует аргумент командной строки для профиля."""
        pass
    
    @abstractmethod
    def parse_profile_from_args(self, args: str) -> Optional[Dict]:
        """Парсит профиль из аргументов командной строки."""
        pass
    
    def validate_profile_data(self, profile_data: Dict) -> bool:
        """Валидирует данные профиля."""
        required_keys = ['args']
        return all(key in profile_data for key in required_keys)
    
    def format_profile_display_name(self, profile_data: Dict) -> str:
        """Форматирует имя профиля для отображения в UI."""
        return (profile_data.get('email') or 
                profile_data.get('name') or 
                'Профиль')
    
    def get_browser_key(self) -> str:
        """Возвращает ключ браузера для внутреннего использования."""
        return self.get_browser_name().lower().replace(' ', '_')