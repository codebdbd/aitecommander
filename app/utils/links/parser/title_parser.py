from __future__ import annotations

import html as _html
import json
import re
from typing import Optional
from urllib.parse import urlencode, urlparse

from bs4 import BeautifulSoup

from .constants import BS_PARSER, logger
from .domain import base_domain
from .http_client import http_request
from .js_renderer import render_html

# ------------------------------
# Module-level constants
# ------------------------------
_SITE_SPECIFIC_SUFFIXES = {
    "youtube.com": [
        " - YouTube",
        " | YouTube",
        " - YouTube Music",
        " - YouTube Gaming",
        " - YouTube TV",
    ],
    "youtu.be": [" - YouTube", " | YouTube"],
    "twitter.com": [" / Twitter", " on Twitter", " | Twitter"],
    "x.com": [" / X", " on X", " | X"],
    "reddit.com": [" : ", " • r/", " - Reddit"],
    "stackoverflow.com": [" - Stack Overflow"],
    "github.com": [" · GitHub", " - GitHub"],
    "medium.com": [" - Medium", " | Medium"],
    "dev.to": [" - DEV Community"],
    "hackernews": [" | Hacker News"],
    "wikipedia.org": [" - Wikipedia"],
    "amazon.com": [" - Amazon.com", " : Amazon.com"],
}

_GENERAL_SUFFIX_SEPARATORS = [
    " - ",
    " | ",
    " :: ",
    " • ",
    " — ",
    " – ",
]

_HTML_TITLE_SEPARATORS = [" | ", " - ", " :: ", " • ", " — ", " – ", " : "]


def _build_soup_index(soup: BeautifulSoup) -> dict:
    """Предварительно индексирует часто используемые элементы, чтобы избежать повторных find().
    Возвращает словарь с заранее выбранными тегами/значениями.
    """
    try:
        metas = soup.find_all("meta")
    except Exception:
        metas = []

    meta_by_name = {}
    meta_by_prop = {}
    for m in metas:
        try:
            n = (m.get("name") or "").strip().lower()
            p = (m.get("property") or "").strip().lower()
            if n:
                meta_by_name.setdefault(n, []).append(m)
            if p:
                meta_by_prop.setdefault(p, []).append(m)
        except Exception:
            continue

    try:
        scripts_jsonld = soup.find_all("script", type="application/ld+json")
    except Exception:
        scripts_jsonld = []

    idx = {
        "title_tag": getattr(soup, "title", None),
        "h1_first": None,
        "meta_by_name": meta_by_name,
        "meta_by_prop": meta_by_prop,
        "scripts_jsonld": scripts_jsonld,
    }
    try:
        idx["h1_first"] = soup.find("h1")
    except Exception:
        idx["h1_first"] = None
    return idx


def _looks_js_heavy(soup: BeautifulSoup, html_text: str) -> bool:
    """Простая эвристика для определения страниц, зависящих от JS/SPA."""
    try:
        text_len = len(html_text or "")
        scripts_count = len(soup.find_all("script")) if soup else 0
        markers = [
            'id="__next"',
            "data-reactroot",
            "ng-version",
            "vite",
            "webpackJsonp",
            "data-hydrate",
        ]
        marker_hit = any(m in (html_text or "") for m in markers)
        title_ok = bool(
            getattr(soup, "title", None)
            and soup.title
            and soup.title.get_text(strip=True)
        )
        # Мало текста, много скриптов, нет нормального <title> или есть SPA-маркеры
        if (text_len < 15000 and scripts_count > 20 and not title_ok) or marker_hit:
            return True
    except Exception:
        return False
    return False


# ------------------------------
# Small helpers (no behavior change)
# ------------------------------
def _decode_response_text(resp, config) -> str:
    """Decode HTTP response to text with charset-normalizer fallback.
    Mirrors existing inline logic in get_title() without behavior change.
    """
    try:
        enc = getattr(resp, "encoding", None)
        if not enc or str(enc).lower() == "iso-8859-1":
            try:
                # Попытка детектировать кодировку через charset-normalizer
                try:
                    from charset_normalizer import from_bytes  # type: ignore

                    best = from_bytes(resp.content).best()
                    if best is not None:
                        return str(best)
                    return resp.content.decode(
                        getattr(resp, "apparent_encoding", None) or "utf-8",
                        errors="replace",
                    )
                except Exception:
                    return resp.content.decode(
                        getattr(resp, "apparent_encoding", None) or "utf-8",
                        errors="replace",
                    )
            except Exception:
                return resp.text
        else:
            return resp.text
    except Exception:
        return getattr(resp, "text", "") or ""


def _make_soup(html_text: str) -> BeautifulSoup:
    """Create BeautifulSoup with BS_PARSER and safe fallback; no behavior change."""
    try:
        return BeautifulSoup(html_text, BS_PARSER)
    except Exception:
        return BeautifulSoup(html_text, "html.parser")


def _use_playwright_for_title(config) -> bool:
    """Read config flag for Playwright usage; preserves existing default True-on-except."""
    try:
        return bool(getattr(config, "USE_PLAYWRIGHT_FOR_TITLE", False))
    except Exception:
        return True


def _try_playwright_title(url: str, config) -> str:
    """Render via Playwright and extract title. Returns empty string on failure."""
    try:
        rendered_html = render_html(url, config)
        if not rendered_html:
            return ""
        s2 = _make_soup(rendered_html)
        return _extract_title(s2, url)
    except Exception:
        return ""


def _fetch_youtube_title(url: str, config) -> Optional[str]:
    api_url = "https://www.youtube.com/oembed?" + urlencode(
        {"url": url, "format": "json"}
    )
    resp = http_request(api_url, config)
    if resp and getattr(resp, "ok", False):
        try:
            data = json.loads(resp.text)
            return data.get("title")
        except Exception:
            return None
    return None


def _extract_jsonld_title(soup: BeautifulSoup, soup_index: dict | None = None) -> str:
    """Extract title from JSON-LD structured data"""
    scripts = (
        (soup_index or {}).get("scripts_jsonld") if soup_index is not None else None
    )
    if scripts is None:
        scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            if not script.string:
                continue
            data = json.loads(script.string)

            # Handle None or empty data
            if data is None:
                continue

            if isinstance(data, list):
                data = data[0] if data else {}

            # Ensure data is a dictionary
            if not isinstance(data, dict):
                continue

            # Search for title in different Schema.org types
            title_fields = ["headline", "name", "title"]
            for field in title_fields:
                if field in data and data[field]:
                    title = str(data[field]).strip()
                    if title:
                        return title
        except (json.JSONDecodeError, AttributeError, TypeError):
            continue
    return ""


def _extract_site_specific_title(
    soup: BeautifulSoup, domain: str, soup_index: dict | None = None
) -> Optional[str]:
    """Special handling for popular sites"""
    domain_lower = domain.lower()

    # Site-specific selectors
    if "medium.com" in domain_lower:
        title_elem = soup.find("h1", class_=re.compile(r"graf.*title|pw-post-title"))
        if title_elem:
            text = title_elem.get_text(strip=True)
            return text if text else None

    elif "dev.to" in domain_lower:
        title_elem = soup.find(
            "h1", class_=re.compile(r"crayons-article__title|article-title")
        )
        if title_elem:
            text = title_elem.get_text(strip=True)
            return text if text else None

    elif "hackernews" in domain_lower or "news.ycombinator.com" in domain_lower:
        title_elem = soup.find("a", class_="storylink") or soup.find(
            "span", class_="titleline"
        )
        if title_elem:
            text = title_elem.get_text(strip=True)
            return text if text else None

    elif "wikipedia.org" in domain_lower:
        title_elem = soup.find("h1", id="firstHeading")
        if title_elem:
            text = title_elem.get_text(strip=True)
            return text if text else None

    elif "amazon.com" in domain_lower or "amazon." in domain_lower:
        title_elem = soup.find("span", id="productTitle")
        if title_elem:
            text = title_elem.get_text(strip=True)
            return text if text else None

    elif "reddit.com" in domain_lower:
        title_elem = soup.find(
            "h1", attrs={"data-testid": "post-content"}
        ) or soup.find("div", class_=re.compile(r".*title.*"))
        if title_elem:
            text = title_elem.get_text(strip=True)
            return text if text else None

    elif "stackoverflow.com" in domain_lower:
        title_elem = soup.find("h1", attrs={"itemprop": "name"}) or soup.find(
            "a", class_="question-hyperlink"
        )
        if title_elem:
            text = title_elem.get_text(strip=True)
            return text if text else None

    elif "github.com" in domain_lower:
        title_elem = soup.find("h1", class_=re.compile(r".*header.*")) or soup.find(
            "strong", attrs={"itemprop": "name"}
        )
        if title_elem:
            text = title_elem.get_text(strip=True)
            return text if text else None

    return None


def _score_title_quality(title: str) -> int:
    """Score title quality from 0 to 100"""
    if not title:
        return 0

    score = 50  # base score
    title_lower = title.lower()

    # Length scoring (optimal 30-60 characters)
    if 30 <= len(title) <= 60:
        score += 20
    elif 15 <= len(title) <= 80:
        score += 10
    elif len(title) < 10:
        score -= 20
    elif len(title) > 100:
        score -= 10

    # Avoid technical/error titles
    bad_patterns = [
        "404",
        "error",
        "not found",
        "untitled",
        "document",
        "page not found",
        "access denied",
    ]
    if any(pattern in title_lower for pattern in bad_patterns):
        score -= 30

    # Prefer descriptive titles with separators
    if any(sep in title for sep in ":-|•—–"):
        score += 10

    # Avoid titles with only symbols/numbers
    if not re.search(r"[a-zA-Zа-яА-Я\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]", title):
        score -= 40

    # Prefer titles with mixed case (not all caps or all lowercase)
    if title.isupper() or title.islower():
        score -= 5

    # Bonus for titles that seem like real content
    content_indicators = [
        "how to",
        "what is",
        "guide",
        "tutorial",
        "review",
        "analysis",
    ]
    if any(indicator in title_lower for indicator in content_indicators):
        score += 5

    return max(0, min(100, score))


def _get_best_title(candidates: list[tuple[str, str]]) -> str:
    """Select best title from candidates based on quality scoring"""
    if not candidates:
        return ""

    scored = []
    for title, source in candidates:
        if title and title.strip():
            quality_score = _score_title_quality(title)
            # Add source priority bonus
            source_bonus = {
                "site_specific": 15,
                "jsonld": 10,
                "og_twitter": 8,
                "html_title": 5,
                "meta_title": 3,
                "h1": 2,
            }.get(source, 0)

            total_score = quality_score + source_bonus
            scored.append((title.strip(), total_score, source))
            try:
                logger.debug(
                    f"[title] candidate source={source} score={total_score} raw='{title[:120]}'"
                )
            except Exception:
                pass

    if not scored:
        return ""

    # Return best scored title
    best = max(scored, key=lambda x: x[1])
    try:
        logger.debug(f"[title] best source={best[2]} score={best[1]} title='{best[0]}'")
    except Exception:
        pass
    return best[0]


def _smart_postprocess_title(title: str, domain: str) -> str:
    """Enhanced title postprocessing with site-specific rules"""
    if not title:
        return domain

    title = title.strip()

    # Remove HTML tags if any remain
    title = BeautifulSoup(title, "html.parser").get_text()
    title = _html.unescape(title).strip()

    # Site-specific cleaning patterns
    domain_lower = domain.lower()
    for site, patterns in _SITE_SPECIFIC_SUFFIXES.items():
        if site in domain_lower:
            for pattern in patterns:
                if title.endswith(pattern):
                    title = title[: -len(pattern)].strip()
                    break

    # General cleaning patterns (case insensitive)
    general_patterns = [f"{sep}{domain}" for sep in _GENERAL_SUFFIX_SEPARATORS]

    title_lower = title.lower()
    for pattern in general_patterns:
        pattern_lower = pattern.lower()
        if title_lower.endswith(pattern_lower):
            title = title[: -len(pattern)].strip()
            break

    # Remove common prefixes/suffixes
    prefixes_suffixes = [
        ("Home - ", ""),
        ("Home | ", ""),
        ("Welcome to ", ""),
        ("", " - Home"),
        ("", " | Home"),
        ("", " - Official Site"),
        ("", " - Official Website"),
        ("", " | Official Site"),
    ]

    for prefix, suffix in prefixes_suffixes:
        if prefix and title.startswith(prefix):
            title = title[len(prefix) :].strip()
        elif suffix and title.endswith(suffix):
            title = title[: -len(suffix)].strip()

    # Clean up separators and whitespace
    title = re.sub(r"\s*[-|•—–:]\s*$", "", title)  # Remove trailing separators
    title = re.sub(r"^\s*[-|•—–:]\s*", "", title)  # Remove leading separators
    title = re.sub(r"\s+", " ", title)  # Normalize whitespace

    return title if title else domain


def _meta_content(
    soup: BeautifulSoup, *selectors: tuple[str, str], soup_index: dict | None = None
) -> str:
    """Extract content from meta tags with multiple selector fallbacks"""
    for attr, value in selectors:
        tag = None
        if soup_index is not None:
            key = (value or "").strip().lower()
            try:
                if attr == "name":
                    candidates = (soup_index.get("meta_by_name", {}) or {}).get(key, [])
                elif attr == "property":
                    candidates = (soup_index.get("meta_by_prop", {}) or {}).get(key, [])
                else:
                    candidates = []
                tag = candidates[0] if candidates else None
            except Exception:
                tag = None
        if tag is None:
            tag = soup.find("meta", attrs={attr: value})
        if tag and tag.get("content"):
            content = (tag.get("content") or "").strip()
            if content:
                return content
    return ""


def _extract_html_title(
    soup: BeautifulSoup, domain: str, soup_index: dict | None = None
) -> str:
    """Extract and clean HTML title tag"""
    title_tag = (soup_index or {}).get("title_tag") if soup_index is not None else None
    if title_tag is None:
        title_tag = soup.title
    if not title_tag:
        return ""

    # Get text from all child elements
    title_text = title_tag.get_text(separator=" ", strip=True)
    if not title_text:
        return ""

    # Handle common title separators intelligently
    for sep in _HTML_TITLE_SEPARATORS:
        if sep in title_text:
            parts = [p.strip() for p in title_text.split(sep)]
            # Remove parts that are just the domain
            clean_parts = [p for p in parts if p and domain.lower() not in p.lower()]
            if clean_parts:
                # Return the first meaningful part
                return clean_parts[0]

    return title_text


def _extract_title(soup: BeautifulSoup, url: str) -> str:
    """Enhanced title extraction with multiple sources and quality scoring"""
    domain = base_domain(urlparse(url).netloc)
    candidates = []
    soup_index = _build_soup_index(soup)

    # 1. Site-specific extraction (highest priority)
    site_specific = _extract_site_specific_title(soup, domain, soup_index)
    if site_specific:
        candidates.append((site_specific, "site_specific"))

    # 2. JSON-LD structured data
    jsonld_title = _extract_jsonld_title(soup, soup_index)
    if jsonld_title:
        candidates.append((jsonld_title, "jsonld"))

    # 3. Open Graph and Twitter meta tags
    og_twitter = _meta_content(
        soup,
        ("property", "og:title"),
        ("name", "og:title"),
        ("name", "twitter:title"),
        ("property", "twitter:title"),
        ("property", "article:title"),
        ("name", "sailthru.title"),
        ("name", "DC.title"),  # Dublin Core
        ("itemprop", "name"),  # Schema.org microdata
        soup_index=soup_index,
    )
    if og_twitter:
        candidates.append((og_twitter, "og_twitter"))

    # 4. HTML title tag (with intelligent parsing)
    html_title = _extract_html_title(soup, domain, soup_index)
    if html_title:
        candidates.append((html_title, "html_title"))

    # 5. Named title meta tag
    named = _meta_content(
        soup, ("name", "title"), ("property", "title"), soup_index=soup_index
    )
    if named:
        candidates.append((named, "meta_title"))

    # 6. First H1 tag
    h1 = soup_index.get("h1_first")
    if h1:
        h1_text = h1.get_text(strip=True)
        if h1_text:
            candidates.append((h1_text, "h1"))

    # Select best title based on quality scoring
    best_title = _get_best_title(candidates)
    if best_title:
        return _smart_postprocess_title(best_title, domain)

    return domain


def _postprocess_title(title: str, domain: str) -> str:
    """Legacy postprocessing function for backward compatibility"""
    title = title.strip()
    replacements = [" - YouTube", " | YouTube", " - YouTube Music", " - YouTube Gaming"]
    for suffix in replacements:
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    if not title:
        return domain
    return title


def get_title(url: str, config, soup: Optional[BeautifulSoup] = None) -> str:
    """Main function to extract page title with enhanced parsing capabilities"""
    host = base_domain(urlparse(url).netloc)

    # Special handling for YouTube
    if host in ("youtube.com", "youtu.be"):
        yt = _fetch_youtube_title(url, config)
        if yt:
            return _smart_postprocess_title(yt, host)

    if soup is not None:
        return _extract_title(soup, url)

    # Fetch page content if soup not provided
    try:
        ua = getattr(config, "USER_AGENT", None)
    except Exception:
        ua = None
    timeout_override = getattr(config, "HTML_FETCH_TIMEOUT", None)
    retries_override = getattr(config, "HTML_FETCH_RETRIES", 2)
    try:
        logger.info(
            f"[title] start url={url} ua={ua} timeout={timeout_override} retries={retries_override}"
        )
    except Exception:
        pass

    # HEAD preflight: выяснить content-type/length, не тратя трафик (диагностика и эвристики)
    try:
        head_resp = http_request(
            url,
            config,
            allow_non_2xx=True,
            timeout_override=timeout_override,
            retries=1,
            method="HEAD",
        )
        if head_resp is not None:
            ctype = head_resp.headers.get("Content-Type", "")
            clen = head_resp.headers.get("Content-Length", "")
            logger.debug(f"[title] HEAD url={url} type='{ctype}' len={clen}")
            if ctype and "text/html" not in ctype.lower():
                logger.warning(
                    f"[title] non-html content-type url={url} type='{ctype}'"
                )
    except Exception as he:
        try:
            logger.debug(f"[title] HEAD failed url={url} err={he}")
        except Exception:
            pass

    resp = http_request(
        url, config, timeout_override=timeout_override, retries=retries_override
    )
    if resp:
        try:
            txt = _decode_response_text(resp, config)
            s = _make_soup(txt)
            # Эвристика: страница может требовать JS-рендера
            js_suspected = False
            try:
                js_suspected = _looks_js_heavy(s, txt)
                if js_suspected:
                    logger.warning(f"[title] js-heavy suspected url={url}")
            except Exception:
                js_suspected = False
            title = _extract_title(s, url)
            # Пробуем лёгкий JS-рендер перед Selenium, если заголовок пуст/плохой или страница js-heavy
            try:
                use_playwright = _use_playwright_for_title(config)
            except Exception:
                use_playwright = True
            if use_playwright:
                need_render = js_suspected or not title or len(title) < 3
                if need_render:
                    try:
                        logger.info(f"[title] try playwright render url={url}")
                        title2 = _try_playwright_title(url, config)
                        if (
                            title2
                            and title2.strip()
                            and title2.strip().lower() != (title or "").strip().lower()
                        ):
                            title = title2
                            logger.info(
                                f"[title] playwright extracted url={url} title='{title2}'"
                            )
                    except Exception as re:
                        try:
                            logger.warning(
                                f"[title] playwright render failed url={url} err={re}"
                            )
                        except Exception:
                            pass
            try:
                logger.info(f"[title] done url={url} extracted='{title}'")
            except Exception:
                pass
            return title
        except Exception as e:
            try:
                logger.error(f"[title] parse error url={url} err={e}")
            except Exception:
                pass

    # Optional Selenium fallback for JS-heavy pages (unchanged behavior)
    try:
        use_selenium = bool(getattr(config, "USE_SELENIUM_FOR_TITLE", False))
    except Exception:
        use_selenium = False
    if use_selenium:
        try:
            logger.info(f"[title] selenium fallback enabled url={url}")
            try:
                from selenium import webdriver  # type: ignore
                from selenium.webdriver.chrome.options import Options  # type: ignore
            except Exception as ie:
                logger.warning(f"[title] selenium import failed: {ie}")
                raise

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            if ua:
                options.add_argument(f"--user-agent={ua}")
            # Faster load strategy
            try:
                options.page_load_strategy = "eager"
            except Exception:
                pass
            driver = webdriver.Chrome(options=options)
            try:
                pl_to = int(getattr(config, "SELENIUM_PAGELOAD_TIMEOUT", 12))
            except Exception:
                pl_to = 12
            try:
                driver.set_page_load_timeout(pl_to)
            except Exception:
                pass
            try:
                driver.get(url)
                page = driver.page_source or ""
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass
            if page:
                try:
                    s2 = _make_soup(page)
                    title2 = _extract_title(s2, url)
                    logger.info(
                        f"[title] selenium extracted url={url} title='{title2}'"
                    )
                    return title2 or host
                except Exception as pe:
                    logger.error(f"[title] selenium parse error url={url} err={pe}")
        except Exception as se:
            try:
                logger.warning(f"[title] selenium fallback failed url={url} err={se}")
            except Exception:
                pass

    return base_domain(urlparse(url).netloc)


__all__ = ["get_title"]
