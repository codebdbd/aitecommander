import os
import re
import time
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from requests.exceptions import RequestException

from app import config

# Локальные параметры (вынесены из бывшего icon_config)
MAX_IMAGE_SIZE = 1 * 1024 * 1024  # 1 MB
CACHE_TTL = 60 * 60 * 24 * 7  # 1 неделя
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"

# Локальный кэш
_favicon_cache = {}

def make_http_request(url: str, timeout: int = 5) -> Optional[requests.Response]:
    """Выполняет HTTP-запрос с обработкой ошибок."""
    if not url or not isinstance(url, str):
        logging.error(f"[make_http_request] Некорректный URL: {url}")
        return None
    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url
    try:
        parsed_url = urlparse(url)
        if not parsed_url.netloc:
            logging.error(f"[make_http_request] Неверный формат URL: {url}")
            return None
    except Exception as e:
        logging.error(f"[make_http_request] Ошибка при парсинге URL: {url}, ошибка: {e}")
        return None
    headers = {"User-Agent": USER_AGENT}
    try:
        try:
            import cloudscraper
            scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
            response = scraper.get(url, headers=headers, timeout=timeout)
        except ImportError:
            response = requests.get(url, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            logging.error(f"[make_http_request] Тайм-аут при запросе URL: {url}")
            return None
        except requests.exceptions.ConnectionError:
            logging.error(f"[make_http_request] Ошибка соединения при запросе URL: {url}")
            return None
        if response.status_code != 200:
            logging.debug(f"[make_http_request] Статус: {response.status_code}, URL: {url}")
            return None
        return response
    except RequestException as e:
        logging.error(f"[make_http_request] Ошибка запроса: {e}, URL: {url}")
        return None

def get_favicon_url_from_html(url: str) -> Optional[str]:
    """Извлекает URL favicon из HTML-страницы."""
    response = make_http_request(url)
    if not response:
        return None
    try:
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, "html.parser")
        icon_candidates = []

        raw_icon_matches = re.findall(
            r'<link[^>]*rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*href=["\']([^"\'>]+)["\'][^>]*>',
            response.text
        )
        for href in raw_icon_matches:
            href = href.replace('&amp;', '&')
            size = 0
            match = re.search(r'(\d+)x(\d+)', href)
            if match:
                try:
                    size = int(match.group(1))
                except ValueError:
                    pass
            elif 'w=' in href:
                w_match = re.search(r'w=(\d+)', href)
                if w_match:
                    try:
                        size = int(w_match.group(1))
                    except ValueError:
                        pass
            if not href.startswith(('http://', 'https://')):
                href = urljoin(url, href)
            icon_candidates.append((href, size))

        for link in soup.find_all("link"):
            rel = link.get("rel")
            href = link.get("href")
            if not rel or not href:
                continue
            rel_str = " ".join(rel).lower() if isinstance(rel, list) else str(rel).lower()
            if any(x in rel_str for x in ["icon", "shortcut", "apple-touch-icon", "apple-touch-icon-precomposed"]):
                href = href.replace('&amp;', '&')
                size = 0
                sizes = link.get("sizes")
                if sizes:
                    if sizes.lower() == "any":
                        size = 1000
                    else:
                        match = re.search(r'(\d+)x(\d+)', sizes)
                        if match:
                            try:
                                size = int(match.group(1))
                            except ValueError:
                                pass
                if size == 0 and 'w=' in href:
                    w_match = re.search(r'w=(\d+)', href)
                    if w_match:
                        try:
                            size = int(w_match.group(1))
                        except ValueError:
                            pass
                if size == 0:
                    match = re.search(r'(\d+)x(\d+)', href)
                    if match:
                        try:
                            size = int(match.group(1))
                        except ValueError:
                            pass
                if not href.startswith(('http://', 'https://')):
                    href = urljoin(url, href)
                icon_candidates.append((href, size))

        for meta in soup.find_all("meta"):
            name = meta.get("name")
            content = meta.get("content")
            if name and content and name.lower() in ["msapplication-tileimage", "msapplication-square150x150logo"]:
                content = content.replace('&amp;', '&')
                if not content.startswith(("http://", "https://")):
                    content = urljoin(url, content)
                icon_candidates.append((content, 150))

        # Уникальность + сортировка
        seen = set()
        unique_candidates = []
        for href, size in icon_candidates:
            if href not in seen:
                seen.add(href)
                unique_candidates.append((href, size))
        unique_candidates.sort(key=lambda x: x[1], reverse=True)

        logging.debug(f"[get_favicon_url_from_html] Найдено {len(unique_candidates)} кандидатов")
        for i, (u, s) in enumerate(unique_candidates[:5]):
            logging.debug(f"  {i+1}. {u} (size: {s})")

        if unique_candidates:
            return unique_candidates[0][0]
    except Exception as e:
        logging.error(f"[get_favicon_url_from_html] Ошибка парсинга HTML: {e}")
        logging.debug(response.text[:500])
    return None

def get_web_favicon(url: str, config_override=None) -> str:
    """Возвращает путь к favicon для веб-ссылки."""
    if not url:
        return config.DEFAULT_ICONS['web']
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"

    if url in _favicon_cache:
        path, ts = _favicon_cache[url]
        if os.path.exists(path) and time.time() - ts < CACHE_TTL:
            return path
        del _favicon_cache[url]

    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if not domain:
            return config.DEFAULT_ICONS['web']
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception as e:
        logging.error(f"[get_web_favicon] Ошибка парсинга домена: {e}")
        return config.DEFAULT_ICONS['web']

    icons_dir = config.LINK_ICONS_DIR
    os.makedirs(icons_dir, exist_ok=True)

    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', domain)
    icon_path = os.path.join(icons_dir, f"{safe_name}.ico")
    png_path = os.path.join(icons_dir, f"{safe_name}.png")

    if os.path.exists(icon_path) and os.path.getsize(icon_path) > 0:
        if time.time() - os.path.getmtime(icon_path) < CACHE_TTL:
            _favicon_cache[url] = (icon_path, time.time())
            return icon_path

    favicon_urls = []

    html_icon = get_favicon_url_from_html(url)
    if html_icon:
        favicon_urls.append(html_icon)

    scheme = parsed.scheme
    favicon_urls += [
        f"{scheme}://{domain}/favicon.ico",
        f"{scheme}://{domain}/favicon.png",
        f"{scheme}://www.{domain}/favicon.ico",
        f"{scheme}://www.{domain}/favicon.png",
        f"{scheme}://{domain}/assets/favicon.ico",
        f"{scheme}://{domain}/assets/images/favicon.ico",
        f"{scheme}://{domain}/static/favicon.ico",
        f"{scheme}://{domain}/static/images/favicon.ico",
        f"{scheme}://{domain}/images/favicon.ico",
        f"{scheme}://{domain}/wp-content/themes/theme/favicon.ico",
    ]
    favicon_urls = list(dict.fromkeys(favicon_urls))

    for favicon_url in favicon_urls:
        try:
            response = make_http_request(favicon_url, timeout=5)
            if not response or len(response.content) == 0 or len(response.content) > MAX_IMAGE_SIZE:
                continue
            ext = os.path.splitext(favicon_url.split("?")[0])[1].lower()
            temp_path = png_path if ext in ('.png', '.jpg', '.jpeg', '.webp', '.svg') else icon_path
            with open(temp_path, "wb") as f:
                f.write(response.content)

            if ext != ".ico" and ext in ('.png', '.jpg', '.jpeg', '.webp'):
                try:
                    img = Image.open(temp_path)
                    img.save(icon_path, format="ICO")
                    os.remove(temp_path)
                except Exception as e:
                    logging.error(f"[get_web_favicon] Ошибка конвертации в ICO: {e}")
                    os.remove(temp_path)
                    continue
            elif ext == ".svg":
                try:
                    import cairosvg
                    cairosvg.svg2png(url=temp_path, write_to=png_path)
                    img = Image.open(png_path)
                    img.save(icon_path, format="ICO")
                    os.remove(temp_path)
                    os.remove(png_path)
                except Exception as e:
                    logging.error(f"[get_web_favicon] Ошибка конвертации SVG: {e}")
                    for p in [temp_path, png_path]:
                        if os.path.exists(p):
                            os.remove(p)
                    continue

            if os.path.exists(icon_path) and os.path.getsize(icon_path) > 0:
                _favicon_cache[url] = (icon_path, time.time())
                return icon_path
            if os.path.exists(icon_path):
                os.remove(icon_path)
        except Exception as e:
            logging.error(f"[get_web_favicon] Ошибка обработки: {e}")
            for p in [icon_path, png_path]:
                if os.path.exists(p):
                    os.remove(p)

    _favicon_cache[url] = (config.DEFAULT_ICONS['web'], time.time())
    return config.DEFAULT_ICONS['web']
