"""Icon downloading and saving utilities.

Выделены чистые функции и класс `IconDownloader`:
- read/write метаданных
- построение условных заголовков
- проверка типа/размера/аспекта изображения
- преобразование SVG
- сохранение файла и обновление метаданных

`save_icon` оставлен как тонкий фасад поверх `IconDownloader`.
"""

from __future__ import annotations

import hashlib
import atexit
import json
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
from io import BytesIO
from typing import TYPE_CHECKING, Optional

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError as RequestsConnectionError
from PIL import Image, UnidentifiedImageError

from app.config_data import app_config
from app.utils.ui.icon.path_service import icon_path_service

if TYPE_CHECKING:
    # For type hints only; avoids runtime dependency and fixes Ruff F821
    from bs4 import BeautifulSoup

from .constants import MIN_GOOD_SIZE, TARGET_SIZE, logger
from .http_client import get_session
from .icon_candidates import find_favicon_candidates
from .svg_convert import convert_svg

_ICON_LOCKS: "OrderedDict[str, threading.Lock]" = OrderedDict()
_ICON_LOCKS_GUARD = threading.Lock()

# Guard for thread-safe temporary changes to PIL global settings
_PIL_MAX_PIXELS_GUARD = threading.Lock()

# Shared executor for icon downloads (singleton)
_ICON_EXECUTOR = None
_ICON_EXECUTOR_GUARD = threading.Lock()

def _shutdown_icon_executor(wait: bool = False):  # pragma: no cover - atexit path
    global _ICON_EXECUTOR
    try:
        ex = _ICON_EXECUTOR
        _ICON_EXECUTOR = None
        if ex is not None:
            try:
                ex.shutdown(wait=wait, cancel_futures=True)
            except TypeError:
                # Python < 3.9 compat: cancel_futures not available
                ex.shutdown(wait=wait)
    except Exception as e:
        logger.debug("icon executor shutdown failed: %s", e)

def _get_icon_executor(max_workers_hint: int) -> ThreadPoolExecutor:
    global _ICON_EXECUTOR
    ex = _ICON_EXECUTOR
    if ex is not None:
        return ex
    with _ICON_EXECUTOR_GUARD:
        if _ICON_EXECUTOR is None:
            try:
                cfg = int(getattr(app_config, "ICON_MAX_WORKERS", 6) or 6)
            except Exception:
                cfg = 6
            max_workers = max(1, int(min(max_workers_hint or 1, cfg)))
            _ICON_EXECUTOR = ThreadPoolExecutor(max_workers=max_workers)
            try:
                atexit.register(lambda: _shutdown_icon_executor(wait=False))
            except Exception as e:  # pragma: no cover - best-effort atexit
                logger.debug("failed to register icon executor shutdown: %s", e)
        return _ICON_EXECUTOR


@contextmanager
def _pil_max_pixels(limit: int):
    """Temporarily set PIL Image.MAX_IMAGE_PIXELS in a thread-safe way.

    Ensures that concurrent calls don't step on each other's toes and that the
    original setting is restored even if exceptions occur.
    """
    _PIL_MAX_PIXELS_GUARD.acquire()
    prev = getattr(Image, "MAX_IMAGE_PIXELS", None)
    try:
        Image.MAX_IMAGE_PIXELS = limit
        yield
    finally:
        try:
            if prev is None:
                try:
                    delattr(Image, "MAX_IMAGE_PIXELS")
                except Exception:
                    pass
            else:
                Image.MAX_IMAGE_PIXELS = prev
        except Exception:
            pass
        _PIL_MAX_PIXELS_GUARD.release()


# === Метаданные и пути ===
def get_icon_meta_path(domain: str) -> str:
    d = (domain or "").replace(".", "_")
    return str(icon_path_service.get_user_icons_dir() / f"web_{d}.meta.json")


def read_icon_meta(domain: str) -> dict:
    try:
        p = get_icon_meta_path(domain)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug("Icon meta read failed for %s: %s", domain, e, exc_info=True)
    return {}


def write_icon_meta(domain: str, meta: dict) -> None:
    try:
        p = get_icon_meta_path(domain)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("Icon meta write failed for %s: %s", domain, e, exc_info=True)


def build_conditional_headers(domain: str, meta: dict, force_refresh: bool) -> dict:
    return {
        "If-None-Match": None if force_refresh else meta.get("etag"),
        "If-Modified-Since": None if force_refresh else meta.get("last_modified"),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": f"https://{domain}/",
    }


def _get_icon_lock(domain: str) -> threading.Lock:
    d = domain or ""
    with _ICON_LOCKS_GUARD:
        lock = _ICON_LOCKS.get(d)
        if lock is None:
            lock = threading.Lock()
            _ICON_LOCKS[d] = lock
        # Помечаем как недавно использованный
        try:
            _ICON_LOCKS.move_to_end(d)
        except Exception:
            pass

        # LRU-очистка при превышении лимита
        try:
            max_locks = int(getattr(app_config, "ICON_LOCKS_MAX", 1024) or 1024)
        except Exception:
            max_locks = 1024
        if len(_ICON_LOCKS) > max_locks:
            # Пытаемся удалить самый старый незахваченный замок
            keys_to_check = list(_ICON_LOCKS.keys())
            for k in keys_to_check:
                if len(_ICON_LOCKS) <= max_locks:
                    break
                if k == d:
                    # не трогаем только что использованный ключ
                    continue
                lock_var = _ICON_LOCKS.get(k)
                if lock_var is None:
                    continue
                if not lock_var.locked():
                    try:
                        _ICON_LOCKS.pop(k, None)
                    except Exception:
                        pass
            # Если все были захвачены, размер временно может оставаться > max_locks
        return lock


class IconDownloader:
    """Логика скачивания/валидации/сохранения иконок, разбитая на шаги."""

    def __init__(self, config):
        self.config = config
        # Поддержка тестового клиента
        self.http_get = getattr(config, "HTTP_GET", None) or (
            lambda u, headers, timeout: requests.get(
                u, headers=headers, timeout=timeout
            )
        )

    # === Валидация и декодирование ===
    @staticmethod
    def is_non_image_data(ct: str, data: bytes) -> bool:
        if (
            ct.startswith("text/")
            or "html" in ct
            or ct in {"application/json", "application/xml"}
        ):
            head = data[:256].lstrip()
            return (
                head.startswith(b"<!DOCTYPE")
                or head.startswith(b"<html")
                or (b"<html" in head.lower())
            )
        return False

    @staticmethod
    def maybe_convert_svg(
        icon_url: str, ct: str, ext: str, data: bytes
    ) -> Optional[bytes]:
        if "image/svg" in ct or ext == "svg" or b"<svg" in data[:200].lower():
            logger.debug("SVG detected %s", icon_url)
            try:
                target = int(
                    getattr(app_config, "ICON_TARGET_SIZE", TARGET_SIZE) or TARGET_SIZE
                )
            except Exception:
                target = TARGET_SIZE
            return convert_svg(data, target_size=target)
        return data

    @staticmethod
    def select_best_frame(img: Image.Image) -> Image.Image:
        try:
            n_frames = int(getattr(img, "n_frames", 1) or 1)
        except Exception:
            n_frames = 1
        best_img = img
        best_score = None
        if (getattr(img, "format", "").upper() == "ICO") or n_frames > 1:
            try:
                for i in range(max(1, n_frames)):
                    try:
                        img.seek(i)
                    except Exception:
                        if i == 0:
                            pass
                        else:
                            break
                    w, h = img.size
                    score = (-max(w, h),)
                    if (best_score is None) or (score < best_score):
                        best_score = score
                        best_img = img.copy()
            except Exception:
                best_img = img
        return best_img

    @staticmethod
    def validate_image_geometry(img: Image.Image, icon_url: str) -> bool:
        width, height = img.size
        if width < MIN_GOOD_SIZE or height < MIN_GOOD_SIZE:
            logger.info(
                "[icon] skip reason=too_small size=%sx%s url=%s",
                width,
                height,
                icon_url,
            )
            return False
        aspect_ratio = max(width, height) / max(1, min(width, height))
        if aspect_ratio > 2.0:
            logger.info(
                "[icon] skip reason=bad_aspect size=%sx%s ratio=%.2f url=%s",
                width,
                height,
                aspect_ratio,
                icon_url,
            )
            return False
        return True

    @staticmethod
    def save_png_with_meta(
        domain: str,
        icon_url: str,
        response_headers: dict,
        img: Image.Image,
        data: bytes,
        is_fallback: bool,
        meta: Optional[dict] = None,
    ) -> Optional[str]:
        path = os.path.join(
            str(icon_path_service.get_user_icons_dir()),
            f"web_{domain.replace('.', '_')}.png",
        )
        width, height = img.size
        lock = _get_icon_lock(domain)
        with lock:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(path, format="PNG")
            try:
                prev_meta = meta or {}
                meta_update = {
                    "etag": response_headers.get("ETag") or prev_meta.get("etag"),
                    "last_modified": response_headers.get("Last-Modified")
                    or prev_meta.get("last_modified"),
                    "saved_at": time.time(),
                    "source_url": icon_url,
                    "content_hash": hashlib.sha256(data).hexdigest(),
                    "width": width,
                    "height": height,
                    "fallback": bool(is_fallback),
                }
                write_icon_meta(domain, meta_update)
            except Exception as me:
                logger.debug(
                    "Icon meta update failed for %s: %s", domain, me, exc_info=True
                )
        return path

    # === Публичный метод ===
    def save_icon(
        self,
        icon_url: str,
        domain: str,
        is_fallback: bool = False,
        force_refresh: bool = False,
    ) -> Optional[str]:
        meta = read_icon_meta(domain)
        cond_headers = build_conditional_headers(domain, meta, force_refresh)

        # Единый streaming GET с условными заголовками
        headers = {k: v for k, v in cond_headers.items() if v}

        try:
            resp = get_session().request(
                "GET",
                icon_url,
                headers=headers,
                timeout=(5, 8),
                stream=True,
                allow_redirects=True,
            )
        except (RequestException, Timeout, RequestsConnectionError) as e:
            logger.info(
                "[icon] skip reason=request_failed url=%s err=%s",
                icon_url,
                e,
                exc_info=True,
            )
            return None

        # Обработка статусов до чтения тела
        if getattr(resp, "status_code", 0) == 304 and not force_refresh:
            logger.info("[conditional] 304 Not Modified for %s", icon_url)
            icon_filename = f"web_{domain.replace('.', '_')}.png"
            path = str(icon_path_service.get_user_icons_dir() / icon_filename)
            if os.path.exists(path):
                meta2 = read_icon_meta(domain)
                meta2["saved_at"] = time.time()
                write_icon_meta(domain, meta2)
                return path
            return None
        if getattr(resp, "status_code", 0) >= 400:
            logger.info(
                "[icon] skip reason=bad_status status=%s url=%s",
                resp.status_code,
                icon_url,
            )
            return None

        ct_dbg = resp.headers.get("Content-Type")
        cl_dbg = resp.headers.get("Content-Length")
        logger.debug(
            "Icon response %s: status=%s ct=%s len=%s",
            icon_url,
            resp.status_code,
            ct_dbg,
            cl_dbg,
        )

        ct_header = (
            (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        )
        url_lower = icon_url.lower().split("?")[0].split("#")[0]
        ext = url_lower.rsplit(".", 1)[-1] if "." in url_lower else ""
        # Проверка контент-тайпа до чтения
        if not ct_header.startswith("image/"):
            img_ext = url_lower.endswith(
                (".png", ".ico", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")
            )
            if img_ext:
                logger.info(
                    "[icon] non_image_ct ct=%s, but URL suggests image; skipping body %s",
                    ct_header,
                    icon_url,
                )
            else:
                logger.info(
                    "[icon] skip reason=non_image_head ct=%s url=%s",
                    ct_header,
                    icon_url,
                )
            resp.close()
            return None

        # Проверка Content-Length (если есть) до чтения
        max_size = app_config.get_max_web_icon_size()
        if "Content-Length" in resp.headers:
            try:
                cl_val = int(resp.headers.get("Content-Length", "-1"))
            except Exception:
                cl_val = -1
            if cl_val > 0 and cl_val > max_size:
                logger.info(
                    "[icon] skip reason=content_length_excess len=%s limit=%s url=%s",
                    cl_val,
                    max_size,
                    icon_url,
                )
                resp.close()
                return None

        # Стриминг тела с ограничением размера
        body = bytearray()
        try:
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                body.extend(chunk)
                if len(body) > max_size:
                    logger.info(
                        "[icon] skip reason=body_too_large size=%s url=%s",
                        len(body),
                        icon_url,
                    )
                    resp.close()
                    return None
        except (RequestException, Timeout, RequestsConnectionError) as e:
            logger.info(
                "[icon] skip reason=stream_error url=%s err=%s",
                icon_url,
                e,
                exc_info=True,
            )
            resp.close()
            return None
        finally:
            resp.close()

        data: bytes = bytes(body)
        ct = ct_header

        if self.is_non_image_data(ct, data):
            logger.info("[icon] skip reason=non_image ct=%s url=%s", ct, icon_url)
            return None

        # Дополнительная страховка после стрим-лимита
        if len(data) > max_size:
            logger.info(
                "[icon] skip reason=body_too_large size=%s url=%s", len(data), icon_url
            )
            return None

        data2 = self.maybe_convert_svg(icon_url, ct, ext, data)
        if not data2:
            return None

        # Безопасное открытие изображения с ограничением на количество пикселей и проверкой содержимого
        try:
            try:
                max_pixels_limit = int(
                    getattr(app_config, "ICON_MAX_IMAGE_PIXELS", 2_000_000) or 2_000_000
                )
            except Exception:
                max_pixels_limit = 2_000_000

            with _pil_max_pixels(max_pixels_limit):
                # Первая фаза: быстрая проверка контейнера без декодирования пикселей
                with Image.open(BytesIO(data2)) as _probe:
                    _probe.verify()

                # Вторая фаза: повторно открываем для реального чтения/обработки
                with Image.open(BytesIO(data2)) as _img:
                    img = self.select_best_frame(_img)
                    # На случай ленивой загрузки делаем копию в память
                    img = img.copy()
                    if not self.validate_image_geometry(img, icon_url):
                        return None
                    path = self.save_png_with_meta(
                        domain, icon_url, resp.headers, img, data2, is_fallback, meta
                    )
                    etag = resp.headers.get("ETag")
                    lm = resp.headers.get("Last-Modified")
                    w, h = img.size
                    logger.info(
                        "[icon] saved path=%s size=%sx%s url=%s status=%s ct=%s len=%s etag=%s lm=%s",
                        path,
                        w,
                        h,
                        icon_url,
                        resp.status_code,
                        ct_dbg,
                        cl_dbg,
                        etag,
                        lm,
                    )
                    return path
        except (UnidentifiedImageError, Image.DecompressionBombError) as e:
            logger.warning(
                "[icon] unsafe_or_invalid_image url=%s: %s", icon_url, e, exc_info=True
            )
            return None
        except Exception as e:
            logger.error("Save icon error %s: %s", icon_url, e, exc_info=True)
            return None
        finally:
            # MAX_IMAGE_PIXELS восстанавливается контекстным менеджером
            pass


def save_icon(
    icon_url: str,
    domain: str,
    config,
    is_fallback: bool = False,
    force_refresh: bool = False,
) -> Optional[str]:
    """Тонкий фасад поверх IconDownloader.save_icon."""
    return IconDownloader(config).save_icon(
        icon_url, domain, is_fallback, force_refresh
    )


def pick_icon_parallel(
    soup: "BeautifulSoup",
    page_url: str,
    domain: str,
    config,
    force_refresh: bool = False,
) -> Optional[str]:
    # Сначала только локальные и fallback-кандидаты (без сторонних сервисов)
    candidates = find_favicon_candidates(soup, page_url, config, use_external=False)[
        :10
    ]
    logger.debug("Trying %s favicon candidates for %s", len(candidates), domain)

    max_elapsed = float(getattr(config, "ICON_PICK_MAX_SECONDS", 6.0))
    # Уважаем заданный тайм-аут без принудительного минимума 1s
    finish_by = time.monotonic() + max(0.05, max_elapsed)

    def _try_candidates_parallel(icon_urls, is_fallback: bool) -> Optional[str]:
        if not icon_urls:
            return None
        remaining = max(0.0, finish_by - time.monotonic())
        if remaining <= 0:
            logger.info("[limit] Icon pick exceeded max_elapsed_seconds for %s", domain)
            return None

        max_workers_cfg = int(getattr(config, "ICON_MAX_WORKERS", 6) or 6)
        max_workers = max(1, min(len(icon_urls), max_workers_cfg))
        logger.debug(
            "Parallel fetch (workers=%s, size=%s, fallback=%s) for %s",
            max_workers,
            len(icon_urls),
            is_fallback,
            domain,
        )
        # Используем общий пул потоков и неблокирующее ожидание первого завершившегося future
        executor = _get_icon_executor(max_workers)
        try:
            futures = [
                executor.submit(
                    save_icon, u, domain, config, is_fallback, force_refresh
                )
                for u in icon_urls
            ]
            while True:
                remaining = max(0.0, finish_by - time.monotonic())
                if remaining <= 0:
                    logger.debug("Parallel wait timeout: cancelled pending futures")
                    # Отменяем все незавершенные задачи
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    return None
                done, not_done = wait(
                    futures, timeout=remaining, return_when=FIRST_COMPLETED
                )
                # Проверяем завершившиеся задачи
                any_completed = False
                for fut in list(done):
                    any_completed = True
                    try:
                        saved = fut.result()
                    except Exception as e:
                        logger.debug("Parallel fetch error: %s", e, exc_info=True)
                        continue
                    if saved:
                        # Отменяем остальные
                        for f in futures:
                            if f is not fut and not f.done():
                                f.cancel()
                        return saved
                # Если кто-то завершился, но результата нет — продолжаем ждать оставшиеся до дедлайна
                if not not_done:
                    # Все задачи завершились, ни одна не дала результат
                    return None
                if not any_completed:
                    # Ничего не завершилось в заданный таймаут — цикл пересчитает оставшееся время
                    continue
        except Exception as e:
            logger.debug("Parallel wait error: %s", e, exc_info=True)
            return None
        return None

    tried_urls = set(candidates)
    saved_path = _try_candidates_parallel(candidates, is_fallback=False)
    if saved_path:
        logger.info(
            "Successfully saved good-sized icon %s for domain %s", saved_path, domain
        )
        return saved_path
    logger.debug(
        "No icons ≥%spx found, trying fallback mode for %s",
        MIN_GOOD_SIZE,
        domain,
    )
    saved_path = _try_candidates_parallel(candidates, is_fallback=True)
    if saved_path:
        logger.info(
            "Successfully saved fallback icon %s for domain %s", saved_path, domain
        )
        return saved_path
    # После неудачи локальных попыток — подключаем внешние источники при разрешении в конфиге
    if bool(getattr(config, "ICON_USE_EXTERNAL", False)):
        ext_all = find_favicon_candidates(soup, page_url, config, use_external=True)[
            :12
        ]
        ext_only = [u for u in ext_all if u not in tried_urls]
        if ext_only:
            logger.debug(
                "Trying %s external favicon candidates for %s",
                len(ext_only),
                domain,
            )
            saved_path = _try_candidates_parallel(ext_only, is_fallback=True)
            if saved_path:
                logger.info(
                    "Successfully saved external fallback icon %s for domain %s",
                    saved_path,
                    domain,
                )
                return saved_path

    logger.warning(
        "No valid favicon found for domain %s after trying all candidates",
        domain,
    )
    return None


__all__ = [
    "pick_icon_parallel",
    "save_icon",
    "IconDownloader",
    "read_icon_meta",
    "write_icon_meta",
    "get_icon_meta_path",
]
