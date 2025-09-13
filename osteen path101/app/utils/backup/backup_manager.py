import datetime
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    deleted_count: int
    errors: List[Tuple[Path, Exception]]


def _timestamp() -> str:
    now = datetime.datetime.now()
    return now.strftime("%Y%m%d_%H%M%S_%f")


def create_backup(src_db_path: Path, backups_dir: Path) -> Path:
    """Create a consistent SQLite backup copy of src_db_path into backups_dir.

    Returns the destination Path of the created backup file.
    """
    backups_dir.mkdir(parents=True, exist_ok=True)
    dst = backups_dir / f"links_{_timestamp()}.db"
    # Use sqlite3 backup API for consistency
    with sqlite3.connect(str(src_db_path)) as src, sqlite3.connect(str(dst)) as dest:
        src.backup(dest)
    logger.info("Создана резервная копия: %s", dst)
    return dst


def apply_retention(
    backups_dir: Path,
    max_backups: int,
    keep: Set[Path],
    *,
    attempts: int = 30,
    sleep_sec: float = 0.05,
    settle_sec: float | None = None,
) -> RetentionResult:
    """Ensure the number of backup files does not exceed max_backups.

    - Does not delete any files listed in `keep`.
    - Tries multiple attempts with small sleeps to mitigate transient locks (Windows).
    - Returns a RetentionResult with counters and errors.
    """
    errors: List[Tuple[Path, Exception]] = []
    deleted_count = 0

    # Отсортируем по имени, чтобы не зависеть от сравнения объектов Path-подобных
    files = sorted(backups_dir.glob("links_*.db"), key=lambda p: getattr(p, "name", str(p)))
    if max_backups < 0:
        max_backups = 0
    if len(files) <= max_backups:
        return RetentionResult(deleted_count=0, errors=errors)

    # Candidates sorted oldest first, excluding keep set
    keep_resolved = {p.resolve() for p in (keep or set())}
    candidates = [f for f in files if f.resolve() not in keep_resolved]

    target_deletions = max(0, len(files) - max_backups)
    if target_deletions == 0 or not candidates:
        return RetentionResult(deleted_count=0, errors=errors)

    # Small settle delay before aggressive deletion attempts
    # Give a short settle time before deletions (Windows AV/indexer may grab handles briefly)
    if settle_sec is None:
        base_settle = max(sleep_sec, 0.5)
    else:
        base_settle = max(0.0, max(sleep_sec, settle_sec))
    if base_settle > 0.0:
        time.sleep(base_settle)

    # Try multiple passes to bypass transient locks, re-sorting by mtime each pass
    for attempt in range(attempts):
        if deleted_count >= target_deletions:
            break
        # Refresh candidate set and prepare two orders: oldest-first and newest-first
        snapshot = [f for f in candidates if f.exists()]
        try:
            snapshot.sort(key=lambda p: p.stat().st_mtime)
        except Exception:
            # Fallback to name order if stat fails sporadically
            snapshot.sort(key=lambda p: p.name)
        if not snapshot:
            break

        orders = [snapshot, list(reversed(snapshot))]
        for order in orders:
            for old_file in list(order):
                if deleted_count >= target_deletions:
                    break
                try:
                    old_file.unlink()
                    deleted_count += 1
                    # Remove from candidates to avoid retrying
                    if old_file in candidates:
                        candidates.remove(old_file)
                    # Also remove from both orders
                    try:
                        order.remove(old_file)
                    except Exception:
                        pass
                except Exception as del_err:
                    logger.warning(
                        "Не удалось удалить старую резервную копию %s: %s",
                        old_file,
                        del_err,
                        exc_info=False,
                    )
                    # Fallback: try to quarantine by renaming so it no longer matches retention glob
                    try:
                        quarantine_path = old_file.with_name(old_file.name + ".locked")
                        old_file.rename(quarantine_path)
                        logger.info(
                            "Отложенное удаление: файл перемещен в карантин %s",
                            quarantine_path,
                        )
                        deleted_count += 1
                        if old_file in candidates:
                            candidates.remove(old_file)
                        try:
                            order.remove(old_file)
                        except Exception:
                            pass
                    except Exception:
                        # Could not quarantine; record error and try later
                        errors.append((old_file, del_err))
            if deleted_count >= target_deletions:
                break
        if attempt < attempts - 1 and deleted_count < target_deletions:
            # Exponential backoff to give the OS time to release handles (cap at ~1.5s)
            delay = sleep_sec * (2 ** attempt)
            if delay > 1.5:
                delay = 1.5
            time.sleep(delay)

    # Final diagnostic if still above limit
    try:
        final_files = list(backups_dir.glob("links_*.db"))
        if len(final_files) > max_backups:
            logger.info(
                "Retention could not reach limit: have=%d, limit=%d, deleted=%d, errors=%d",
                len(final_files),
                max_backups,
                deleted_count,
                len(errors),
            )
    except Exception:
        pass

    return RetentionResult(deleted_count=deleted_count, errors=errors)
