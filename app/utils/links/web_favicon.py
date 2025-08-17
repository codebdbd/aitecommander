# Standard library imports
import html
import json
import logging
import os
import shelve
import time
import random
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from io import BytesIO
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urljoin, urlparse

# Third-party imports
import requests
from bs4 import BeautifulSoup
from PIL import Image

# PyQt6 imports
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from requests.exceptions import RequestException

# App imports
from app.utils.ui.icon.path_service import icon_path_service

# Initialize logger at the top level
logger = logging.getLogger("favicon_parser")
logger.setLevel(logging.DEBUG)

# Warn if cloudscraper is unavailable
try:
    import cloudscraper
except ImportError:
    cloudscraper = None
    logger.warning("cloudscraper not installed, some sites may fail to fetch")

try:
    import lxml
    BS_PARSER = "lxml"
except ImportError:
    lxml = None
    BS_PARSER = "html.parser"
    logger.debug("lxml not found, using html.parser. For better performance, install lxml.")

# --- Constants ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 3  # Reduced to 3 for speed
CACHE_TTL = 7 * 24 * 3600
SHORT_NEGATIVE_TTL = 3600  # 1 hour for negative cache (timeouts, 5xx)
MEDIUM_NEGATIVE_TTL = 4 * 3600  # 4 hours for 4xx
ICON_FILE_TTL = 3 * 24 * 3600  # 3 days for icon file refresh
DEFAULT_JITTER_PCT = 0.15
MIN_GOOD_SIZE = 16
TARGET_SIZE = 64
FORMAT_RANK = {
    "ico": 0,
    "png": 1,
    "webp": 2,
    "gif": 3,
    "jpg": 4,
    "jpeg": 4,
    "bmp": 5,
    "svg": 9,  # SVG last
    "unknown": 6,
}

# --- TTL helpers ---
def _cfg_ttl(config, key: str, default_val: int) -> int:
    try:
        v = getattr(config, key, default_val)
        return int(v)
    except Exception:
        return default_val

def _apply_jitter(ttl: int, config) -> int:
    try:
        pct = float(getattr(config, 'CACHE_JITTER_PCT', DEFAULT_JITTER_PCT))
    except Exception:
        pct = DEFAULT_JITTER_PCT
    if pct <= 0:
        return ttl
    delta = ttl * pct
    return max(1, int(ttl + random.uniform(-delta, delta)))

from app.config_data import app_config

# --- Global Session ---
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# --- Per-domain icon save locks to avoid duplicate concurrent writes ---
_ICON_LOCKS: Dict[str, threading.Lock] = {}
_ICON_LOCKS_GUARD = threading.Lock()

def _get_icon_lock(domain: str) -> threading.Lock:
    d = domain or ""
    with _ICON_LOCKS_GUARD:
        lock = _ICON_LOCKS.get(d)
        if not lock:
            lock = threading.Lock()
            _ICON_LOCKS[d] = lock
        return lock

# --- HTTP request ---
def _http_request(
    url: str,
    config,
    extra_headers: Optional[Dict[str, str]] = None,
    allow_non_2xx: bool = False,
    timeout_override: Optional[object] = None,
    retries: int = 1,
    http_get=None,
) -> Optional[requests.Response]:
    headers = {"User-Agent": getattr(config, 'USER_AGENT', USER_AGENT)}
    if extra_headers:
        headers.update({k: v for k, v in extra_headers.items() if v})
    base_timeout = getattr(config, 'TIMEOUT', TIMEOUT)
    timeout = timeout_override if timeout_override is not None else base_timeout

    # Retry loop with exponential backoff for transient failures/timeouts
    attempt = 0
    last_err: Optional[Exception] = None
    while attempt <= max(0, int(retries)):
        if attempt > 0:
            time.sleep(0.5 * (2 ** attempt))  # Exponential backoff
            logger.debug(f"[retry {attempt}] GET {url}")
        try:
            if http_get:
                resp = http_get(url, headers=headers, timeout=timeout)
                if resp is None:
                    raise RequestException("Injected http_get returned None")
                if allow_non_2xx:
                    return resp
                resp.raise_for_status()
                return resp
            if cloudscraper:
                try:
                    scraper = cloudscraper.create_scraper(
                        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
                    )
                    logger.debug(f"[cloudscraper] GET {url}")
                    resp = scraper.get(url, headers=headers, timeout=timeout)
                    if allow_non_2xx:
                        return resp
                    resp.raise_for_status()
                    return resp
                except Exception as e:
                    logger.warning(f"Cloudscraper failed for {url}: {e}")
                    last_err = e
            logger.debug(f"[session] GET {url}")
            resp = session.get(url, headers=headers, timeout=timeout)
            if allow_non_2xx:
                return resp
            resp.raise_for_status()
            return resp
        except RequestException as e:
            last_err = e
            err_s = str(e)
            if "Read timed out" in err_s or "ConnectTimeout" in err_s or "timeout" in err_s.lower():
                attempt += 1
                continue
            break
        except Exception as e:
            last_err = e
            break
    logger.warning(f"Requests failed for {url}: {last_err}")
    return None

# --- HTML decode helper ---
def _get_html(resp: requests.Response) -> str:
    """Return response body decoded with best-guess correct encoding."""
    enc = resp.encoding
    if not enc or enc.lower() == "iso-8859-1":
        enc = resp.apparent_encoding or "utf-8"
    try:
        return resp.content.decode(enc, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return resp.content.decode("utf-8", errors="replace")

# --- Favicon candidates ---
def _parse_icon_size(sizes_attr: str) -> int:
    """Extracts icon size from sizes attribute (e.g., '32x32' -> 32)."""
    if not sizes_attr:
        return 0
    import re
    match = re.search(r'(\d+)x?\d*', sizes_attr.lower())
    if not match:
        logger.debug(f"Invalid sizes attribute: {sizes_attr}")
        return 0
    return int(match.group(1))

def _find_favicon_candidates(soup: BeautifulSoup, base_url: str, config=None) -> List[str]:
    """Finds favicon candidates (including web manifest icons) and returns a list of URLs by priority."""
    def _detect_format(href: str, type_attr: str | None) -> str:
        ext = ""
        if href:
            lower = href.lower().split("?")[0].split("#")[0]
            if "." in lower:
                ext = lower.rsplit(".", 1)[-1]
        t = (type_attr or "").lower()
        if "svg" in t or ext == "svg":
            return "svg"
        if "x-icon" in t or ext == "ico":
            return "ico"
        if "png" in t or ext == "png":
            return "png"
        if "webp" in t or ext == "webp":
            return "webp"
        if "gif" in t or ext == "gif":
            return "gif"
        if "jpeg" in t or ext in ("jpg", "jpeg"):
            return "jpg"
        if ext:
            return ext
        return "unknown"

    candidates: List[dict] = []

    def _add_link_candidate(link, rel_label: str, base_priority: int):
        href = link.get("href")
        if not href or href.startswith("data:"):
            return
        sizes = link.get("sizes", "")
        size_value = _parse_icon_size(sizes)
        media = link.get("media", "")
        type_attr = link.get("type", "")
        fmt = _detect_format(href, type_attr)
        media_priority = 0 if not media or "light" in media else 1
        candidates.append({
            "url": urljoin(base_url, href),
            "size": size_value,
            "format": fmt,
            "format_rank": FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
            "base_priority": base_priority,
            "media_priority": media_priority,
            "type": rel_label,
        })

    # 0) Web Manifest (high quality PWA icons)
    try:
        # rel can be a list of tokens
        manifest_links = []
        for link in soup.find_all("link"):
            rel_val = link.get("rel")
            if not rel_val:
                continue
            tokens = [t.lower() for t in (rel_val if isinstance(rel_val, list) else str(rel_val).split())]
            if any(t == "manifest" for t in tokens):
                manifest_links.append(link)
        if manifest_links and config is not None:
            from urllib.parse import urljoin as _uj
            m_href = manifest_links[0].get("href")
            if m_href and not m_href.startswith("data:"):
                m_url = _uj(base_url, m_href)
                m_resp = _http_request(m_url, config, allow_non_2xx=True)
                if m_resp and getattr(m_resp, 'ok', False):
                    try:
                        m_json = json.loads(m_resp.text)
                        icons = m_json.get("icons") or []
                        for icon in icons:
                            src = icon.get("src")
                            if not src:
                                continue
                            i_url = _uj(m_url, src)
                            sizes = str(icon.get("sizes") or "").split()
                            type_attr = icon.get("type") or ""
                            fmt = _detect_format(i_url, type_attr)
                            # If multiple sizes listed, add each as a separate candidate
                            if sizes:
                                for sz in sizes:
                                    candidates.append({
                                        "url": i_url,
                                        "size": _parse_icon_size(sz),
                                        "format": fmt,
                                        "format_rank": FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
                                        "base_priority": 1,  # same as link-icon
                                        "media_priority": 0,
                                        "type": "manifest",
                                    })
                            else:
                                candidates.append({
                                    "url": i_url,
                                    "size": 0,
                                    "format": fmt,
                                    "format_rank": FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
                                    "base_priority": 1,
                                    "media_priority": 0,
                                    "type": "manifest",
                                })
                    except Exception:
                        pass
    except Exception:
        pass

    # 1) Main favicons — handle multiple rel values
    for link in soup.find_all("link"):
        rel_val = link.get("rel")
        if not rel_val:
            continue
        tokens = [t.lower() for t in (rel_val if isinstance(rel_val, list) else str(rel_val).split())]
        if any("icon" == t or t.endswith("icon") for t in tokens):
            if any("mask-icon" == t for t in tokens):
                _add_link_candidate(link, "mask-icon", 4)
            else:
                _add_link_candidate(link, "link-icon", 0)

    # 2) Apple touch (lower priority — often large splash icons)
    for link in soup.find_all("link", rel="apple-touch-icon"):
        _add_link_candidate(link, "apple-touch-icon", 2)
    for link in soup.find_all("link", rel="apple-touch-icon-precomposed"):
        _add_link_candidate(link, "apple-touch-icon", 2)

    # 3) Extended fallback paths and host variants (with/without www)
    p = urlparse(base_url)
    host = p.netloc
    hosts = {host}
    if host.startswith("www."):
        hosts.add(host[4:])
    else:
        hosts.add("www." + host)

    fallback_paths = [
        "/favicon.ico",
        "/favicon.png",
        "/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png",
    ]
    for h in hosts:
        base = f"{p.scheme}://{h}"
        for path in fallback_paths:
            url = urljoin(base + "/", path.lstrip("/"))
            fmt = _detect_format(url, None)
            candidates.append({
                "url": url,
                "size": 0,
                "format": fmt,
                "format_rank": FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
                "base_priority": 1,
                "media_priority": 0,
                "type": "fallback",
            })

    def sort_key(c: dict):
        size = c.get("size", 0)
        # Prefer larger sizes over closeness to TARGET_SIZE
        return (
            c.get("base_priority", 9),
            c.get("format_rank", FORMAT_RANK["unknown"]),
            -size,  # larger first
            c.get("media_priority", 0),
        )

    candidates.sort(key=sort_key)

    logger.debug(f"Found {len(candidates)} icon candidates (before og:image):")
    for cand in candidates[:5]:
        logger.debug(
            f"  {cand['type']} {cand['size']}px {cand['format']} p{cand['base_priority']}/f{cand['format_rank']}: {cand['url']}"
        )
    if candidates:
        best = candidates[0]
        logger.info(
            f"Best candidate: {best['type']} {best['size']}px {best['format']} from {best['url']}"
        )

    # 4) Use og:image only if no proper link-icon/ico found
    og_urls: List[str] = []
    if not candidates or all(c.get("base_priority", 9) > 1 for c in candidates):
        def _maybe_add_og(prop_name: str):
            meta = soup.find("meta", property=prop_name)
            if meta and meta.get("content"):
                og_content = meta.get("content") or ""
                og_url = urljoin(base_url, og_content)
                low = og_url.lower()
                banned_markers = [
                    "1200", "1080", "1024", "800", "630", "600", "banner", "social", "share", "opengraph", "og:", ".svg"
                ]
                if not any(m in low for m in banned_markers):
                    if any(k in low for k in ["icon", "favicon"]):
                        og_urls.append(og_url)
        _maybe_add_og("og:image")
        _maybe_add_og("og:image:secure_url")

    ordered_urls = [c["url"] for c in candidates] + og_urls
    # Remove duplicates while preserving order
    seen = set()
    ordered_urls = [url for url in ordered_urls if not (url in seen or seen.add(url))]
    return ordered_urls

# --- YouTube oEmbed fallback ---
def _fetch_youtube_title(url: str, config) -> Optional[str]:
    api_url = "https://www.youtube.com/oembed?" + urlencode({"url": url, "format": "json"})
    resp = _http_request(api_url, config)
    if resp and resp.ok:
        try:
            data = json.loads(resp.text)
            return data.get("title")
        except Exception:
            return None
    return None

# --- Title extractor ---
def _postprocess_title(title: str, domain: str) -> str:
    title = title.strip()
    replacements = [" - YouTube", " | YouTube", " - YouTube Music", " - YouTube Gaming"]
    for suffix in replacements:
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    if not title:
        return domain
    return title

def _extract_title(soup: BeautifulSoup, url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "")

    def _meta_content(*selectors: tuple[str, str]):
        for attr, value in selectors:
            tag = soup.find("meta", attrs={attr: value})
            if tag and tag.get("content"):
                content = (tag.get("content") or "").strip()
                if content:
                    return content
        return ""

    # 1) Prefer OpenGraph/Twitter titles over <title>
    og_twitter = _meta_content(
        ("property", "og:title"),
        ("name", "og:title"),
        ("name", "twitter:title"),
        ("property", "twitter:title"),
    )
    if og_twitter:
        return _postprocess_title(og_twitter, domain)

    # 2) Fallback to HTML <title>
    if soup.title:
        raw = soup.title.string if soup.title.string else soup.title.get_text(strip=True)
        raw = (raw or "").strip()
        if raw:
            return _postprocess_title(html.unescape(raw), domain)

    # 3) meta name="title" as another fallback
    named = _meta_content(("name", "title"))
    if named:
        return _postprocess_title(named, domain)

    # 4) h1 text
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if text:
            return _postprocess_title(text, domain)

    # 5) Domain
    return domain

# --- Title + Icon helper wrappers ---
def _get_title(url: str, config, soup: Optional[BeautifulSoup] = None) -> str:
    """Returns normalized title. Uses oEmbed for YouTube. Avoids extra HTTP request if soup provided."""
    host = urlparse(url).netloc.lower().replace("www.", "")
    if host in ("youtube.com", "youtu.be"):
        yt = _fetch_youtube_title(url, config)
        if yt:
            return _postprocess_title(yt, host)
    if soup is not None:
        return _extract_title(soup, url)
    resp = _http_request(url, config)
    if resp:
        try:
            s = BeautifulSoup(resp.text, BS_PARSER)
            return _extract_title(s, url)
        except Exception:
            pass
    return urlparse(url).netloc.replace("www.", "")

def _pick_icon_parallel(soup: BeautifulSoup, page_url: str, domain: str, config, force_refresh: bool = False) -> Optional[str]:
    """Attempts to save favicon from candidates in parallel. Returns path or None."""
    candidates = _find_favicon_candidates(soup, page_url)[:12]
    logger.debug(f"Trying {len(candidates)} favicon candidates for {domain}")

    import itertools
    max_elapsed = float(getattr(config, 'ICON_PICK_MAX_SECONDS', 8.0))
    finish_by = time.monotonic() + max(1.0, max_elapsed)
    batch_size = 2

    def _try_candidates_parallel(icon_urls, is_fallback: bool) -> Optional[str]:
        if not icon_urls:
            return None
        it = iter(icon_urls)
        while True:
            if time.monotonic() > finish_by:
                logger.info(f"[limit] Icon pick exceeded max_elapsed_seconds for {domain}")
                return None
            batch = list(itertools.islice(it, batch_size))
            if not batch:
                return None
            max_workers = min(len(batch), 2)
            logger.debug(f"Parallel fetch batch (workers={max_workers}, size={len(batch)}, fallback={is_fallback}) for {domain}")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(_save_icon, u, domain, config, is_fallback, force_refresh): u for u in batch}
                for fut in as_completed(future_map):
                    try:
                        saved = fut.result()
                    except Exception as e:
                        logger.debug(f"Parallel fetch error for {future_map[fut]}: {e}")
                        continue
                    if saved:
                        return saved
        return None  # Explicit return for no results

    saved_path = _try_candidates_parallel(candidates, is_fallback=False)
    if saved_path:
        logger.info(f"Successfully saved good-sized icon {saved_path} for domain {domain}")
        return saved_path
    logger.debug(f"No icons ≥{MIN_GOOD_SIZE}px found, trying fallback mode for {domain}")
    saved_path = _try_candidates_parallel(candidates, is_fallback=True)
    if saved_path:
        logger.info(f"Successfully saved fallback icon {saved_path} for domain {domain}")
        return saved_path
    logger.warning(f"No valid favicon found for domain {domain} after trying all {len(candidates)} candidates")
    return None

# --- Cache ---
def _get_cache_path(config) -> str:
    return str(icon_path_service.get_user_icons_dir() / "favicon_cache.db")

def _read_cache(url: str, config) -> Optional[Dict[str, Any]]:
    path = _get_cache_path(config)
    with closing(shelve.open(path)) as db:
        item = db.get(url)
        if not item:
            return None
        default_icon = config.get_default_icons().get("web", "")
        if "ttl" not in item and item.get("icon") == default_icon:
            ttl = SHORT_NEGATIVE_TTL
        else:
            ttl = item.get("ttl", CACHE_TTL)
        if time.time() - item.get("timestamp", 0) < ttl:
            logger.debug(f"[cache] HIT {url}")
            return item
    return None

def _write_cache(url: str, data: Dict[str, Any], config):
    path = _get_cache_path(config)
    with closing(shelve.open(path, writeback=True)) as db:
        db[url] = data
        logger.debug(f"[cache] SAVE {url}")

# --- SVG conversion ---
def _convert_svg(svg_data: bytes) -> Optional[bytes]:
    renderer = QSvgRenderer(QByteArray(svg_data))
    if not renderer.isValid():
        logger.warning("Invalid SVG")
        return None

    image = QImage(QSize(64, 64), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter()
    try:
        painter.begin(image)
        try:
            renderer.render(painter)
        finally:
            painter.end()
    except Exception as e:
        logger.error(f"SVG render error: {e}")
        return None

    buffer = QBuffer()
    try:
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if image.save(buffer, "PNG"):
            return bytes(buffer.data())
    finally:
        buffer.close()
    return None

# --- Save icon ---
def _save_icon(icon_url: str, domain: str, config, is_fallback: bool = False, force_refresh: bool = False) -> Optional[str]:
    def _get_icon_meta_path(d: str) -> str:
        return str(icon_path_service.get_user_icons_dir() / f"web_{d.replace('.', '_')}.meta.json")

    def _read_icon_meta(d: str) -> Dict[str, Any]:
        try:
            p = _get_icon_meta_path(d)
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Icon meta read failed for {d}: {e}")
        return {}

    def _write_icon_meta(d: str, meta: Dict[str, Any]):
        try:
            p = _get_icon_meta_path(d)
            with open(p, 'w', encoding='utf-8') as f:
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
    # Use per-request HTTP client here to avoid shared session in parallel threads
    # Prefer injected test client from config, otherwise fallback to requests.get
    local_http_get = getattr(config, 'HTTP_GET', None) or (lambda u, headers, timeout: requests.get(u, headers=headers, timeout=timeout))
    response = _http_request(
        icon_url,
        config,
        extra_headers=cond_headers,
        allow_non_2xx=True,
        timeout_override=(5, 8),
        retries=1,
        http_get=local_http_get,
    )
    if not response:
        logger.info(f"[icon] skip reason=request_failed url={icon_url}")
        return None

    if response.status_code == 304 and not force_refresh:
        logger.info(f"[conditional] 304 Not Modified for {icon_url}")
        icon_filename = f"web_{domain.replace('.', '_')}.png"
        path = str(icon_path_service.get_user_icons_dir() / icon_filename)
        if os.path.exists(path):
            try:
                os.utime(path, None)
            except Exception:
                pass
            meta["saved_at"] = time.time()
            _write_icon_meta(domain, meta)
            return path
        return None

    if response.status_code >= 400:
        logger.info(f"[icon] skip reason=bad_status status={response.status_code} url={icon_url}")
        return None

    if 'Content-Length' in response.headers:
        try:
            cl_val = int(response.headers['Content-Length'])
        except Exception:
            cl_val = -1
        head_limit = max(app_config.get_max_web_icon_size() * 2, 5 * 1024 * 1024)
        if cl_val > 0 and cl_val > head_limit:
            logger.info(f"[icon] skip reason=head_content_length_excess len={cl_val} head_limit={head_limit} url={icon_url}")
            return None

    ct_dbg = response.headers.get('Content-Type')
    cl_dbg = response.headers.get('Content-Length')
    logger.debug(f"Icon response {icon_url}: status={response.status_code} ct={ct_dbg} len={cl_dbg}")
    data = response.content
    ct = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
    url_lower = icon_url.lower().split('?')[0].split('#')[0]
    ext = url_lower.rsplit('.', 1)[-1] if '.' in url_lower else ''

    if ct.startswith('text/') or 'html' in ct or ct in {'application/json', 'application/xml'}:
        head = data[:256].lstrip()
        if head.startswith(b'<!DOCTYPE') or head.startswith(b'<html') or b'<html' in head.lower():
            logger.info(f"[icon] skip reason=non_image ct={ct} url={icon_url}")
            return None

    if len(data) > app_config.get_max_web_icon_size():
        logger.info(f"[icon] skip reason=body_too_large size={len(data)} url={icon_url}")
        return None

    if 'image/svg' in ct or ext == 'svg' or b"<svg" in data[:200].lower():
        logger.debug(f"SVG detected {icon_url}")
        data = _convert_svg(data)
        if not data:
            return None

    path = os.path.join(str(icon_path_service.get_user_icons_dir()), f"web_{domain.replace('.', '_')}.png")
    try:
        img = Image.open(BytesIO(data))
        # If ICO or multi-frame image, pick the best frame by size/quality
        try:
            n_frames = getattr(img, "n_frames", 1)
        except Exception:
            n_frames = 1
        best_img = img
        best_score = None
        MIN_PREFERRED_SIZE = 16
        if (getattr(img, "format", "").upper() == "ICO") or n_frames > 1:
            try:
                for i in range(max(1, n_frames)):
                    try:
                        img.seek(i)
                    except Exception:
                        # Some formats do not support seek well; break out after the first frame
                        if i == 0:
                            pass
                        else:
                            break
                    w, h = img.size
                    # Score: prefer the largest available frame, regardless of TARGET_SIZE
                    score = (-max(w, h),)
                    if (best_score is None) or (score < best_score):
                        best_score = score
                        best_img = img.copy()
            except Exception:
                # Fallback to first frame already loaded
                best_img = img
        img = best_img
        width, height = img.size

        # No resizing: save icons in original dimensions

        if width < 16 or height < 16:
            logger.info(f"[icon] skip reason=too_small size={width}x{height} url={icon_url}")
            return None

        aspect_ratio = max(width, height) / min(width, height)
        if aspect_ratio > 2.0:
            logger.info(f"[icon] skip reason=bad_aspect size={width}x{height} ratio={aspect_ratio:.2f} url={icon_url}")
            return None

        # Do not enforce preferred-size threshold; accept originals (>= absolute min handled above)

        # Serialize save per-domain to avoid concurrent double writes from parallel tasks
        lock = _get_icon_lock(domain)
        with lock:
            # Re-read meta to see if another thread saved recently
            latest_meta = _read_icon_meta(domain)
            recent_saved_at = latest_meta.get("saved_at") if isinstance(latest_meta, dict) else None
            if not force_refresh and isinstance(recent_saved_at, (int, float)) and (time.time() - recent_saved_at) < 5:
                # Another thread just saved the icon; return existing path
                if os.path.exists(path):
                    logger.debug(f"[icon] skip reason=recently_saved path={path} domain={domain}")
                    return path
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(path, format="PNG")
            try:
                meta_update = {
                    "etag": response.headers.get('ETag') or meta.get('etag'),
                    "last_modified": response.headers.get('Last-Modified') or meta.get('last_modified'),
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
        etag = response.headers.get('ETag')
        lm = response.headers.get('Last-Modified')
        logger.info(f"[icon] saved path={path} size={width}x{height} url={icon_url} status={response.status_code} ct={ct_dbg} len={cl_dbg} etag={etag} lm={lm}")
        return path
    except Exception as e:
        logger.error(f"Save icon error {icon_url}: {e}")
        return None

# --- Main function ---
def fetch_web_link_info(url: str, config, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetches web link info: title and icon.
    Uses multi-level caching:
    1. Cache by full URL (title and icon path).
    2. Icon cache by domain (physical files on disk).
    """
    raw_input = url or ""
    url = raw_input.strip().splitlines()[0] if raw_input else ""
    url = url.split()[0] if url else ""
    url = url.strip('"\'') if url else ""
    if len(url) > 512:
        logger.warning(f"Input URL too long ({len(url)}), trimming to 512 chars")
        url = url[:512]

    # Unwrap view-source: prefix if present (e.g., 'view-source:https://example.com')
    if url and url.lower().startswith("view-source:"):
        # remove all leading 'view-source:' wrappers
        while url.lower().startswith("view-source:"):
            url = url[len("view-source:"):].lstrip()

    def _looks_like_domain(token: str) -> bool:
        if not token:
            return False
        import re
        if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", token):
            return False
        if re.match(r"^\d+\s*-\s*", token):
            return False
        if " " in token:
            return False
        # Reject if token looks like it already has a scheme or other colon-based prefix
        if ":" in token:
            return False
        # Reject if token contains slashes (path), we only want bare hosts here
        if "/" in token:
            return False
        if re.match(r"^(\d{1,3}\.){3}\d{1,3}$", token):
            return True
        return "." in token

    if url and not url.startswith("http") and _looks_like_domain(url):
        url = "https://" + url

    parsed = urlparse(url) if url else None
    netloc = parsed.netloc if parsed else ""
    if not netloc and parsed and parsed.path:
        netloc = parsed.path

    if not netloc or not _looks_like_domain(netloc):
        logger.warning(f"Invalid URL input for favicon fetch, returning defaults. raw='{raw_input[:120]}' sanitized='{url}'")
        fallback_domain = (netloc or (url or "")).replace("www.", "")
        result = {
            "name": fallback_domain or "",
            "icon": config.get_default_icons().get("web", ""),
            "timestamp": time.time(),
            "ttl": SHORT_NEGATIVE_TTL,
        }
        _write_cache(url or (raw_input or ""), result, config)
        return result

    cached = None if force_refresh else _read_cache(url, config)
    domain = urlparse(url).netloc.replace("www.", "")
    if cached and cached.get('name') and cached['name'] != domain:
        if cached.get('icon') and os.path.exists(cached['icon']):
            return cached
        logger.debug(f"[cache] Stale icon path for {url}, refetching.")
    elif cached:
        logger.debug(f"[cache] Missing title in cached record for {url}, refetching.")

    domain = urlparse(url).netloc.replace("www.", "")
    result = {
        "name": domain,
        "icon": config.get_default_icons().get("web", ""),
        "timestamp": time.time()
    }

    icon_filename = f"web_{domain.replace('.', '_')}.png"
    icon_path = str(icon_path_service.get_user_icons_dir() / icon_filename)

    if os.path.exists(icon_path):
        try:
            mtime = os.path.getmtime(icon_path)
        except OSError:
            mtime = 0
        age = time.time() - mtime
        icon_file_ttl = _cfg_ttl(config, 'ICON_FILE_TTL', ICON_FILE_TTL)
        if age <= icon_file_ttl and not force_refresh:
            logger.debug(f"Found existing fresh icon for domain {domain}. Fetching title only.")
            result["icon"] = icon_path
            result["name"] = _get_title(url, config)
            result["timestamp"] = time.time()
            result["ttl"] = _apply_jitter(_cfg_ttl(config, 'CACHE_TTL', CACHE_TTL), config)
            _write_cache(url, result, config)
            return result
        else:
            logger.debug(f"Existing icon for {domain} is stale (age={int(age)}s). Will attempt refresh.")
            resp = _http_request(url, config)
            if not resp:
                result["icon"] = icon_path
                result["name"] = _get_title(url, config)
                result["timestamp"] = time.time()
                result["ttl"] = _apply_jitter(_cfg_ttl(config, 'SHORT_NEGATIVE_TTL', SHORT_NEGATIVE_TTL), config)
                _write_cache(url, result, config)
                return result
            try:
                soup = BeautifulSoup(resp.text, BS_PARSER)
                result["name"] = _get_title(url, config, soup)
                saved_path = _pick_icon_parallel(soup, url, domain, config, force_refresh=force_refresh)
                result["icon"] = saved_path or icon_path
                result["timestamp"] = time.time()
                default_icon = config.get_default_icons().get("web", "")
                is_updated = bool(saved_path) and os.path.exists(saved_path) and saved_path != default_icon
                base_ttl = _cfg_ttl(config, 'CACHE_TTL', CACHE_TTL) if is_updated else _cfg_ttl(config, 'SHORT_NEGATIVE_TTL', SHORT_NEGATIVE_TTL)
                result["ttl"] = _apply_jitter(base_ttl, config)
                _write_cache(url, result, config)
                return result
            except Exception as e:
                logger.error(f"Refresh attempt failed for {url}: {e}")
                result["icon"] = icon_path
                result["name"] = _get_title(url, config)
                result["timestamp"] = time.time()
                result["ttl"] = _apply_jitter(_cfg_ttl(config, 'SHORT_NEGATIVE_TTL', SHORT_NEGATIVE_TTL), config)
                _write_cache(url, result, config)
                return result

    logger.debug(f"No icon for domain {domain}, starting full fetch.")
    resp = _http_request(url, config)
    if not resp:
        result["name"] = _get_title(url, config)
        result["timestamp"] = time.time()
        result["ttl"] = _apply_jitter(_cfg_ttl(config, 'SHORT_NEGATIVE_TTL', SHORT_NEGATIVE_TTL), config)
        _write_cache(url, result, config)
        return result

    try:
        status = int(getattr(resp, 'status_code', 0))
    except Exception:
        status = 0
    if status >= 500:
        result["name"] = _get_title(url, config)
        result["timestamp"] = time.time()
        result["ttl"] = _apply_jitter(_cfg_ttl(config, 'SHORT_NEGATIVE_TTL', SHORT_NEGATIVE_TTL), config)
        _write_cache(url, result, config)
        return result
    if 400 <= status < 500:
        result["name"] = _get_title(url, config)
        result["timestamp"] = time.time()
        result["ttl"] = _apply_jitter(_cfg_ttl(config, 'MEDIUM_NEGATIVE_TTL', MEDIUM_NEGATIVE_TTL), config)
        _write_cache(url, result, config)
        return result

    try:
        soup = BeautifulSoup(resp.text, BS_PARSER)
        result["name"] = _get_title(url, config, soup)
        saved_path = _pick_icon_parallel(soup, url, domain, config, force_refresh=force_refresh)
        if saved_path:
            result["icon"] = saved_path
    except Exception as e:
        logger.error(f"Full parse error for {url}: {e}")

    result["timestamp"] = time.time()
    default_icon = config.get_default_icons().get("web", "")
    is_ok = result.get("icon") and result["icon"] != default_icon
    base_ttl = _cfg_ttl(config, 'CACHE_TTL', CACHE_TTL) if is_ok else _cfg_ttl(config, 'SHORT_NEGATIVE_TTL', SHORT_NEGATIVE_TTL)
    result["ttl"] = _apply_jitter(base_ttl, config)
    _write_cache(url, result, config)
    return result