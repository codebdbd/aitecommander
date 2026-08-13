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
import os
import tempfile
import threading
import time
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
)
from requests.exceptions import (
    RequestException,
    Timeout,
)

from app.config_data import app_config
from app.utils.ui.icon.path_service import icon_path_service

# Set PIL MAX_IMAGE_PIXELS once at import time (avoids per-call lock overhead)
try:
    Image.MAX_IMAGE_PIXELS = int(
        getattr(app_config, "ICON_MAX_IMAGE_PIXELS", 2_000_000) or 2_000_000
    )
except Exception:
    Image.MAX_IMAGE_PIXELS = 2_000_000

from .constants import BS_PARSER, MIN_GOOD_SIZE, TARGET_SIZE, logger
from .favicon_cache import _file_lock
from .http_client import http_request
from .icon_candidates import find_favicon_candidates
from .icon_fallback import (
    clear_domain_failed,
    get_www_variant,
    is_domain_failed,
    mark_domain_failed,
    try_google_favicon_api,
)
from .svg_convert import convert_svg


# === Atomic file write helpers ===
def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write *data* to *target* atomically via a temp file + os.replace().

    The temp file is created in the same directory as *target* so that
    ``os.replace`` is guaranteed to be atomic on the same filesystem.
    On Windows, retries on PermissionError (file held open by reader).
    On failure the temp file is cleaned up and the original is untouched.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_bytes(data)
        _replace_with_retry(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _atomic_write_text(target: Path, text: str) -> None:
    """Write *text* to *target* atomically via a temp file + os.replace()."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(text, encoding="utf-8")
        _replace_with_retry(tmp, target)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _replace_with_retry(src: Path, dst: Path, *, retries: int = 10, delay: float = 0.02) -> None:
    """Retry ``os.replace`` long enough to outlive transient Windows file handles.

    Readers may briefly keep the destination file open without delete sharing,
    which makes ``os.replace`` raise ``PermissionError`` even though the write is
    otherwise valid. A wider exponential backoff keeps the icon pipeline
    progressing under concurrent reads instead of spuriously failing.
    """
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                raise

_ICON_LOCKS: OrderedDict[str, threading.Lock] = OrderedDict()
_ICON_LOCKS_GUARD = threading.Lock()

# Shared executor for icon downloads (singleton)
_ICON_EXECUTOR = None
_ICON_EXECUTOR_SIZE = 0  # current pool size
_ICON_EXECUTOR_GUARD = threading.Lock()


def _is_cancelled(cancel_event) -> bool:
    """Safely check cancel flag for cooperative cancellation."""
    return bool(cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)())


def _combine_cancel_events(*events):
    valid_events = [ev for ev in events if ev is not None]
    if not valid_events:
        return None

    class _CombinedCancelEvent:
        def is_set(self_nonlocal):
            return any(getattr(ev, "is_set", lambda: False)() for ev in valid_events)

    return _CombinedCancelEvent()


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
        p = Path(get_icon_meta_path(domain))
        text = json.dumps(meta, ensure_ascii=False, indent=2)
        _atomic_write_text(p, text)
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
            # SECURITY: Limit SVG size to prevent DoS (max 2MB)
            max_svg_size = int(getattr(app_config, "ICON_MAX_SVG_SIZE", 2_097_152) or 2_097_152)
            if len(data) > max_svg_size:
                logger.warning(
                    "[svg] Skipping oversized SVG (size=%s, limit=%s) from %s",
                    len(data),
                    max_svg_size,
                    icon_url,
                )
                return None

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
    ) -> tuple[str | None, bool]:
        path = str(
            icon_path_service.get_user_icons_dir()
            / f"web_{domain.replace('.', '_')}.png"
        )
        width, height = img.size
        lock = _get_icon_lock(domain)
        with lock:
            with _file_lock(f"{path}.lock"):
                # RACE CONDITION FIX: Check if fresh icon already exists
                path_obj = Path(path)
                if path_obj.exists():
                    try:
                        # Skip if file was modified less than 1 hour ago
                        age_seconds = time.time() - path_obj.stat().st_mtime
                        if age_seconds < 3600:  # 1 hour
                            logger.debug(
                                "[race] Icon already exists and is fresh (age=%.1fs) for %s, skipping save",
                                age_seconds,
                                domain,
                            )
                            clear_domain_failed(icon_url)
                            return path, False
                    except Exception as e:
                        logger.debug("Failed to check icon age for %s: %s", domain, e)

                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                buf = BytesIO()
                img.save(buf, format="PNG")
                _atomic_write_bytes(path_obj, buf.getvalue())
                # NOTE: PNG and metadata are replaced atomically independently,
                # not as a single transaction. Readers may briefly see stale meta.
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
                clear_domain_failed(icon_url)
        return path, True

    # === Public method ===
    def _fetch_icon_response(
        self, icon_url, domain, meta, force_refresh, cancel_event=None
    ):
        """Fetch icon HTTP response."""
        if _is_cancelled(cancel_event):
            return None
        cond_headers = build_conditional_headers(domain, meta, force_refresh)
        headers = {k: v for k, v in cond_headers.items() if v}

        try:
            if _is_cancelled(cancel_event):
                return None
            resp = http_request(
                icon_url,
                self.config,
                extra_headers=headers,
                allow_non_2xx=True,
                timeout_override=(5, 8),
                retries=0,
                method="GET",
                stream=True,
                allow_redirects=True,
                prefer_cloudscraper_primary=False,
            )
            if _is_cancelled(cancel_event) and resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
                return None
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
            clear_domain_failed(icon_url)
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

    def _stream_response_body(self, resp, icon_url, max_size, cancel_event=None):
        """Stream response body with size limit."""
        body = bytearray()
        try:
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                if _is_cancelled(cancel_event):
                    return None
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

    def _process_and_save_image(
        self,
        data2,
        domain,
        icon_url,
        resp,
        ct_dbg,
        cl_dbg,
        is_fallback,
        meta,
        cancel_event=None,
    ):
        """Process and save image data."""
        if _is_cancelled(cancel_event):
            return None

        with Image.open(BytesIO(data2)) as _probe:
            _probe.verify()

        with Image.open(BytesIO(data2)) as _img:
            if _is_cancelled(cancel_event):
                return None
            img = self.select_best_frame(_img)
            img = img.copy()
            if not self.validate_image_geometry(img, icon_url):
                return None
            if _is_cancelled(cancel_event):
                return None
            path, did_save = self.save_png_with_meta(
                domain, icon_url, resp.headers, img, data2, is_fallback, meta
            )
            if did_save:
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

    def _handle_response_status(
        self, resp, domain: str, icon_url: str, force_refresh: bool
    ) -> tuple[bool, str | None]:
        """Handle HTTP status codes; return (handled, path_or_none).

        - 304 returns existing path (unless force_refresh)
        - 4xx/5xx returns (True, None) and marks domain failed only for
          statuses that plausibly indicate a host-wide icon block
        - otherwise returns (False, None) to continue processing
        """
        status = getattr(resp, "status_code", 0)
        if status == 304:
            if force_refresh:
                return True, None
            logger.info("[conditional] 304 Not Modified for %s", icon_url)
            icon_filename = f"web_{domain.replace('.', '_')}.png"
            path = str(icon_path_service.get_user_icons_dir() / icon_filename)
            if Path(path).exists():
                meta2 = read_icon_meta(domain)
                meta2["saved_at"] = time.time()
                write_icon_meta(domain, meta2)
                return True, path
            return True, None

        if status >= 400:
            logger.info(
                "[icon] skip reason=bad_status status=%s url=%s", status, icon_url
            )
            if status in (403, 429) or status >= 500:
                mark_domain_failed(icon_url, status)
            return True, None
        return False, None

    def _get_ext_and_max(self, icon_url: str) -> tuple[str, int]:
        """Extract extension from URL and read maximum allowed size."""
        url_lower = icon_url.lower().split("?")[0].split("#")[0]
        ext = url_lower.rsplit(".", 1)[-1] if "." in url_lower else ""
        max_size = app_config.get_max_web_icon_size()
        return ext, max_size

    def _read_body_with_limits(
        self, resp, icon_url: str, max_size: int, cancel_event=None
    ) -> bytes | None:
        """Stream response body via helper with limits and ensure resp closes."""
        try:
            return self._stream_response_body(
                resp, icon_url, max_size, cancel_event=cancel_event
            )
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def _should_reject_body(
        self, ct_header: str, data: bytes, icon_url: str, max_size: int
    ) -> bool:
        """Return True if body should be rejected (non-image or too large)."""
        if self.is_non_image_data(ct_header, data):
            logger.info(
                "[icon] skip reason=non_image ct=%s url=%s", ct_header, icon_url
            )
            return True
        if len(data) > max_size:
            logger.info(
                "[icon] skip reason=body_too_large size=%s url=%s", len(data), icon_url
            )
            return True
        return False

    def _preprocess_and_get_data(
        self, resp, icon_url: str, cancel_event=None
    ) -> tuple[bytes, str | None, str | None, str, str] | None:
        """Validate headers, log debug, check sizes, read and validate body.

        Returns tuple: (data, ct_dbg, cl_dbg, ct_header, ext) or None on rejection.
        """
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
            try:
                resp.close()
            except Exception:
                pass
            return None

        ext, max_size = self._get_ext_and_max(icon_url)
        if not self._check_content_length(resp, icon_url, max_size):
            try:
                resp.close()
            except Exception:
                pass
            return None

        data = self._read_body_with_limits(
            resp, icon_url, max_size, cancel_event=cancel_event
        )
        if data is None:
            return None
        if self._should_reject_body(ct_header, data, icon_url, max_size):
            return None
        if _is_cancelled(cancel_event):
            return None
        return data, ct_dbg, cl_dbg, ct_header, ext

    def _fetch_and_validate_response(
        self,
        icon_url: str,
        domain: str,
        force_refresh: bool,
        cancel_event=None,
        meta: dict | None = None,
    ):
        """Fetch response and handle cancellation/status; return (resp or None, path or None)."""
        resp = self._fetch_icon_response(
            icon_url, domain, meta or {}, force_refresh, cancel_event=cancel_event
        )
        if resp is None:
            return None, None
        if _is_cancelled(cancel_event):
            try:
                resp.close()
            except Exception:
                pass
            return None, None
        handled, maybe_path = self._handle_response_status(
            resp, domain, icon_url, force_refresh
        )
        if handled:
            if (
                getattr(resp, "status_code", 0) == 304
                and maybe_path is None
                and not force_refresh
            ):
                try:
                    resp.close()
                except Exception:
                    pass
                logger.info(
                    "[conditional] 304 missing local file, retrying without validators for %s",
                    icon_url,
                )
                retry_resp = self._fetch_icon_response(
                    icon_url,
                    domain,
                    meta or {},
                    True,
                    cancel_event=cancel_event,
                )
                if retry_resp is None:
                    return None, None
                handled, maybe_path = self._handle_response_status(
                    retry_resp,
                    domain,
                    icon_url,
                    True,
                )
                if handled:
                    try:
                        retry_resp.close()
                    except Exception:
                        pass
                    return None, maybe_path
                return retry_resp, None
            try:
                resp.close()
            except Exception:
                pass
            return None, maybe_path
        return resp, None

    def save_icon(
        self,
        icon_url: str,
        domain: str,
        is_fallback: bool = False,
        force_refresh: bool = False,
        cancel_event=None,
    ) -> str | None:
        if _is_cancelled(cancel_event):
            return None
        meta = read_icon_meta(domain)
        if _is_cancelled(cancel_event):
            return None
        resp, maybe_path = self._fetch_and_validate_response(
            icon_url, domain, force_refresh, cancel_event, meta
        )
        if resp is None:
            return maybe_path

        data_tuple = self._preprocess_and_get_data(resp, icon_url, cancel_event)
        if data_tuple is None:
            return None
        data, ct_dbg, cl_dbg, ct_header, ext = data_tuple

        data2 = self.maybe_convert_svg(icon_url, ct_header, ext, data)
        if not data2:
            return None

        try:
            return self._process_and_save_image(
                data2,
                domain,
                icon_url,
                resp,
                ct_dbg,
                cl_dbg,
                is_fallback,
                meta,
                cancel_event=cancel_event,
            )
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
    cancel_event=None,
) -> str | None:
    """Thin facade over IconDownloader.save_icon."""
    return IconDownloader(config).save_icon(
        icon_url,
        domain,
        is_fallback,
        force_refresh,
        cancel_event=cancel_event,
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


def _try_candidates_parallel_impl(
    icon_urls,
    domain,
    config,
    is_fallback,
    force_refresh,
    finish_by,
    batch_size=None,
    cancel_event=None,
):
    """Try icon candidates in parallel with optional batching.
    
    Args:
        batch_size: If provided, only submit this many candidates initially.
                   Useful for prioritizing best candidates.
    """
    if not icon_urls:
        return None
    if _is_cancelled(cancel_event):
        return None
    remaining = max(0.0, finish_by - time.monotonic())
    if remaining <= 0:
        logger.info("[limit] Icon pick exceeded max_elapsed_seconds for %s", domain)
        return None

    # Apply batch size limit if specified
    urls_to_try = icon_urls[:batch_size] if batch_size else icon_urls
    
    max_workers_cfg = int(getattr(config, "ICON_MAX_WORKERS", 6) or 6)
    max_workers = max(1, min(len(urls_to_try), max_workers_cfg))
    logger.debug(
        "Parallel fetch (workers=%s, size=%s/%s, fallback=%s) for %s",
        max_workers,
        len(urls_to_try),
        len(icon_urls),
        is_fallback,
        domain,
    )
    executor = _get_icon_executor(max_workers)
    local_cancel_event = threading.Event()
    combined_cancel_event = _combine_cancel_events(cancel_event, local_cancel_event)
    try:
        futures = _submit_candidate_futures(
            executor,
            urls_to_try,
            domain,
            config,
            is_fallback,
            force_refresh,
            combined_cancel_event,
        )
        if not futures or _is_cancelled(combined_cancel_event):
            _cancel_pending_futures(futures)
            return None
        return _await_first_saved(
            futures,
            finish_by,
            domain,
            combined_cancel_event,
            stop_event=local_cancel_event,
        )
    except Exception as e:
        logger.debug("Parallel wait error: %s", e, exc_info=True)
        return None


def _submit_candidate_futures(
    executor,
    urls_to_try,
    domain,
    config,
    is_fallback,
    force_refresh,
    cancel_event,
):
    """Submit download tasks for each candidate URL."""
    futures = []
    for u in urls_to_try:
        if _is_cancelled(cancel_event):
            break
        futures.append(
            executor.submit(
                save_icon,
                u,
                domain,
                config,
                is_fallback,
                force_refresh,
                cancel_event=cancel_event,
            )
        )
    return futures


def _await_first_saved(futures, finish_by, domain, cancel_event, stop_event=None):
    """Wait until first future returns saved path or timeout/cancel occurs."""
    while futures:
        if _is_cancelled(cancel_event):
            logger.debug("Parallel fetch cancelled for %s", domain)
            if stop_event is not None:
                stop_event.set()
            _cancel_pending_futures(futures)
            return None
        remaining = max(0.0, finish_by - time.monotonic())
        if remaining <= 0:
            logger.debug("Parallel wait timeout: cancelled pending futures")
            if stop_event is not None:
                stop_event.set()
            _cancel_pending_futures(futures)
            return None
        done, not_done = wait(futures, timeout=remaining, return_when=FIRST_COMPLETED)
        any_completed = bool(done)
        saved = _check_completed_futures(futures, done)
        if saved:
            if stop_event is not None:
                stop_event.set()
            # Cancel any tasks that are still pending/not started to reduce noise
            try:
                _cancel_pending_futures(list(not_done))
            except Exception:
                pass
            return saved
        if not not_done:
            return None
        if not any_completed:
            continue
    return None


def _try_external_candidates(
    config,
    soup,
    page_url,
    domain,
    tried_urls,
    finish_by,
    force_refresh,
    cancel_event=None,
):
    """Try external icon candidates if enabled."""
    if _is_cancelled(cancel_event):
        return None
    if not bool(getattr(config, "ICON_USE_EXTERNAL", False)):
        return None
    ext_all = find_favicon_candidates(
        soup, page_url, config, use_external=True, cancel_event=cancel_event
    )[:12]
    ext_only = [u for u in ext_all if u not in tried_urls]
    if ext_only:
        if _is_cancelled(cancel_event):
            return None
        logger.debug(
            "Trying %s external favicon candidates for %s",
            len(ext_only),
            domain,
        )
        saved_path = _try_candidates_parallel_impl(
            ext_only,
            domain,
            config,
            True,
            force_refresh,
            finish_by,
            cancel_event=cancel_event,
        )
        if saved_path:
            logger.info(
                "Successfully saved external fallback icon %s for domain %s",
                saved_path,
                domain,
            )
            return saved_path
    return None


def _phase3_try_www_variant(
    soup,
    page_url: str,
    domain: str,
    config,
    finish_by: float,
    force_refresh: bool,
    cancel_event=None,
) -> str | None:
    """Try www/non-www variant page to fetch additional candidates.

    Best-effort: fetch HTML of variant URL and try up to 5 best internal candidates.
    """
    if _is_cancelled(cancel_event):
        return None
    logger.debug("[phase3] Trying www/non-www variant for %s", page_url)
    variant_url = get_www_variant(page_url)
    if not variant_url or variant_url == page_url:
        return None
    try:
        resp = http_request(
            variant_url,
            config,
            allow_non_2xx=True,
            timeout_override=(5, 8),
            retries=int(getattr(config, "HTTP_RETRIES", 2) or 2),
            method="GET",
            stream=False,
            allow_redirects=True,
        )
        if not resp or getattr(resp, "status_code", 0) >= 400:
            try:
                if resp is not None:
                    resp.close()
            except Exception:
                pass
            return None
        try:
            variant_html = getattr(resp, "text", "") or ""
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if not variant_html.strip():
            return None
        variant_soup = BeautifulSoup(variant_html, BS_PARSER)
        variant_candidates = find_favicon_candidates(
            variant_soup,
            variant_url,
            config,
            use_external=False,
            cancel_event=cancel_event,
        )[:5]
        return _try_candidates_parallel_impl(
            variant_candidates,
            domain,
            config,
            True,
            force_refresh,
            finish_by,
            cancel_event=cancel_event,
        )
    except Exception as e:  # noqa: BLE001 - best-effort fallback
        logger.debug("[phase3] www-variant fetch failed: %s", e)
        return None


def _phase3_try_homepage_root(
    page_url: str,
    domain: str,
    config,
    finish_by: float,
    force_refresh: bool,
    cancel_event=None,
) -> str | None:
    """Try homepage/root HTML when the current page is SPA-like or head-poor."""
    if _is_cancelled(cancel_event):
        return None
    try:
        parsed = urlparse(page_url)
        scheme = parsed.scheme or "https"
        netloc = (parsed.netloc or "").strip()
    except Exception:
        return None
    if not netloc:
        return None

    root_url = f"{scheme}://{netloc}/"
    normalized_path = (parsed.path or "").strip()
    if root_url == page_url and normalized_path in {"", "/"}:
        return None

    logger.debug("[phase3] Trying homepage root for %s via %s", page_url, root_url)
    try:
        resp = http_request(
            root_url,
            config,
            allow_non_2xx=True,
            timeout_override=(5, 8),
            retries=int(getattr(config, "HTTP_RETRIES", 2) or 2),
            method="GET",
            stream=False,
            allow_redirects=True,
        )
        if not resp or getattr(resp, "status_code", 0) >= 400:
            try:
                if resp is not None:
                    resp.close()
            except Exception:
                pass
            return None
        try:
            homepage_html = getattr(resp, "text", "") or ""
        finally:
            try:
                resp.close()
            except Exception:
                pass
        if not homepage_html.strip():
            return None
        try:
            homepage_soup = BeautifulSoup(homepage_html, BS_PARSER)
        except Exception:
            homepage_soup = BeautifulSoup(homepage_html, "html.parser")
        homepage_candidates = find_favicon_candidates(
            homepage_soup,
            root_url,
            config,
            use_external=False,
            cancel_event=cancel_event,
        )[:8]
        return _try_candidates_parallel_impl(
            homepage_candidates,
            domain,
            config,
            True,
            force_refresh,
            finish_by,
            cancel_event=cancel_event,
        )
    except Exception as e:  # noqa: BLE001 - best-effort fallback
        logger.debug("[phase3] homepage-root fetch failed: %s", e)
        return None


def _phase4_google_api(
    domain: str,
    config,
    force_refresh: bool,
    cancel_event=None,
) -> str | None:
    """Absolute last resort: Google Favicon API."""
    if _is_cancelled(cancel_event):
        return None
    logger.debug("[phase4] Trying Google Favicon API for %s", domain)
    google_url = try_google_favicon_api(domain, size=128)
    if _is_cancelled(cancel_event):
        return None
    return save_icon(
        google_url,
        domain,
        config,
        is_fallback=True,
        force_refresh=force_refresh,
        cancel_event=cancel_event,
    )


def pick_icon_parallel(
    soup: BeautifulSoup,
    page_url: str,
    domain: str,
    config,
    force_refresh: bool = False,
    cancel_event=None,
) -> str | None:
    """Pick best icon using multi-phase prioritization strategy.
    
    Phase 1: Try top-3 primary candidates (link-icon, apple-touch-icon) with 2s timeout
    Phase 2: If no result, try remaining candidates + external services
    Phase 3: Try www/non-www variant
    Phase 4: Google Favicon API as absolute fallback
    """
    if _is_cancelled(cancel_event):
        return None
    # Skip if domain recently failed (unless force_refresh)
    if not force_refresh and is_domain_failed(page_url):
        logger.debug("[failed_cache] Skipping domain %s (recently failed)", domain)
        # Still try Google API as last resort
        google_url = try_google_favicon_api(domain, size=128)
        if _is_cancelled(cancel_event):
            return None
        return save_icon(
            google_url,
            domain,
            config,
            is_fallback=True,
            force_refresh=False,
            cancel_event=cancel_event,
        )
    
    candidates = find_favicon_candidates(
        soup, page_url, config, use_external=False, cancel_event=cancel_event
    )[:10]
    logger.debug("Trying %s favicon candidates for %s", len(candidates), domain)

    max_elapsed = float(getattr(config, "ICON_PICK_MAX_SECONDS", 6.0))
    finish_by = time.monotonic() + max(0.05, max_elapsed)
    tried_urls = set(candidates)

    # PHASE 1: Try top-3 primary candidates first (fast path)
    phase1_timeout = min(2.0, max_elapsed * 0.4)  # 40% of total time or 2s
    phase1_finish = time.monotonic() + phase1_timeout
    saved_path = _phase1_try_top3(candidates, domain, config, force_refresh, phase1_finish, cancel_event)
    if saved_path:
        return saved_path

    # PHASE 2: Try all remaining candidates if phase 1 failed
    saved_path = _phase2_try_all(candidates, domain, config, force_refresh, finish_by, cancel_event)
    if saved_path:
        return saved_path
    
    # Fallback mode: accept smaller icons
    logger.debug(
        "No icons ≥%spx found, trying fallback mode for %s",
        MIN_GOOD_SIZE,
        domain,
    )
    saved_path = _try_candidates_parallel_impl(
        candidates,
        domain,
        config,
        True,
        force_refresh,
        finish_by,
        cancel_event=cancel_event,
    )
    if saved_path:
        logger.info(
            "Successfully saved fallback icon %s for domain %s", saved_path, domain
        )
        return saved_path

    # External services as last resort
    saved_path = _try_external_candidates(
        config,
        soup,
        page_url,
        domain,
        tried_urls,
        finish_by,
        force_refresh,
        cancel_event=cancel_event,
    )
    if saved_path:
        return saved_path

    # PHASE 3: Try homepage/root HTML for SPA/login-shell pages
    saved_path = _phase3_try_homepage_root(
        page_url, domain, config, finish_by, force_refresh, cancel_event
    )
    if saved_path:
        logger.info(
            "[phase3] Successfully saved icon from homepage root %s for domain %s",
            saved_path,
            domain,
        )
        return saved_path

    # PHASE 4: Try www/non-www variant if original failed
    saved_path = _phase3_try_www_variant(
        soup, page_url, domain, config, finish_by, force_refresh, cancel_event
    )
    if saved_path:
        logger.info(
            "[phase4] Successfully saved icon from www-variant %s for domain %s",
            saved_path, domain
        )
        return saved_path

    # PHASE 5: Google Favicon API as absolute last resort
    saved_path = _phase4_google_api(domain, config, force_refresh, cancel_event)
    if saved_path:
        logger.info(
            "[phase5] Successfully saved icon from Google API %s for domain %s",
            saved_path, domain
        )
        return saved_path

    logger.info("No suitable icon found for %s", domain)
    return None


def _phase1_try_top3(candidates, domain, config, force_refresh, phase1_finish, cancel_event):
    """Phase 1: try top 3 candidates quickly."""
    saved_path = _try_candidates_parallel_impl(
        candidates,
        domain,
        config,
        False,
        force_refresh,
        phase1_finish,
        batch_size=3,
        cancel_event=cancel_event,
    )
    if saved_path:
        logger.info("[phase1] Successfully saved icon %s for domain %s", saved_path, domain)
    return saved_path


def _phase2_try_all(candidates, domain, config, force_refresh, finish_by, cancel_event):
    """Phase 2: try all remaining candidates in given time budget."""
    logger.debug(
        "[phase2] No icons found in phase 1, trying all %s candidates for %s",
        len(candidates),
        domain,
    )
    saved_path = _try_candidates_parallel_impl(
        candidates,
        domain,
        config,
        False,
        force_refresh,
        finish_by,
        cancel_event=cancel_event,
    )
    if saved_path:
        logger.info(
            "[phase2] Successfully saved good-sized icon %s for domain %s", saved_path, domain
        )
    return saved_path


__all__ = [
    "pick_icon_parallel",
    "save_icon",
    "IconDownloader",
    "read_icon_meta",
    "write_icon_meta",
    "get_icon_meta_path",
]
