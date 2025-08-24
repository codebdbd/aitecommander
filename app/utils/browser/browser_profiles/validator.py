"""
Валидатор для проверки корректности профилей браузеров.
"""

import logging
from typing import Dict, List

from .profile_manager import get_profile_manager
from .utils import get_browser_display_name

logger = logging.getLogger(__name__)


class BrowserProfileValidator:
    """Валидатор для проверки корректности профилей браузеров."""

    def __init__(self):
        """Инициализация валидатора."""
        self.profile_manager = get_profile_manager()
        logger.info("Инициализирован валидатор профилей браузеров")

    def validate_all_browsers(self) -> Dict[str, Dict]:
        """Проверяет все браузеры и их профили."""
        results = {}

        for browser_key, finder in self.profile_manager.finders.items():
            try:
                profiles = finder.find_profiles()
                results[browser_key] = {
                    "status": "success",
                    "profile_count": len(profiles),
                    "profiles": profiles,
                    "browser_name": get_browser_display_name(finder, browser_key),
                    "validation_details": self._validate_profiles_detailed(
                        finder, profiles
                    ),
                }
                logger.debug(
                    f"Валидация {browser_key}: успешно, {len(profiles)} профилей"
                )
            except Exception as e:
                results[browser_key] = {
                    "status": "error",
                    "error": str(e),
                    "profile_count": 0,
                    "profiles": [],
                    "browser_name": get_browser_display_name(finder, browser_key),
                }
                logger.error(f"Ошибка валидации {browser_key}: {e}")

        return results

    def _validate_profiles_detailed(self, finder, profiles: List[Dict]) -> Dict:
        """Детальная валидация профилей."""
        details = {
            "valid_profiles": 0,
            "invalid_profiles": 0,
            "profiles_with_email": 0,
            "profiles_without_email": 0,
            "argument_test_passed": 0,
            "argument_test_failed": 0,
        }

        for profile in profiles:
            # Проверка базовой валидности
            if finder.validate_profile_data(profile):
                details["valid_profiles"] += 1
            else:
                details["invalid_profiles"] += 1

            # Проверка наличия email
            if profile.get("email"):
                details["profiles_with_email"] += 1
            else:
                details["profiles_without_email"] += 1

            # Тест аргументов
            if self.test_profile_arguments(finder.get_browser_key(), profile):
                details["argument_test_passed"] += 1
            else:
                details["argument_test_failed"] += 1

        return details

    def test_profile_arguments(self, browser_key: str, profile: Dict) -> bool:
        """Тестирует корректность аргументов профиля."""
        finder = self.profile_manager.finders.get(browser_key)
        if not finder:
            return False

        try:
            # Генерируем аргументы
            args = finder.get_profile_argument(profile)

            # Пытаемся их распарсить обратно
            parsed = finder.parse_profile_from_args(args)

            return parsed is not None
        except Exception as e:
            logger.debug(f"Ошибка тестирования аргументов для {browser_key}: {e}")
            return False

    def validate_browser_availability(self) -> Dict[str, bool]:
        """Проверяет доступность браузеров в системе."""
        availability = {}

        for browser_key, finder in self.profile_manager.finders.items():
            try:
                profiles = finder.find_profiles()
                availability[browser_key] = len(profiles) > 0
            except Exception:
                availability[browser_key] = False

        return availability

    def get_validation_summary(self) -> Dict:
        """Получает сводку валидации."""
        validation_results = self.validate_all_browsers()

        summary = {
            "total_browsers": len(validation_results),
            "working_browsers": 0,
            "total_profiles": 0,
            "browsers_with_errors": 0,
            "browser_details": {},
        }

        for browser_key, result in validation_results.items():
            if result["status"] == "success":
                summary["working_browsers"] += 1
                summary["total_profiles"] += result["profile_count"]
            else:
                summary["browsers_with_errors"] += 1

            summary["browser_details"][browser_key] = {
                "name": result["browser_name"],
                "status": result["status"],
                "profile_count": result["profile_count"],
            }

        return summary
