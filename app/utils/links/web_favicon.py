# Standard library imports
import html
import json
import logging
import os
import shelve
import time
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

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

try:
    import lxml
    BS_PARSER = "lxml"
except ImportError:
    lxml = None
    BS_PARSER = "html.parser"
    logger.debug("lxml not found, using html.parser. For better performance, install lxml.")

# --- Константы ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 3  # Уменьшил до 3 для ускорения
CACHE_TTL = 7 * 24 * 3600

from app.config_data import app_config

# --- Глобальный Session ---
session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

# --- HTTP запрос ---
def _http_request(url: str, config) -> Optional[requests.Response]:
    headers = {"User-Agent": getattr(config, 'USER_AGENT', USER_AGENT)}
    timeout = getattr(config, 'TIMEOUT', TIMEOUT)

    if cloudscraper:
        try:
            scraper = cloudscraper.create_scraper(
                browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
            )
            logger.debug(f"[cloudscraper] GET {url}")
            resp = scraper.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            logger.warning(f"Cloudscraper failed for {url}: {e}")

    try:
        logger.debug(f"[session] GET {url}")
        resp = session.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp
    except RequestException as e:
        logger.warning(f"Requests failed for {url}: {e}")
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
    """Извлекает размер иконки из атрибута sizes (например, '32x32' -> 32)."""
    if not sizes_attr:
        return 0
    
    # Ищем паттерн NxN или просто N
    import re
    match = re.search(r'(\d+)x?\d*', sizes_attr.lower())
    if match:
        return int(match.group(1))
    return 0

def _find_favicon_candidates(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Находит кандидатов на фавикон в порядке приоритета с учетом размеров."""
    MIN_PREFERRED_SIZE = 48  # Минимальный предпочтительный размер
    
    # Собираем все иконки с информацией о размерах
    icon_candidates = []
    
    # 1. Специфичные фавиконы (высший приоритет)
    for rel in ["icon", "shortcut icon"]:
        for link in soup.find_all("link", rel=rel):
            href = link.get("href")
            if href and not href.startswith("data:"):
                sizes = link.get("sizes", "")
                size_value = _parse_icon_size(sizes)
                media = link.get("media", "")
                
                # Предпочитаем light theme или без media query
                media_priority = 0 if not media or "light" in media else 1
                
                icon_candidates.append({
                    'url': urljoin(base_url, href),
                    'size': size_value,
                    'priority': 1,  # Высший приоритет
                    'media_priority': media_priority,
                    'type': 'icon'
                })
    
    # 2. Apple touch иконки (средний приоритет)
    for link in soup.find_all("link", rel="apple-touch-icon"):
        href = link.get("href")
        if href and not href.startswith("data:"):
            sizes = link.get("sizes", "")
            size_value = _parse_icon_size(sizes)
            
            icon_candidates.append({
                'url': urljoin(base_url, href),
                'size': size_value,
                'priority': 2,  # Средний приоритет
                'media_priority': 0,
                'type': 'apple-touch-icon'
            })
    
    # Сортируем кандидатов по приоритету и размеру
    def sort_key(candidate):
        size = candidate['size']
        priority = candidate['priority']
        media_priority = candidate['media_priority']
        
        # Для больших иконок (≥48px): предпочитаем размеры 64-128px
        if size >= MIN_PREFERRED_SIZE:
            # Идеальный диапазон 64-128px, штраф за отклонение
            if 64 <= size <= 128:
                size_score = -size  # Чем больше в идеальном диапазоне, тем лучше
            elif size < 64:
                size_score = -(size - 10)  # Небольшой штраф за размер меньше 64
            else:  # size > 128
                size_score = -(256 - size)  # Штраф растет с увеличением размера
            size_penalty = 0
        else:
            # Для маленьких иконок: чем больше, тем лучше
            size_score = -size  # Отрицательное значение для правильной сортировки
            size_penalty = 1000  # Большой штраф за маленький размер
        
        return (priority, media_priority, size_penalty, size_score)
    
    # Сортируем и извлекаем URL
    icon_candidates.sort(key=sort_key)
    priority_urls = [candidate['url'] for candidate in icon_candidates]
    
    logger.debug(f"Found {len(icon_candidates)} sized icons:")
    for candidate in icon_candidates[:5]:  # Показываем топ-5
        media_info = f" ({candidate.get('media_priority', 0)})" if 'media_priority' in candidate else ""
        logger.debug(f"  {candidate['type']} {candidate['size']}px{media_info}: {candidate['url']}")
    
    if len(icon_candidates) > 0:
        best = icon_candidates[0]
        logger.info(f"Best candidate: {best['type']} {best['size']}px from {best['url']}")
    
    # 3. Стандартный фавикон как fallback
    fallback_urls = [urljoin(base_url, "/favicon.ico")]
    
    # 4. og:image только как последний резерв (низший приоритет)
    og_urls = []
    meta = soup.find("meta", property="og:image")
    if meta and meta.get("content"):
        og_content = meta.get("content")
        # Фильтруем слишком большие изображения по URL
        if not any(size in og_content.lower() for size in ['1200', '800', '600', 'large', 'banner']):
            og_urls.append(urljoin(base_url, og_content))

    # Объединяем в порядке приоритета
    all_urls = priority_urls + fallback_urls + og_urls
    
    # Приоритет форматов: PNG/JPG/ICO → SVG в конец
    pngs = [u for u in all_urls if not u.lower().endswith(".svg")]
    svgs = [u for u in all_urls if u.lower().endswith(".svg")]
    combined = pngs + svgs
    
    return list(dict.fromkeys(combined))


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
    # Чистим типичные суффиксы
    replacements = [" - YouTube", " | YouTube", " - YouTube Music", " - YouTube Gaming"]
    for suffix in replacements:
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    if not title:
        return domain
    return title


def _extract_title(soup: BeautifulSoup, url: str) -> str:
    if soup.title:
        raw = soup.title.string if soup.title.string else soup.title.get_text(strip=True)
        raw = (raw or "").strip()
        if raw:
            return _postprocess_title(html.unescape(raw), urlparse(url).netloc.replace("www.", ""))
    # OpenGraph title
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        return _postprocess_title(og["content"].strip(), urlparse(url).netloc.replace("www.", ""))
    # Fallback to <meta name="title"> or <meta name="og:title"> variants
    if not og:
        og = soup.find("meta", attrs={"name": "title"})
    if not og:
        og = soup.find("meta", attrs={"name": "og:title"})

    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if text:
            return _postprocess_title(text, urlparse(url).netloc.replace("www.", ""))
    return urlparse(url).netloc.replace("www.", "")

# --- Кэш ---
def _get_cache_path(config) -> str:
    return str(icon_path_service.get_user_icons_dir() / "favicon_cache.db")

def _read_cache(url: str, config) -> Optional[Dict[str, Any]]:
    path = _get_cache_path(config)
    with closing(shelve.open(path)) as db:
        item = db.get(url)
        if item and (time.time() - item.get("timestamp", 0) < CACHE_TTL):
            logger.debug(f"[cache] HIT {url}")
            return item
    return None

def _write_cache(url: str, data: Dict[str, Any], config):
    path = _get_cache_path(config)
    with closing(shelve.open(path, writeback=True)) as db:
        db[url] = data
        logger.debug(f"[cache] SAVE {url}")

# --- SVG конвертация ---
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
        renderer.render(painter)
        painter.end()
    except Exception as e:
        logger.error(f"SVG render error: {e}")
        return None

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if image.save(buffer, "PNG"):
        return bytes(buffer.data())
    return None

# --- Сохранение иконки ---
def _save_icon(icon_url: str, domain: str, config, is_fallback: bool = False) -> Optional[str]:
    response = _http_request(icon_url, config)
    if not response:
        return None

    if 'Content-Length' in response.headers:
        from app.config_data import app_config
        if int(response.headers['Content-Length']) > app_config.get_max_web_icon_size():
            logger.debug(f"[skip] Large icon: {icon_url}")
            return None

    data = response.content
    from app.config_data import app_config
    if len(data) > app_config.get_max_web_icon_size():
        logger.debug(f"[skip] Too big after download: {icon_url}")
        return None

    if b"<svg" in data[:200] or icon_url.lower().endswith(".svg"):
        logger.debug(f"SVG detected {icon_url}")
        data = _convert_svg(data)
        if not data:
            return None

    from app.utils.ui.icon.path_service import icon_path_service
    path = os.path.join(str(icon_path_service.get_user_icons_dir()), f"web_{domain.replace('.', '_')}.png")
    try:
        img = Image.open(BytesIO(data))
        
        # Проверяем качество иконки
        width, height = img.size
        MIN_PREFERRED_SIZE = 48  # Минимальный предпочтительный размер
        
        # Фильтруем слишком большие изображения (вероятно не фавиконы)
        if width > 512 or height > 512:
            logger.debug(f"[skip] Too large for favicon: {width}x{height} from {icon_url}")
            return None
            
        # Фильтруем слишком маленькие изображения (битые/placeholder)
        if width < 16 or height < 16:
            logger.debug(f"[skip] Too small for favicon: {width}x{height} from {icon_url}")
            return None
            
        # Проверяем соотношение сторон (фавиконы обычно квадратные или близко к квадратным)
        aspect_ratio = max(width, height) / min(width, height)
        if aspect_ratio > 2.0:
            logger.debug(f"[skip] Bad aspect ratio: {width}x{height} (ratio: {aspect_ratio:.2f}) from {icon_url}")
            return None
        
        # Проверяем минимальный предпочтительный размер
        if width < MIN_PREFERRED_SIZE or height < MIN_PREFERRED_SIZE:
            if not is_fallback:
                logger.debug(f"[skip] Icon too small: {width}x{height} < {MIN_PREFERRED_SIZE}px from {icon_url}")
                return None
            else:
                logger.warning(f"[fallback] Using small icon: {width}x{height} from {icon_url}")
        else:
            logger.debug(f"[good] Icon size {width}x{height} meets minimum requirements from {icon_url}")
        
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        img.save(path, format="PNG")
        logger.info(f"[save] {path} ({width}x{height})")
        return path
    except Exception as e:
        logger.error(f"Save icon error {icon_url}: {e}")
        return None

# --- Главная функция ---
def fetch_web_link_info(url: str, config) -> Dict[str, str]:
    """
    Получает информацию о веб-ссылке: заголовок и иконку.
    Использует многоуровневое кэширование:
    1. Кэш по полному URL (включая заголовок и путь к иконке).
    2. Кэш иконок по домену (физические файлы на диске).
    """
    # --- Sanitize and validate incoming URL to avoid fetching for invalid inputs (e.g., pasted logs) ---
    raw_input = url or ""
    # 1) Trim and keep only the first line and first token
    url = raw_input.strip().splitlines()[0] if raw_input else ""
    url = url.split()[0] if url else ""
    # 2) Strip wrapping quotes
    url = url.strip('"\'') if url else ""
    # 3) Cap excessive length
    if len(url) > 512:
        logger.warning(f"Input URL too long ({len(url)}), trimming to 512 chars")
        url = url[:512]
    
    # Helper: quick check if token looks like a domain
    def _looks_like_domain(token: str) -> bool:
        if not token:
            return False
        # Skip strings that clearly look like log lines (start with YYYY-MM-DD or digits followed by ' - ')
        import re
        if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", token):
            return False
        if re.match(r"^\d+\s*-\s*", token):
            return False
        # Basic domain heuristic: contains a dot and no spaces
        if " " in token:
            return False
        # Accept IPv4 as well
        if re.match(r"^(\d{1,3}\.){3}\d{1,3}$", token):
            return True
        return "." in token
    
    # 4) Prepend scheme only if it looks like a domain and no scheme is present
    if url and not url.startswith("http") and _looks_like_domain(url):
        url = "https://" + url
    
    # 5) Parse and validate
    parsed = urlparse(url) if url else None
    netloc = parsed.netloc if parsed else ""
    if not netloc and parsed and parsed.path:
        # Case like: "example.com" without scheme: after prepend above it should be fixed,
        # but keep a fallback here just in case.
        netloc = parsed.path
    
    if not netloc or not _looks_like_domain(netloc):
        # Invalid input: return default without network calls and cache the result
        logger.warning(f"Invalid URL input for favicon fetch, returning defaults. raw='{raw_input[:120]}' sanitized='{url}'")
        # Build default result using config
        fallback_domain = (netloc or (url or "")).replace("www.", "")
        result = {
            "name": fallback_domain or "",
            "icon": config.get_default_icons().get("web", ""),
            "timestamp": time.time(),
        }
        _write_cache(url or (raw_input or ""), result, config)
        return result

    # Уровень 1: Проверка кэша по полному URL
    cached = _read_cache(url, config)
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

    # Уровень 2: Проверка наличия файла иконки для домена
    icon_filename = f"web_{domain.replace('.', '_')}.png"
    icon_path = str(icon_path_service.get_user_icons_dir() / icon_filename)

    if os.path.exists(icon_path):
        logger.debug(f"Found existing icon for domain {domain}. Fetching title only.")
        result["icon"] = icon_path
        
        resp = _http_request(url, config)
        if resp:
            try:
                soup = BeautifulSoup(resp.text, BS_PARSER)
                result["name"] = _extract_title(soup, url)
            except Exception as e:
                logger.error(f"Title parse error (icon existed) for {url}: {e}")
        
        _write_cache(url, result, config)
        return result

    # Иконки нет, выполняем полный поиск
    logger.debug(f"No icon for domain {domain}, starting full fetch.")
    resp = _http_request(url, config)
    if not resp:
        _write_cache(url, result, config)  # Кэшируем неудачу
        return result

    try:
        soup = BeautifulSoup(resp.text, BS_PARSER)
        result["name"] = _extract_title(soup, url)
        candidates = _find_favicon_candidates(soup, url)[:4]

        # Двухэтапная стратегия выбора иконки
        logger.debug(f"Trying {len(candidates)} favicon candidates for {domain}")
        
        # Этап 1: Ищем иконки размером минимум 48x48
        for i, icon_url in enumerate(candidates):
            logger.debug(f"Attempting candidate {i+1}/{len(candidates)}: {icon_url}")
            saved_path = _save_icon(icon_url, domain, config, is_fallback=False)
            if saved_path:
                result["icon"] = saved_path
                logger.info(f"Successfully saved good-sized icon {saved_path} for domain {domain} (candidate {i+1})")
                break  # Нашли подходящую иконку
        else:
            # Этап 2: Если не нашли подходящих, пробуем fallback (принимаем маленькие иконки)
            logger.debug(f"No icons ≥48px found, trying fallback mode for {domain}")
            for i, icon_url in enumerate(candidates):
                logger.debug(f"Fallback attempt {i+1}/{len(candidates)}: {icon_url}")
                saved_path = _save_icon(icon_url, domain, config, is_fallback=True)
                if saved_path:
                    result["icon"] = saved_path
                    logger.info(f"Successfully saved fallback icon {saved_path} for domain {domain} (candidate {i+1})")
                    break
            else:
                logger.warning(f"No valid favicon found for domain {domain} after trying all {len(candidates)} candidates")
    except Exception as e:
        logger.error(f"Full parse error for {url}: {e}")

    result["timestamp"] = time.time()
    _write_cache(url, result, config)
    return result
