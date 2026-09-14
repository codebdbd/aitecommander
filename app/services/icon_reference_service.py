"""Сервис управления жизненным циклом иконок.

Обеспечивает очистку осиротевших иконок (файлов, на которые не ссылается ни одна ссылка в БД).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.db import Database

logger = logging.getLogger(__name__)


class IconReferenceService:
    """Сервис управления жизненным циклом иконок.

    Предоставляет методы для:
    - Поиска осиротевших иконок (файлов без ссылок в БД)
    - Очистки осиротевших иконок
    - Проверки использования иконки
    """

    def __init__(self, db: Database):
        self.db = db

    def _get_user_icons_dir(self) -> Path:
        """Получить папку пользовательских иконок."""
        from app.utils.ui.icon.path_service import icon_path_service
        return icon_path_service.get_user_icons_dir()

    def get_referenced_icons(self) -> set[str]:
        """Получить множество иконок, на которые ссылаются активные сущности (link, category, section, sphere).

        Returns:
            Множество имен файлов иконок и путей, используемых в структуре.
        """
        query = """
            SELECT icon_path FROM link WHERE icon_path IS NOT NULL AND icon_path != ''
            UNION
            SELECT icon_path FROM category WHERE icon_path IS NOT NULL AND icon_path != ''
            UNION
            SELECT icon_path FROM section WHERE icon_path IS NOT NULL AND icon_path != ''
            UNION
            SELECT icon_path FROM sphere WHERE icon_path IS NOT NULL AND icon_path != ''
        """
        rows = self.db.connection.execute(query).fetchall()
        referenced = set()
        for row in rows:
            icon_path = row["icon_path"] if isinstance(row, dict) else row[0]
            if icon_path:
                referenced.add(str(icon_path))
                referenced.add(Path(icon_path).name)
        return referenced

    def is_icon_used(self, icon_path: str) -> bool:
        """Проверить, используется ли иконка хотя бы одной сущностью (link, category, section, sphere).

        Args:
            icon_path: Путь или имя файла иконки.

        Returns:
            True если иконка используется.
        """
        if not icon_path:
            return False
        try:
            filename = Path(icon_path).name
            escaped_filename = (
                filename.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            query = """
                SELECT 1 FROM link WHERE icon_path = ? OR icon_path LIKE ? ESCAPE '\\'
                UNION ALL
                SELECT 1 FROM category WHERE icon_path = ? OR icon_path LIKE ? ESCAPE '\\'
                UNION ALL
                SELECT 1 FROM section WHERE icon_path = ? OR icon_path LIKE ? ESCAPE '\\'
                UNION ALL
                SELECT 1 FROM sphere WHERE icon_path = ? OR icon_path LIKE ? ESCAPE '\\'
                LIMIT 1
            """
            like_pattern = f"%{escaped_filename}"
            row = self.db.connection.execute(
                query,
                (
                    icon_path,
                    like_pattern,
                    icon_path,
                    like_pattern,
                    icon_path,
                    like_pattern,
                    icon_path,
                    like_pattern,
                ),
            ).fetchone()
            return row is not None
        except Exception as e:
            logger.error("Failed to check icon usage for %s: %s", icon_path, e)
            return True  # В случае ошибки считаем, что иконка используется (fail-safe)

    def get_orphaned_icons(self) -> list[Path]:
        """Найти осиротевшие иконки (файлы без ссылок в БД).

        Returns:
            Список Path к осиротевшим файлам иконок.
        """
        user_icons_dir = self._get_user_icons_dir()
        if not user_icons_dir.exists():
            return []

        try:
            referenced = self.get_referenced_icons()
        except Exception as e:
            logger.error("Failed to query referenced icons, aborting orphan scan: %s", e)
            return []

        orphans = []
        try:
            for icon_file in user_icons_dir.iterdir():
                if not icon_file.is_file():
                    continue

                # Пропускаем служебные файлы
                if icon_file.name.startswith(".") or icon_file.name.endswith(".db"):
                    continue
                if icon_file.name.endswith(".meta.json"):
                    continue

                # Проверяем, используется ли иконка
                if icon_file.name not in referenced and str(icon_file) not in referenced:
                    orphans.append(icon_file)
        except Exception as e:
            logger.error("Failed to scan user icons directory: %s", e)

        return orphans

    def cleanup_orphaned_icons(
        self,
        dry_run: bool = False,
        min_age_hours: int = 24,
    ) -> dict:
        """Удалить осиротевшие иконки.

        Args:
            dry_run: Если True, только подсчитать, не удаляя файлы.
            min_age_hours: Минимальный возраст файла в часах для удаления.

        Returns:
            Статистика: {deleted: N, kept: N, errors: N}
        """
        orphans = self.get_orphaned_icons()
        stats = {"deleted": 0, "kept": 0, "errors": 0, "total": len(orphans)}

        for icon_path in orphans:
            try:
                # Проверяем возраст файла
                if self._is_recent_file(icon_path, min_age_hours):
                    stats["kept"] += 1
                    continue

                if dry_run:
                    stats["kept"] += 1
                    continue

                icon_path.unlink()
                stats["deleted"] += 1
                logger.info("Deleted orphaned icon: %s", icon_path)
            except Exception as e:
                logger.error("Failed to delete orphaned icon %s: %s", icon_path, e)
                stats["errors"] += 1

        return stats

    def cleanup_icon_if_orphaned(self, icon_path: str) -> bool:
        """Проверить и удалить иконку, если она осиротевшая и находится внутри user_icons_dir.

        Args:
            icon_path: Путь или имя файла иконки.

        Returns:
            True если иконка была удалена, False если осталась или находилась вне user_icons_dir.
        """
        if not icon_path:
            return False

        path_obj = Path(icon_path)
        if ".." in path_obj.parts:
            logger.warning(
                "Unsafe icon path with parent directory traversal: %s", icon_path
            )
            return False

        filename = path_obj.name
        if not filename or filename in (".", ".."):
            return False

        user_icons_dir = self._get_user_icons_dir().resolve()
        target_file = (user_icons_dir / filename).resolve()

        # Strict containment verification: target must reside within user_icons_dir
        try:
            target_file.relative_to(user_icons_dir)
        except ValueError:
            logger.warning("Target icon escapes user icons directory: %s", target_file)
            return False

        if not target_file.is_file():
            return False

        if self.is_icon_used(icon_path) or self.is_icon_used(filename):
            return False

        try:
            target_file.unlink()
            logger.info("Cleaned up orphaned icon: %s", target_file)
            return True
        except Exception as e:
            logger.warning("Failed to cleanup icon %s: %s", target_file, e)
            return False

    def _is_recent_file(self, path: Path, hours: int = 24) -> bool:
        """Проверить, является ли файл свежим (младше указанного возраста).

        Args:
            path: Путь к файлу.
            hours: Возраст в часах.

        Returns:
            True если файл младше указанного возраста.
        """
        try:
            mtime = path.stat().st_mtime
            return (time.time() - mtime) < (hours * 3600)
        except Exception:
            return False  # В случае ошибки считаем файл старым

    def get_stats(self) -> dict:
        """Получить статистику по иконкам.

        Returns:
            Словарь со статистикой.
        """
        user_icons_dir = self._get_user_icons_dir()
        total_files = 0
        total_size = 0

        if user_icons_dir.exists():
            try:
                for icon_file in user_icons_dir.iterdir():
                    if icon_file.is_file():
                        total_files += 1
                        total_size += icon_file.stat().st_size
            except Exception as e:
                logger.error("Failed to get icon stats: %s", e)

        orphans = self.get_orphaned_icons()

        return {
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "orphaned_count": len(orphans),
            "orphaned_size_mb": round(
                sum(o.stat().st_size for o in orphans if o.exists()) / (1024 * 1024),
                2,
            ),
        }


__all__ = ["IconReferenceService"]
