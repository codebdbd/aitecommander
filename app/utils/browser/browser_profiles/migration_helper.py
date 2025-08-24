"""
Помощник для миграции существующих Chrome профилей на универсальную систему.
"""

import logging
from typing import Dict

from .profile_manager import get_profile_manager

logger = logging.getLogger(__name__)


class ProfileMigrationHelper:
    """Помощник для миграции существующих Chrome профилей в новый формат."""

    def __init__(self, database):
        """
        Инициализация помощника миграции.

        Args:
            database: Объект базы данных
        """
        self.database = database
        self.profile_manager = get_profile_manager()
        logger.info("Инициализирован помощник миграции профилей")

    def migrate_existing_chrome_links(self) -> int:
        """Мигрирует существующие Chrome ссылки в новый формат."""
        try:
            # Находим все ссылки с Chrome профилями
            chrome_links = self.database.connection.execute("""
                SELECT * FROM links 
                WHERE type = 'web' AND args LIKE '--profile-directory=%'
            """).fetchall()

            migrated_count = 0
            for link in chrome_links:
                try:
                    # Добавляем метаданные о браузере в заметки
                    current_notes = link.get("notes", "") or ""

                    # Проверяем, не добавлены ли уже метаданные
                    if "Browser: Chrome" not in current_notes:
                        new_notes = current_notes
                        if new_notes and not new_notes.endswith("\n"):
                            new_notes += "\n"
                        new_notes += "Browser: Chrome"

                        self.database.connection.execute(
                            """
                            UPDATE links 
                            SET notes = ?
                            WHERE id = ?
                        """,
                            (new_notes, link["id"]),
                        )

                        migrated_count += 1
                        logger.debug(
                            f"Мигрирована ссылка {link['id']}: {link.get('name', 'Без имени')}"
                        )

                except Exception as e:
                    logger.error(f"Ошибка миграции ссылки {link['id']}: {e}")
                    continue

            # Сохраняем изменения
            self.database.connection.commit()

            logger.info(f"Мигрировано {migrated_count} Chrome ссылок")
            return migrated_count

        except Exception as e:
            logger.error(f"Ошибка при миграции Chrome ссылок: {e}")
            return 0

    def detect_browser_from_existing_links(self) -> Dict[str, int]:
        """Анализирует существующие ссылки и определяет используемые браузеры."""
        browsers_stats = {}

        try:
            # Анализируем аргументы командной строки
            links_with_args = self.database.connection.execute("""
                SELECT args FROM links WHERE args IS NOT NULL AND args != ''
            """).fetchall()

            for link in links_with_args:
                args = link.get("args", "")
                if args:
                    browser = self.profile_manager.detect_browser_from_args(args)
                    if browser:
                        browsers_stats[browser] = browsers_stats.get(browser, 0) + 1

            logger.info(
                f"Статистика браузеров в существующих ссылках: {browsers_stats}"
            )

        except Exception as e:
            logger.error(f"Ошибка анализа существующих ссылок: {e}")

        return browsers_stats

    def get_migration_summary(self) -> str:
        """Генерирует сводку по миграции."""
        try:
            existing_browsers = self.detect_browser_from_existing_links()
            available_browsers = self.profile_manager.get_available_browsers()

            summary = ["=== СВОДКА ПО МИГРАЦИИ ПРОФИЛЕЙ ===\n"]

            summary.append(f"Доступно браузеров: {len(available_browsers)}")
            for browser in available_browsers:
                summary.append(
                    f"  • {browser['name']}: {browser['profile_count']} профилей"
                )

            if existing_browsers:
                summary.append("\nСуществующие ссылки браузеров:")
                for browser, count in existing_browsers.items():
                    summary.append(f"  • {browser}: {count} ссылок")

            return "\n".join(summary)

        except Exception as e:
            logger.error(f"Ошибка генерации сводки миграции: {e}")
            return "Ошибка генерации сводки миграции"
