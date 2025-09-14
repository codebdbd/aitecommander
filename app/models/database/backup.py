"""
backup.py — создание резервной копии базы и ротация старых копий.

Организационный перенос из app/models/db.py без изменения логики поведения.
"""
from __future__ import annotations

import datetime
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def perform_backup(db_path: str, backups_dir: Path, max_backups: int) -> Path:
    """Создаёт резервную копию БД в backups_dir и удаляет старые копии при превышении лимита.

    Возвращает путь к созданному файлу бэкапа.
    """
    try:
        # 1) Создаём новый бэкап (гарантированно уникальное имя)
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
        base_name = f"links_{timestamp}"
        # Снимок уже существующих файлов — предотвращает перезапись
        existing = {p.name for p in backups_dir.glob("links_*.db")}
        candidate = f"{base_name}.db"
        if candidate in existing:
            suffix = 1
            while True:
                alt_name = f"{base_name}_{suffix:02d}.db"
                if alt_name not in existing:
                    candidate = alt_name
                    break
                suffix += 1
        dst = backups_dir / candidate
        # Дополнительная страховка от коллизий/гонок: гарантируем несуществующий путь
        if dst.exists():
            suffix = 1
            while True:
                alt = backups_dir / f"{base_name}_{suffix:02d}.db"
                if not alt.exists():
                    dst = alt
                    break
                suffix += 1

        with sqlite3.connect(db_path) as src, sqlite3.connect(dst) as dest:
            src.backup(dest)
        logger.info("Создана резервная копия: %s", dst)

        # 2) Очистка сверх лимита
        files = sorted(backups_dir.glob("links_*.db"))
        if len(files) > max_backups:
            candidates = [f for f in files if f != dst]
            deleted_count = 0
            target_deletions = len(files) - max_backups
            max_attempts = 3
            for attempt in range(max_attempts):
                files_to_try = [f for f in candidates if f.exists()]
                if not files_to_try or deleted_count >= target_deletions:
                    break
                for old_file in files_to_try:
                    if deleted_count >= target_deletions:
                        break
                    try:
                        old_file.unlink()
                        deleted_count += 1
                        if old_file in candidates:
                            candidates.remove(old_file)
                    except Exception as del_err:
                        logger.warning(
                            "Не удалось удалить старую резервную копию %s: %s",
                            old_file,
                            del_err,
                            exc_info=False,
                        )
                if attempt < max_attempts - 1 and deleted_count < target_deletions:
                    time.sleep(0.1)
        return dst
    except Exception as e:
        logger.error("Ошибка создания резервной копии: %s", e, exc_info=True)
        raise
