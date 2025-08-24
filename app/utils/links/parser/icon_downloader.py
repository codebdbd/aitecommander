"""Icon downloading and saving utilities."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import TYPE_CHECKING, Optional

import requests
from PIL import Image

from app.config_data import app_config
from app.utils.ui.icon.path_service import icon_path_service

if TYPE_CHECKING:
    # For type hints only; avoids runtime dependency and fixes Ruff F821
    from bs4 import BeautifulSoup

from .constants import MIN_GOOD_SIZE, logger
from .http_client import http_request
from .icon_candidates import find_favicon_candidates
from .svg_convert import convert_svg

_ICON_LOCKS: dict[str, threading.Lock] = {}
_ICON_LOCKS_GUARD = threading.Lock()


def _get_icon_lock(domain: str) -> threading.Lock:
    d = domain or ""
    with _ICON_LOCKS_GUARD:
        lock = _ICON_LOCKS.get(d)
        if not lock:
            lock = threading.Lock()
            _ICON_LOCKS[d] = lock
        return lock


def save_icon(
    icon_url: str,
    domain: str,
    config,
    is_fallback: bool = False,
    force_refresh: bool = False,
) -> Optional[str]:
    def _get_icon_meta_path(d: str) -> str:
        return str(
            icon_path_service.get_user_icons_dir()
            / f"web_{d.replace('.', '_')}.meta.json"
        )

    def _read_icon_meta(d: str) -> dict:
        try:
            p = _get_icon_meta_path(d)
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    import json as _json

                    return _json.load(f)
        except Exception as e:
            logger.debug(f"Icon meta read failed for {d}: {e}")
        return {}

    def _write_icon_meta(d: str, meta: dict):
        try:
            p = _get_icon_meta_path(d)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Icon meta write failed for {d}: {e}")

    meta = _read_icon_meta(domain)
    cond_headers = {
        "If-None-Match": None if force_refresh else meta.get("etag"),
        "If-Modified-Since": None if force_refresh else meta.get("last_modified"),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": f"https://{domain}/",
    }

    # Prefer injected test client from config, otherwise fallback to requests.get
    local_http_get = getattr(config, "HTTP_GET", None) or (
        lambda u, headers, timeout: requests.get(u, headers=headers, timeout=timeout)
    )

    # HEAD first
    head_response = http_request(
        icon_url,
        config,
        extra_headers=cond_headers,
        allow_non_2xx=True,
        timeout_override=(5, 8),
        retries=1,
        http_get=local_http_get,
        method="HEAD",
    )
    if not head_response:
        logger.info(f"[icon] head_request_failed, will try GET fallback url={icon_url}")
    else:
        if getattr(head_response, "status_code", 0) == 304 and not force_refresh:
            logger.info(f"[conditional] 304 Not Modified for {icon_url}")
            icon_filename = f"web_{domain.replace('.', '_')}.png"
            path = str(icon_path_service.get_user_icons_dir() / icon_filename)
            if os.path.exists(path):
                meta = _read_icon_meta(domain)
                meta["saved_at"] = time.time()
                _write_icon_meta(domain, meta)
                return path
        elif getattr(head_response, "status_code", 200) != 200:
            if head_response.status_code in (401, 403, 405):
                logger.info(
                    f"[icon] head_status={head_response.status_code}, trying GET fallback url={icon_url}"
                )
            else:
                logger.info(
                    f"[icon] skip reason=head_bad_status status={head_response.status_code} url={icon_url}"
                )
                return None
        else:
            ct = (
                (head_response.headers.get("Content-Type") or "")
                .split(";")[0]
                .strip()
                .lower()
            )
            if not ct.startswith("image/"):
                lower = icon_url.lower().split("?")[0].split("#")[0]
                img_ext = (
                    lower.endswith(".png")
                    or lower.endswith(".ico")
                    or lower.endswith(".jpg")
                    or lower.endswith(".jpeg")
                    or lower.endswith(".webp")
                    or lower.endswith(".gif")
                    or lower.endswith(".bmp")
                    or lower.endswith(".svg")
                )
                if img_ext:
                    logger.info(
                        f"[icon] non_image_head ct={ct}, but URL suggests image; trying GET {icon_url}"
                    )
                else:
                    logger.info(
                        f"[icon] skip reason=non_image_head ct={ct} url={icon_url}"
                    )
                    return None
            head_limit = max(app_config.get_max_web_icon_size() * 2, 5 * 1024 * 1024)
            if "Content-Length" in head_response.headers:
                try:
                    cl_val = int(head_response.headers["Content-Length"])
                except Exception:
                    cl_val = -1
                if cl_val > 0 and cl_val > head_limit:
                    logger.info(
                        f"[icon] skip reason=head_content_length_excess len={cl_val} head_limit={head_limit} url={icon_url}"
                    )
                    return None

    # GET
    response = http_request(
        icon_url,
        config,
        extra_headers=cond_headers,
        allow_non_2xx=True,
        timeout_override=(5, 8),
        retries=1,
        http_get=local_http_get,
        method="GET",
    )
    if not response:
        logger.info(f"[icon] skip reason=request_failed url={icon_url}")
        return None
    if getattr(response, "status_code", 0) >= 400:
        logger.info(
            f"[icon] skip reason=bad_status status={response.status_code} url={icon_url}"
        )
        return None

    ct_dbg = response.headers.get("Content-Type")
    cl_dbg = response.headers.get("Content-Length")
    logger.debug(
        f"Icon response {icon_url}: status={response.status_code} ct={ct_dbg} len={cl_dbg}"
    )
    data = response.content
    ct = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    url_lower = icon_url.lower().split("?")[0].split("#")[0]
    ext = url_lower.rsplit(".", 1)[-1] if "." in url_lower else ""

    if (
        ct.startswith("text/")
        or "html" in ct
        or ct in {"application/json", "application/xml"}
    ):
        head = data[:256].lstrip()
        if (
            head.startswith(b"<!DOCTYPE")
            or head.startswith(b"<html")
            or b"<html" in head.lower()
        ):
            logger.info(f"[icon] skip reason=non_image ct={ct} url={icon_url}")
            return None

    if len(data) > app_config.get_max_web_icon_size():
        logger.info(
            f"[icon] skip reason=body_too_large size={len(data)} url={icon_url}"
        )
        return None

    if "image/svg" in ct or ext == "svg" or b"<svg" in data[:200].lower():
        logger.debug(f"SVG detected {icon_url}")
        data = convert_svg(data)
        if not data:
            return None

    path = os.path.join(
        str(icon_path_service.get_user_icons_dir()),
        f"web_{domain.replace('.', '_')}.png",
    )
    try:
        img = Image.open(BytesIO(data))
        try:
            n_frames = getattr(img, "n_frames", 1)
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
        img = best_img
        width, height = img.size

        if width < MIN_GOOD_SIZE or height < MIN_GOOD_SIZE:
            logger.info(
                f"[icon] skip reason=too_small size={width}x{height} url={icon_url}"
            )
            return None

        aspect_ratio = max(width, height) / min(width, height)
        if aspect_ratio > 2.0:
            logger.info(
                f"[icon] skip reason=bad_aspect size={width}x{height} ratio={aspect_ratio:.2f} url={icon_url}"
            )
            return None

        lock = _get_icon_lock(domain)
        with lock:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(path, format="PNG")
            try:
                meta_update = {
                    "etag": response.headers.get("ETag") or meta.get("etag"),
                    "last_modified": response.headers.get("Last-Modified")
                    or meta.get("last_modified"),
                    "saved_at": time.time(),
                    "source_url": icon_url,
                    "content_hash": hashlib.sha256(data).hexdigest(),
                    "width": width,
                    "height": height,
                    "fallback": bool(is_fallback),
                }
                _write_icon_meta(domain, meta_update)
            except Exception as me:
                logger.debug(f"Icon meta update failed for {domain}: {me}")
        etag = response.headers.get("ETag")
        lm = response.headers.get("Last-Modified")
        logger.info(
            f"[icon] saved path={path} size={width}x{height} url={icon_url} status={response.status_code} ct={ct_dbg} len={cl_dbg} etag={etag} lm={lm}"
        )
        return path
    except Exception as e:
        logger.error(f"Save icon error {icon_url}: {e}")
        return None


def pick_icon_parallel(
    soup: "BeautifulSoup",
    page_url: str,
    domain: str,
    config,
    force_refresh: bool = False,
) -> Optional[str]:
    candidates = find_favicon_candidates(soup, page_url, config)[:10]
    logger.debug(f"Trying {len(candidates)} favicon candidates for {domain}")

    import itertools

    max_elapsed = float(getattr(config, "ICON_PICK_MAX_SECONDS", 6.0))
    finish_by = time.monotonic() + max(1.0, max_elapsed)
    batch_size = 3

    def _try_candidates_parallel(icon_urls, is_fallback: bool) -> Optional[str]:
        if not icon_urls:
            return None
        it = iter(icon_urls)
        while True:
            if time.monotonic() > finish_by:
                logger.info(
                    f"[limit] Icon pick exceeded max_elapsed_seconds for {domain}"
                )
                return None
            batch = list(itertools.islice(it, batch_size))
            if not batch:
                return None
            max_workers = min(len(batch), 3)
            logger.debug(
                f"Parallel fetch batch (workers={max_workers}, size={len(batch)}, fallback={is_fallback}) for {domain}"
            )
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {
                    executor.submit(
                        save_icon, u, domain, config, is_fallback, force_refresh
                    ): u
                    for u in batch
                }
                for fut in as_completed(future_map):
                    try:
                        saved = fut.result()
                    except Exception as e:
                        logger.debug(f"Parallel fetch error for {future_map[fut]}: {e}")
                        continue
                    if saved:
                        return saved
        return None

    saved_path = _try_candidates_parallel(candidates, is_fallback=False)
    if saved_path:
        logger.info(
            f"Successfully saved good-sized icon {saved_path} for domain {domain}"
        )
        return saved_path
    logger.debug(
        f"No icons ≥{MIN_GOOD_SIZE}px found, trying fallback mode for {domain}"
    )
    saved_path = _try_candidates_parallel(candidates, is_fallback=True)
    if saved_path:
        logger.info(
            f"Successfully saved fallback icon {saved_path} for domain {domain}"
        )
        return saved_path
    logger.warning(
        f"No valid favicon found for domain {domain} after trying all {len(candidates)} candidates"
    )
    return None


__all__ = ["pick_icon_parallel", "save_icon"]
