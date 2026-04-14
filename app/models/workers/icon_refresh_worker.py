"""Worker для фонового обновления иконок импортированных ссылок."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, pyqtSignal

from app.config_data import app_config
from app.models.base.db_base import db_lock
from app.models.types.link_type import LinkType
from app.utils.links.parser.fetcher import fetch_web_link_info
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

if TYPE_CHECKING:
    from app.models.database import Database

logger = logging.getLogger(__name__)

_TR_CONTEXT = "IconRefreshWorker"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


class IconRefreshSignals(QObject):
    """Сигналы для IconRefreshWorker."""
    
    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(dict)  # stats: {updated: N, skipped: N, failed: N}
    error = pyqtSignal(str)  # error message
    batch_updated = pyqtSignal(list)  # list[int] - IDs обновлённых ссылок


class IconRefreshWorker(QRunnable):
    """Фоновый воркер для обновления дефолтных иконок веб-ссылок.
    
    После импорта закладок многие ссылки имеют дефолтную иконку.
    Этот воркер проходит по всем веб-ссылкам с дефолтной иконкой
    и пытается скачать реальную иконку сайта.
    """

    def __init__(
        self,
        db: Database,
        batch_size: int = 50,
        delay_ms: int = 100,
        max_workers: int = 5,
    ):
        """
        Args:
            db: Database instance
            batch_size: Количество ссылок для обработки за раз
            delay_ms: Задержка между батчами (мс)
            max_workers: Количество параллельных потоков для загрузки иконок
        """
        super().__init__()
        self.db = db
        self.batch_size = batch_size
        self.delay_ms = delay_ms
        self.max_workers = max_workers
        self.signals = IconRefreshSignals()
        self._is_cancelled = False
        self._cancel_event = threading.Event()
        self._executor = None  # Сохраняем ссылку на executor для принудительной остановки
        self._last_progress_time = 0.0  # Для throttling обновлений прогресса
        self._progress_throttle_ms = 200  # Обновлять прогресс не чаще раза в 200ms

    def cancel(self):
        """Отменить выполнение задачи."""
        self._is_cancelled = True
        self._cancel_event.set()
        self._shutdown_executor(wait=False)
        logger.info("[icon_refresh] Cancellation requested")

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise CancelledError()

    def _get_default_icon_path(self) -> str:
        """Получить путь к дефолтной иконке для веб-ссылок."""
        try:
            return resolve_icon_for_link({"type": "web", "icon_path": ""}) or ""
        except Exception as e:
            logger.debug("Failed to resolve default icon path: %s", e)
            return ""

    def _get_default_web_icon_name(self) -> str:
        """Получить имя дефолтной иконки веб-ссылок из конфигурации."""
        try:
            return (app_config.get_default_icons().get("web") or "web_icon.png").strip()
        except Exception:
            return "web_icon.png"

    def _normalize_path(self, path_value: str) -> str:
        """Нормализовать путь для сравнения (учитывая QRC)."""
        if not path_value:
            return ""
        path_str = str(path_value)
        if path_str.startswith(":/"):
            return path_str.lower()
        try:
            return str(Path(path_str).resolve()).lower()
        except Exception:
            return path_str.lower()

    def _find_links_with_default_icons(self, default_icon_path: str) -> list[dict]:
        """Найти все веб-ссылки с дефолтной иконкой.
        
        Returns:
            Список словарей с полями: id, url, icon_path, category_id
        """
        try:
            default_web_icon = self._get_default_web_icon_name()
            default_web_like = f"%{default_web_icon}" if default_web_icon else "%web_icon.png"
            # Ищем веб-ссылки с дефолтной иконкой или пустой
            # ВАЖНО: Проверяем несколько вариантов дефолтной иконки:
            # - "default.ico" (значение по умолчанию в БД)
            # - Полный путь из resolve_icon_for_link()
            # - Пустая строка или NULL
            query = """
                SELECT id, url, icon_path, category_id, name
                FROM link
                WHERE type = ?
                AND (
                    icon_path = 'default.ico'
                    OR icon_path = ?
                    OR icon_path = ?
                    OR icon_path = ''
                    OR icon_path IS NULL
                    OR icon_path LIKE '%default.ico'
                    OR icon_path LIKE '%web_icon.png'
                    OR icon_path LIKE ?
                    OR icon_path LIKE 'web_%'
                )
                ORDER BY id ASC
            """
            rows = self.db.connection.execute(
                query, (LinkType.WEB.value, default_icon_path, default_web_icon, default_web_like)
            ).fetchall()
            
            logger.debug(
                "[icon_refresh] Found %s web links with default icons (default_icon_path=%s)",
                len(rows),
                default_icon_path,
            )
            
            candidates = []
            for row in rows:
                data = dict(row)
                icon_path = data.get("icon_path") or ""
                if self._is_default_icon(icon_path, default_icon_path):
                    candidates.append(data)
            return candidates
        except Exception as e:
            logger.error("Failed to query links with default icons: %s", e, exc_info=True)
            return []

    def _update_link_icon(self, link_id: int, icon_path: str) -> bool:
        """Обновить иконку ссылки в БД.
        
        Returns:
            True если обновление успешно
        """
        try:
            with db_lock:
                cursor = self.db.connection.execute(
                    "UPDATE link SET icon_path = ? WHERE id = ?",
                    (icon_path, link_id)
                )
            # НЕ делаем commit здесь - будет батчевый commit после обработки батча
            return cursor.rowcount > 0
        except Exception as e:
            logger.error("Failed to update icon for link %s: %s", link_id, e)
            return False

    def _fetch_icon_for_link(self, url: str) -> str | None:
        """Скачать иконку для URL.
        
        Returns:
            Путь к скачанной иконке или None при ошибке
        """
        self._raise_if_cancelled()
        try:
            # Используем defer_icon=False для синхронной загрузки в фоновом потоке
            # force_refresh=True чтобы игнорировать кеш и скачать реальную иконку
            info = fetch_web_link_info(
                url,
                app_config,
                force_refresh=True,
                defer_icon=False,
                on_icon_ready=None,
                cancel_event=self._cancel_event,
            )
            
            self._raise_if_cancelled()
            icon_path = info.get("icon")
            if icon_path:
                # Проверяем что это не дефолтная иконка
                default_icon = self._get_default_icon_path()
                if icon_path != default_icon:
                    return icon_path
            
            return None
        except CancelledError:
            raise
        except Exception as e:
            logger.debug("Failed to fetch icon for %s: %s", url, e)
            return None

    def _is_default_icon(self, icon_path: str, default_icon_path: str) -> bool:
        """Проверить, является ли иконка дефолтной.
        
        Логика:
        - Дефолтная: web_icon.png (общая иконка для всех веб-ссылок)
        - Скачанная: web_domain_com.png (уникальная иконка домена)
        
        Args:
            icon_path: Путь к иконке из БД
            default_icon_path: Путь к дефолтной иконке (не используется)
        
        Returns:
            True если иконка дефолтная
        """
        if not icon_path:
            return True

        icon_name = Path(icon_path).name.lower()
        default_name = Path(default_icon_path).name.lower() if default_icon_path else ""
        default_web_name = self._get_default_web_icon_name().lower()

        # Дефолтные значения (включая абсолютные пути)
        if (
            icon_name in ("default.ico", default_web_name)
            or "web_icon" in icon_name
            or "default.ico" in icon_name
            or (default_name and icon_name == default_name)
        ):
            return True

        # Если это web_* - считаем дефолтной, если файл отсутствует или резолвится в дефолт
        if icon_name.startswith("web_"):
            try:
                resolved = resolve_icon_for_link(
                    {"type": "web", "icon_path": icon_path}
                )
            except Exception:
                resolved = ""
            if not resolved:
                return True
            if default_icon_path:
                if self._normalize_path(resolved) == self._normalize_path(
                    default_icon_path
                ):
                    return True
            return False

        # Любая другая иконка считаем кастомной, если она не резолвится в дефолт
        try:
            resolved = resolve_icon_for_link({"type": "web", "icon_path": icon_path})
        except Exception:
            resolved = ""
        if not resolved:
            return True
        if default_icon_path:
            return (
                self._normalize_path(resolved)
                == self._normalize_path(default_icon_path)
            )
        return False
    
    def _process_batch_parallel(
        self, batch: list[dict], default_icon_path: str, stats: dict, total: int
    ) -> None:
        """Обработать батч ссылок параллельно."""
        updates_to_commit: dict[int, str] = {}
        executor = self._ensure_executor()
        future_to_link = self._submit_batch_futures(executor, batch, default_icon_path)

        try:
            for future in as_completed(future_to_link):
                if self._is_cancelled:
                    self._cancel_pending_futures(future_to_link)
                    return

                link = future_to_link[future]
                try:
                    result = future.result()
                    self._accumulate_result(result, updates_to_commit, stats)
                    self._maybe_emit_progress(stats, total)
                except CancelledError:
                    logger.debug("[icon_refresh] Future for link %s cancelled", link.get("id"))
                    stats["skipped"] += 1
                except Exception as e:
                    logger.warning(
                        "[icon_refresh] Exception processing link %s: %s", link.get("id"), e
                    )
                    stats["failed"] += 1

            if updates_to_commit:
                self._commit_updates(updates_to_commit)
        finally:
            if self._is_cancelled:
                for future in future_to_link:
                    future.cancel()

    # --- Helpers to reduce complexity of _process_batch_parallel() ---
    def _ensure_executor(self) -> ThreadPoolExecutor:
        executor = self._executor
        if executor is None:
            executor = ThreadPoolExecutor(max_workers=self.max_workers)
            self._executor = executor
        return executor

    def _submit_batch_futures(
        self, executor: ThreadPoolExecutor, batch: list[dict], default_icon_path: str
    ) -> dict:
        return {
            executor.submit(self._fetch_and_update_link, link, default_icon_path): link
            for link in batch
        }

    def _cancel_pending_futures(self, future_to_link: dict) -> None:
        logger.info("[icon_refresh] Cancelling %s pending tasks", len(future_to_link))
        for pending_future in future_to_link:
            pending_future.cancel()

    def _accumulate_result(self, result, updates_to_commit: dict[int, str], stats: dict) -> None:
        if isinstance(result, tuple) and len(result) == 3:
            status, link_id, icon_path = result
            if status == "updated" and link_id and icon_path:
                updates_to_commit[int(link_id)] = str(icon_path)
                stats["updated"] += 1
            elif status == "skipped":
                stats["skipped"] += 1
            elif status == "failed":
                stats["failed"] += 1
            return
        # Backward compatible result handling
        if result == "updated":
            stats["updated"] += 1
        elif result == "skipped":
            stats["skipped"] += 1
        else:
            stats["failed"] += 1

    def _maybe_emit_progress(self, stats: dict, total: int) -> None:
        current = stats.get("updated", 0) + stats.get("skipped", 0) + stats.get("failed", 0)
        current_time = time.time() * 1000
        if current_time - self._last_progress_time >= self._progress_throttle_ms:
            self.signals.progress.emit(
                current,
                total,
                QCoreApplication.translate("IconRefreshWorker", "Processed {0}/{1} (updated: {2})").format(
                    current, total, stats.get("updated", 0)
                ),
            )
            self._last_progress_time = current_time

    def _commit_updates(self, updates_to_commit: dict[int, str]) -> None:
        try:
            update_data = [
                (icon_path, link_id) for link_id, icon_path in updates_to_commit.items()
            ]
            self.db.connection.executemany(
                "UPDATE link SET icon_path = ? WHERE id = ?",
                update_data,
            )
            self.db.connection.commit()
            logger.debug(
                "[icon_refresh] Batch committed (%s updates)", len(updates_to_commit)
            )
            updated_ids = list(updates_to_commit.keys())
            self.signals.batch_updated.emit(updated_ids)
        except Exception as e:
            logger.error("[icon_refresh] Failed to commit batch: %s", e)
            try:
                self.db.connection.rollback()
            except Exception:
                pass

    def _shutdown_executor(self, wait: bool) -> None:
        executor = self._executor
        if executor is None:
            return
        try:
            executor.shutdown(wait=wait, cancel_futures=True)
        except Exception as exc:
            logger.debug("[icon_refresh] Executor shutdown failed: %s", exc)
        finally:
            self._executor = None

    def _fetch_and_update_link(
        self, link: dict, default_icon_path: str
    ) -> tuple[str, int | None, str | None]:
        """Скачать иконку для одной ссылки (без записи в БД).
        
        Args:
            link: Словарь с данными ссылки
            default_icon_path: Путь к дефолтной иконке
        
        Returns:
            Кортеж (status, link_id, icon_path):
            - status: "updated", "skipped" или "failed"
            - link_id: ID ссылки (для batch UPDATE)
            - icon_path: Путь к новой иконке (для batch UPDATE)
        """
        self._raise_if_cancelled()

        link_id = link["id"]
        url = link["url"]
        current_icon = link.get("icon_path", "")
        
        # Пропускаем если уже не дефолтная иконка
        is_default = self._is_default_icon(current_icon, default_icon_path)
        if not is_default:
            logger.debug(
                "[icon_refresh] Skipping link %s (already has custom icon: %s)",
                link_id,
                current_icon,
            )
            return ("skipped", None, None)
        
        # Пытаемся скачать иконку
        try:
            # Log first few attempts
            if link_id <= 5:
                logger.info(
                    "[icon_refresh] Fetching icon for link %s: %s",
                    link_id,
                    url[:60],
                )
            new_icon_path = self._fetch_icon_for_link(url)
            
            if new_icon_path and new_icon_path != default_icon_path:
                logger.info(
                    "[icon_refresh] Downloaded icon for link %s (%s): %s",
                    link_id,
                    url[:50],
                    new_icon_path,
                )
                # Возвращаем данные для batch UPDATE
                return ("updated", link_id, new_icon_path)
            else:
                # Log why skipped for first few
                if link_id <= 5:
                    logger.info(
                        "[icon_refresh] Skipped link %s: fetched=%s (same as default or None)",
                        link_id,
                        new_icon_path if new_icon_path else "None",
                    )
                return ("skipped", None, None)
        except CancelledError:
            logger.debug("[icon_refresh] Link %s cancelled during fetch", link_id)
            raise
        except Exception as e:
            logger.warning(
                "[icon_refresh] Failed to process link %s (%s): %s",
                link_id,
                url[:50],
                e,
            )
            return ("failed", None, None)
    
    def _process_link(self, link: dict, default_icon_path: str, stats: dict) -> None:
        """Обработать одну ссылку.
        
        Args:
            link: Словарь с данными ссылки
            default_icon_path: Путь к дефолтной иконке
            stats: Словарь статистики для обновления
        """
        link_id = link["id"]
        url = link["url"]
        current_icon = link.get("icon_path", "")
        
        # Пропускаем если уже не дефолтная иконка
        if not self._is_default_icon(current_icon, default_icon_path):
            stats["skipped"] += 1
            logger.debug(
                "[icon_refresh] Skipping link %s (already has custom icon: %s)",
                link_id,
                current_icon,
            )
            return
        
        # Пытаемся скачать иконку
        try:
            new_icon_path = self._fetch_icon_for_link(url)
            
            if new_icon_path and new_icon_path != default_icon_path:
                # Обновляем в БД
                if self._update_link_icon(link_id, new_icon_path):
                    stats["updated"] += 1
                    logger.info(
                        "[icon_refresh] Updated icon for link %s (%s): %s",
                        link_id,
                        url[:50],
                        new_icon_path,
                    )
                else:
                    stats["failed"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            logger.warning(
                "[icon_refresh] Failed to process link %s (%s): %s",
                link_id,
                url[:50],
                e,
            )
            stats["failed"] += 1

    def run(self):
        """Основной метод выполнения задачи."""
        try:
            logger.info("[icon_refresh] Starting icon refresh worker")
            
            # Получаем путь к дефолтной иконке
            default_icon_path = self._get_default_icon_path()
            if not default_icon_path:
                logger.warning("[icon_refresh] Could not determine default icon path")
                default_icon_path = ""
            
            # Находим все ссылки с дефолтными иконками
            links = self._find_links_with_default_icons(default_icon_path)
            total = len(links)
            
            if total == 0:
                logger.info("[icon_refresh] No links with default icons found")
                self.signals.finished.emit({
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                    "total": 0,
                })
                return
            
            logger.info("[icon_refresh] Found %s links with default icons", total)
            self.signals.progress.emit(
                0, total, QCoreApplication.translate("IconRefreshWorker", "Found {0} links to refresh").format(total)
            )
            
            # Статистика
            stats = {
                "updated": 0,
                "skipped": 0,
                "failed": 0,
                "total": total,
            }
            
            # Обрабатываем ссылки батчами с параллельной загрузкой
            for i in range(0, total, self.batch_size):
                if self._is_cancelled:
                    logger.info("[icon_refresh] Cancelled by user")
                    # Отправляем finished с текущей статистикой вместо error
                    self.signals.finished.emit(stats)
                    return
                
                batch = links[i:i + self.batch_size]
                batch_num = (i // self.batch_size) + 1
                total_batches = (total + self.batch_size - 1) // self.batch_size
                
                logger.debug(
                    "[icon_refresh] Processing batch %s/%s (%s links) with %s workers",
                    batch_num,
                    total_batches,
                    len(batch),
                    self.max_workers,
                )
                
                # Параллельная обработка батча
                self._process_batch_parallel(batch, default_icon_path, stats, total)
                
                if self._is_cancelled:
                    logger.info("[icon_refresh] Cancelled after batch")
                    # Отправляем finished с текущей статистикой вместо error
                    self.signals.finished.emit(stats)
                    return
                
                # Задержка между батчами для снижения нагрузки
                if i + self.batch_size < total and self.delay_ms > 0:
                    time.sleep(self.delay_ms / 1000.0)
            
            # Завершение
            logger.info(
                "[icon_refresh] Completed: updated=%s, skipped=%s, failed=%s, total=%s",
                stats["updated"],
                stats["skipped"],
                stats["failed"],
                stats["total"],
            )
            
            self.signals.finished.emit(stats)
            
        except Exception as e:
            logger.error("[icon_refresh] Unexpected error: %s", e, exc_info=True)
            self.signals.error.emit(QCoreApplication.translate("IconRefreshWorker", "Error: {0}").format(e))
        finally:
            self._shutdown_executor(wait=not self._is_cancelled)


__all__ = ["IconRefreshWorker", "IconRefreshSignals"]
