"""Discover favicon candidates from HTML and well-known paths/services."""
from __future__ import annotations

import json
from typing import List
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .constants import FORMAT_RANK, TARGET_SIZE, logger
from .http_client import http_request


def parse_icon_size(sizes_attr: str) -> int:
    if not sizes_attr:
        return 0
    import re
    match = re.search(r'(\d+)x?\d*', sizes_attr.lower())
    if not match:
        logger.debug(f"Invalid sizes attribute: {sizes_attr}")
        return 0
    return int(match.group(1))


def find_favicon_candidates(soup: BeautifulSoup, base_url: str, config=None) -> List[str]:
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
        size_value = parse_icon_size(sizes)
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

    # Web Manifest
    try:
        manifest_links = []
        for link in soup.find_all("link"):
            rel_val = link.get("rel")
            if not rel_val:
                continue
            tokens = [t.lower() for t in (rel_val if isinstance(rel_val, list) else str(rel_val).split())]
            if any(t == "manifest" for t in tokens):
                manifest_links.append(link)
        if manifest_links and config is not None:
            m_href = manifest_links[0].get("href")
            if m_href and not m_href.startswith("data:"):
                m_url = urljoin(base_url, m_href)
                m_resp = http_request(m_url, config, allow_non_2xx=True)
                if m_resp and getattr(m_resp, 'ok', False):
                    try:
                        m_json = json.loads(m_resp.text)
                        icons = m_json.get("icons") or []
                        for icon in icons:
                            src = icon.get("src")
                            if not src:
                                continue
                            i_url = urljoin(m_url, src)
                            sizes = str(icon.get("sizes") or "").split()
                            type_attr = icon.get("type") or ""
                            fmt = _detect_format(i_url, type_attr)
                            if sizes:
                                for sz in sizes:
                                    candidates.append({
                                        "url": i_url,
                                        "size": parse_icon_size(sz),
                                        "format": fmt,
                                        "format_rank": FORMAT_RANK.get(fmt, FORMAT_RANK["unknown"]),
                                        "base_priority": 1,
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

    # Main favicons (multiple rel tokens)
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

    # Apple touch
    for link in soup.find_all("link", rel="apple-touch-icon"):
        _add_link_candidate(link, "apple-touch-icon", 2)
    for link in soup.find_all("link", rel="apple-touch-icon-precomposed"):
        _add_link_candidate(link, "apple-touch-icon", 2)

    # Fallback paths and host variants
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

    # Third-party services
    google_url = f"https://www.google.com/s2/favicons?domain={host}&sz={TARGET_SIZE}"
    candidates.append({
        "url": google_url,
        "size": TARGET_SIZE,
        "format": "png",
        "format_rank": FORMAT_RANK["png"],
        "base_priority": 10,
        "media_priority": 0,
        "type": "google_fallback",
    })
    ddg_url = f"https://icons.duckduckgo.com/ip3/{host}.ico"
    candidates.append({
        "url": ddg_url,
        "size": 0,
        "format": "ico",
        "format_rank": FORMAT_RANK["ico"],
        "base_priority": 10,
        "media_priority": 0,
        "type": "ddg_fallback",
    })

    def sort_key(c: dict):
        size = c.get("size", 0)
        return (
            c.get("base_priority", 9),
            c.get("format_rank", FORMAT_RANK["unknown"]),
            -size,
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

    # og:image only if no proper link-icon/ico found
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
    seen = set()
    ordered_urls = [url for url in ordered_urls if not (url in seen or seen.add(url))]
    return ordered_urls


__all__ = ["find_favicon_candidates", "parse_icon_size", "FORMAT_RANK", "TARGET_SIZE"]
