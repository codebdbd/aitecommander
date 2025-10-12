"""Icon downloading and saving utilities.

Separated pure functions and `IconDownloader` class:
- read/write metadata
- build conditional headers
- validate image type/size/aspect ratio
- convert SVG
- save file and update metadata

`save_icon` is kept as a thin facade over `IconDownloader`.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from PIL import Image, UnidentifiedImageError
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import RequestException, Timeout

from app.config_data import app_config
from app.utils.ui.icon.path_service import icon_path_service

if TYPE_CHECKING:
    # For type hints only; avoids runtime dependency and fixes Ruff F821
    from bs4 import BeautifulSoup

from .constants import MIN_GOOD_SIZE, TARGET_SIZE, logger
from .http_client import get_session as get_session  # backward-compat for tests
from .http_client import http_request
from .icon_candidates import find_favicon_candidates
from .svg_convert import convert_svg

_ICON_LOCKS: OrderedDict[str, threading.Lock] = OrderedDict()
_ICON_LOCKS_GUARD = threading.Lock()

# Guard for thread-safe temporary changes to PIL global settings
_PIL_MAX_PIXELS_GUARD = threading.Lock()

# Shared executor for icon downloads (singleton)
_ICON_EXECUTOR = None
_ICON_EXECUTOR_SIZE = 0  # current pool size
_ICON_EXECUTOR_GUARD = threading.Lock()


def _shutdown_icon_executor(wait: bool = False):  # pragma: no cover - atexit path
    global _ICON_EXECUTOR, _ICON_EXECUTOR_SIZE
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
    finally:
        _ICON_EXECUTOR_SIZE = 0


def _get_icon_executor(max_workers_hint: int) -> ThreadPoolExecutor:
    """Returns shared ThreadPoolExecutor for icon downloads.

    Pool is created lazily and can dynamically grow when `max_workers_hint` increases.
    On expansion, old pool is gracefully stopped without waiting (running tasks finish there).
    Upper bound is `app_config.ICON_MAX_WORKERS` (default 6).
    """
    global _ICON_EXECUTOR, _ICON_EXECUTOR_SIZE

    # Fast lock-free check
    ex = _ICON_EXECUTOR
    if ex is not None and _ICON_EXECUTOR_SIZE >= max(1, int(max_workers_hint or 1)):
        return ex

    with _ICON_EXECUTOR_GUARD:
        # Recalculate effective sizes under lock
        try:
            cfg_limit = int(getattr(app_config, "ICON_MAX_WORKERS", 6) or 6)
        except Exception:
            cfg_limit = 6
        desired = max(1, int(min(max_workers_hint or 1, cfg_limit)))

        if _ICON_EXECUTOR is None:
            # Initial creation
            _ICON_EXECUTOR = ThreadPoolExecutor(max_workers=desired)
            _ICON_EXECUTOR_SIZE = desired
            try:
                atexit.register(lambda: _shutdown_icon_executor(wait=False))
            except Exception as e:  # pragma: no cover - best-effort atexit
                logger.debug("failed to register icon executor shutdown: %s", e)
            return _ICON_EXECUTOR

        # Existing pool present. If new size is larger — expand by recreating
        if desired > _ICON_EXECUTOR_SIZE:
            old = _ICON_EXECUTOR
            try:
                _ICON_EXECUTOR = ThreadPoolExecutor(max_workers=desired)
                _ICON_EXECUTOR_SIZE = desired
            except Exception as e:
                logger.debug("failed to resize icon executor: %s", e, exc_info=True)
                # Return old pool on failure
                _ICON_EXECUTOR = old
                return _ICON_EXECUTOR
            # Don't block on old pool shutdown; don't cancel already running tasks
            try:
                old.shutdown(wait=False)
            except Exception:
                pass
            return _ICON_EXECUTOR

        # Current size is sufficient
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


# === Metadata and paths ===
def get_icon_meta_path(domain: str) -> str:
    d = (domain or "").replace(".", "_")
    return str(icon_path_service.get_user_icons_dir() / f"web_{d}.meta.json")


def read_icon_meta(domain: str) -> dict:
    try:
        p = get_icon_meta_path(domain)
        if Path(p).exists():
            with open(p, encoding="utf-8") as f:
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
        # Mark as recently used
        try:
            _ICON_LOCKS.move_to_end(d)
        except Exception:
            pass

        # LRU cleanup when limit exceeded
        try:
            max_locks = int(getattr(app_config, "ICON_LOCKS_MAX", 1024) or 1024)
        except Exception:
            max_locks = 1024
        if len(_ICON_LOCKS) > max_locks:
            # Try to remove oldest unlocked lock
            keys_to_check = list(_ICON_LOCKS.keys())
            for k in keys_to_check:
                if len(_ICON_LOCKS) <= max_locks:
                    break
                if k == d:
                    # don't touch just-used key
                    continue
                lock_var = _ICON_LOCKS.get(k)
                if lock_var is None:
                    continue
                if not lock_var.locked():
                    try:
                        _ICON_LOCKS.pop(k, None)
                    except Exception:
                        pass
            # If all were locked, size may temporarily remain > max_locks
        return lock


class IconDownloader:
    """Icon download/validation/save logic, broken down into steps."""

    def __init__(self, config):
        self.config = config
        # Support for test client
        self.http_get = getattr(config, "HTTP_GET", None) or (
            lambda u, headers, timeout: requests.get(
                u, headers=headers, timeout=timeout
            )
        )

    # === Validation and decoding ===
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
    ) -> bytes | None:
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
        meta: dict | None = None,
    ) -> str | None:
        path = str(
            icon_path_service.get_user_icons_dir()
            / f"web_{domain.replace('.', '_')}.png"
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

    # === Public method ===
    def _fetch_icon_response(self, icon_url, domain, meta, force_refresh):
        """Fetch icon HTTP response."""
        cond_headers = build_conditional_headers(domain, meta, force_refresh)
        headers = {k: v for k, v in cond_headers.items() if v}

        try:
            resp = http_request(
                icon_url,
                self.config,
                extra_headers=headers,
                allow_non_2xx=True,
                timeout_override=(5, 8),
                retries=int(getattr(self.config, "HTTP_RETRIES", 2) or 2),
                method="GET",
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
        return resp

    def _handle_304_response(self, domain, icon_url, force_refresh):
        """Handle 304 Not Modified response."""
        if force_refresh:
            return None
        logger.info("[conditional] 304 Not Modified for %s", icon_url)
        icon_filename = f"web_{domain.replace('.', '_')}.png"
        path = str(icon_path_service.get_user_icons_dir() / icon_filename)
        if Path(path).exists():
            meta2 = read_icon_meta(domain)
            meta2["saved_at"] = time.time()
            write_icon_meta(domain, meta2)
            return path
        return None

    def _validate_content_type(self, resp, icon_url):
        """Validate response content type."""
        ct_header = (
            (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        )
        url_lower = icon_url.lower().split("?")[0].split("#")[0]
        
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
            return None
        return ct_header

    def _check_content_length(self, resp, icon_url, max_size):
        """Check Content-Length header."""
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
                return False
        return True

    def _stream_response_body(self, resp, icon_url, max_size):
        """Stream response body with size limit."""
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
                    return None
        except (RequestException, Timeout, RequestsConnectionError) as e:
            logger.info(
                "[icon] skip reason=stream_error url=%s err=%s",
                icon_url,
                e,
                exc_info=True,
            )
            return None
        return bytes(body)

    def _process_and_save_image(self, data2, domain, icon_url, resp, ct_dbg, cl_dbg, is_fallback, meta):
        """Process and save image data."""
        try:
            max_pixels_limit = int(
                getattr(app_config, "ICON_MAX_IMAGE_PIXELS", 2_000_000) or 2_000_000
            )
        except Exception:
            max_pixels_limit = 2_000_000

        with _pil_max_pixels(max_pixels_limit):
            with Image.open(BytesIO(data2)) as _probe:
                _probe.verify()

            with Image.open(BytesIO(data2)) as _img:
                img = self.select_best_frame(_img)
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

    def save_icon(
        self,
        icon_url: str,
        domain: str,
        is_fallback: bool = False,
        force_refresh: bool = False,
    ) -> str | None:
        meta = read_icon_meta(domain)
        resp = self._fetch_icon_response(icon_url, domain, meta, force_refresh)
        if resp is None:
            return None

        if getattr(resp, "status_code", 0) == 304:
            return self._handle_304_response(domain, icon_url, force_refresh)
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

        ct_header = self._validate_content_type(resp, icon_url)
        if ct_header is None:
            resp.close()
            return None

        url_lower = icon_url.lower().split("?")[0].split("#")[0]
        ext = url_lower.rsplit(".", 1)[-1] if "." in url_lower else ""
        max_size = app_config.get_max_web_icon_size()
        
        if not self._check_content_length(resp, icon_url, max_size):
            resp.close()
            return None

        try:
            data = self._stream_response_body(resp, icon_url, max_size)
        finally:
            resp.close()

        if data is None:
            return None

        if self.is_non_image_data(ct_header, data):
            logger.info("[icon] skip reason=non_image ct=%s url=%s", ct_header, icon_url)
            return None

        if len(data) > max_size:
            logger.info(
                "[icon] skip reason=body_too_large size=%s url=%s", len(data), icon_url
            )
            return None

        data2 = self.maybe_convert_svg(icon_url, ct_header, ext, data)
        if not data2:
            return None

        try:
            return self._process_and_save_image(data2, domain, icon_url, resp, ct_dbg, cl_dbg, is_fallback, meta)
        except (UnidentifiedImageError, Image.DecompressionBombError) as e:
            logger.warning(
                "[icon] unsafe_or_invalid_image url=%s: %s", icon_url, e, exc_info=True
            )
            return None
        except Exception as e:
            logger.error("Save icon error %s: %s", icon_url, e, exc_info=True)
            return None


def save_icon(
    icon_url: str,
    domain: str,
    config,
    is_fallback: bool = False,
    force_refresh: bool = False,
) -> str | None:
    """Thin facade over IconDownloader.save_icon."""
    return IconDownloader(config).save_icon(
        icon_url, domain, is_fallback, force_refresh
    )


def _cancel_pending_futures(futures):
    """Cancel all pending futures."""
    for f in futures:
        if not f.done():
            f.cancel()


def _check_completed_futures(futures, done, fut_to_exclude=None):
    """Check completed futures and cancel remaining if result found."""
    for fut in list(done):
        try:
            saved = fut.result()
        except Exception as e:
            logger.debug("Parallel fetch error: %s", e, exc_info=True)
            continue
        if saved:
            for f in futures:
                if f is not fut_to_exclude and not f.done():
                    f.cancel()
            return saved
    return None


def _try_candidates_parallel_impl(icon_urls, domain, config, is_fallback, force_refresh, finish_by):
    """Try icon candidates in parallel."""
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
                _cancel_pending_futures(futures)
                return None
            done, not_done = wait(
                futures, timeout=remaining, return_when=FIRST_COMPLETED
            )
            any_completed = bool(done)
            saved = _check_completed_futures(futures, done)
            if saved:
                return saved
            if not not_done:
                return None
            if not any_completed:
                continue
    except Exception as e:
        logger.debug("Parallel wait error: %s", e, exc_info=True)
        return None
    return None


def _try_external_candidates(config, soup, page_url, domain, tried_urls, finish_by, force_refresh):
    """Try external icon candidates if enabled."""
    if not bool(getattr(config, "ICON_USE_EXTERNAL", False)):
        return None
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
        saved_path = _try_candidates_parallel_impl(ext_only, domain, config, True, force_refresh, finish_by)
        if saved_path:
            logger.info(
                "Successfully saved external fallback icon %s for domain %s",
                saved_path,
                domain,
            )
            return saved_path
    return None


def pick_icon_parallel(
    soup: BeautifulSoup,
    page_url: str,
    domain: str,
    config,
    force_refresh: bool = False,
) -> str | None:
    candidates = find_favicon_candidates(soup, page_url, config, use_external=False)[
        :10
    ]
    logger.debug("Trying %s favicon candidates for %s", len(candidates), domain)

    max_elapsed = float(getattr(config, "ICON_PICK_MAX_SECONDS", 6.0))
    finish_by = time.monotonic() + max(0.05, max_elapsed)

    tried_urls = set(candidates)
    saved_path = _try_candidates_parallel_impl(candidates, domain, config, False, force_refresh, finish_by)
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
    saved_path = _try_candidates_parallel_impl(candidates, domain, config, True, force_refresh, finish_by)
    if saved_path:
        logger.info(
            "Successfully saved fallback icon %s for domain %s", saved_path, domain
        )
        return saved_path
    
    saved_path = _try_external_candidates(config, soup, page_url, domain, tried_urls, finish_by, force_refresh)
    if saved_path:
        return saved_path
    
    logger.info("No suitable icon found for %s", domain)
    return None


__all__ = [
    "pick_icon_parallel",
    "save_icon",
    "IconDownloader",
    "read_icon_meta",
    "write_icon_meta",
    "get_icon_meta_path",
]
