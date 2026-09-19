# app/utils/dnd/mime.py
"""Centralized JSON-only MIME utilities for drag-and-drop.

This module is the single source of truth for creating and parsing
MIME payloads across the app. Payload format is strictly JSON:

    { "ids": [int, ...] }

No CSV or legacy fallbacks are supported here.
"""

import json
import logging
import os
import re
from urllib.parse import urlparse, urlunsplit

from PyQt6.QtCore import QByteArray, QMimeData, QUrl

from app.config_data import app_config

logger = logging.getLogger(__name__)

_WEB_URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
_WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


class MimeDataParser:
    """Utilities for creating and parsing drag-and-drop MIME data."""

    @staticmethod
    def extract_item_ids(mime_data: QMimeData, mime_type: str) -> list[int]:
        """Extracts list of IDs from JSON-only MIME payload.

        Returns empty list on any error or if format is missing/invalid.
        """
        try:
            if not mime_data or not mime_data.hasFormat(mime_type):
                return []
            raw = mime_data.data(mime_type).data().decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                ids = data.get("ids", [])
                if isinstance(ids, list) and all(isinstance(x, int) for x in ids):
                    return ids
            return []
        except Exception as exc:
            logger.warning("Failed to extract IDs from MIME (%s): %s", mime_type, exc)
            return []

    @staticmethod
    def create_mime_data(item_ids: list[int], mime_type: str) -> QMimeData:
        """Creates JSON-only MIME payload with {"ids": [...]}.
        Returns empty QMimeData on error.
        """
        md = QMimeData()
        try:
            payload = json.dumps({"ids": list(map(int, item_ids))}).encode("utf-8")
            md.setData(mime_type, QByteArray(payload))
            return md
        except Exception as exc:
            logger.error("Failed to create MIME data (%s): %s", mime_type, exc)
            return md

    @staticmethod
    def create_section_mime_data(
        section_ids: list[int], source_sphere_id: int | None = None
    ) -> QMimeData:
        """Creates JSON MIME payload for sections with {"ids": [...], "source_sphere_id": ...}."""
        md = QMimeData()
        try:
            payload = {
                "ids": list(map(int, section_ids)),
                "source_sphere_id": int(source_sphere_id) if source_sphere_id is not None else None,
            }
            raw = json.dumps(payload).encode("utf-8")
            mime_type = app_config.get_section_mime_type()
            md.setData(mime_type, QByteArray(raw))
            return md
        except Exception as exc:
            logger.error("Failed to create section MIME data: %s", exc)
            return md

    @staticmethod
    def extract_section_payload(
        mime_data: QMimeData,
    ) -> tuple[list[int], int | None]:
        """Extracts section IDs and source sphere ID from MIME data.

        Returns (section_ids, source_sphere_id).
        """
        try:
            if not mime_data:
                return [], None
            mime_type = app_config.get_section_mime_type()
            if not mime_data.hasFormat(mime_type):
                return [], None
            raw = mime_data.data(mime_type).data().decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                ids = [
                    int(x)
                    for x in data.get("ids", [])
                    if isinstance(x, int) and not isinstance(x, bool)
                ]
                source_sphere_id = data.get("source_sphere_id")
                if isinstance(source_sphere_id, int) and not isinstance(source_sphere_id, bool):
                    sphere_id = int(source_sphere_id)
                else:
                    sphere_id = None
                return ids, sphere_id
            return [], None
        except Exception as exc:
            logger.warning("Failed to extract section payload from MIME: %s", exc)
            return [], None

    @staticmethod
    def extract_external_web_urls(mime_data: QMimeData) -> list[str]:
        """Extract unique external http(s) URLs from common MIME formats."""
        return [
            target
            for target in MimeDataParser.extract_external_link_targets(mime_data)
            if normalize_external_web_url(target)
        ]

    @staticmethod
    def extract_external_link_targets(mime_data: QMimeData) -> list[str]:
        """Extract unique external web URLs and local paths from common MIME formats."""
        if not mime_data:
            return []

        candidates: list[str] = []
        try:
            if mime_data.hasUrls():
                for qurl in mime_data.urls():
                    try:
                        if qurl.isLocalFile():
                            candidates.append(qurl.toLocalFile())
                        else:
                            candidates.append(qurl.toString())
                    except Exception:
                        continue
        except Exception:
            logger.debug("Failed to read dragged URLs", exc_info=True)

        try:
            if mime_data.hasFormat("text/uri-list"):
                raw = bytes(mime_data.data("text/uri-list")).decode(
                    "utf-8", errors="ignore"
                )
                candidates.extend(
                    line.strip()
                    for line in raw.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                )
        except Exception:
            logger.debug("Failed to read text/uri-list", exc_info=True)

        try:
            if mime_data.hasText():
                text = mime_data.text() or ""
                candidates.extend(
                    match.group(0) for match in _WEB_URL_RE.finditer(text)
                )
        except Exception:
            logger.debug("Failed to read dragged text", exc_info=True)

        targets: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = normalize_external_link_target(candidate)
            if not normalized:
                continue
            dedup_key = _external_target_dedup_key(normalized)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            targets.append(normalized)
        return targets


def normalize_external_web_url(candidate: str) -> str:
    """Return a clean http(s) URL or an empty string for unsupported input."""
    if not isinstance(candidate, str):
        return ""
    url = candidate.strip().strip("'\"")
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    return url


def _external_target_dedup_key(target: str) -> str:
    """Return a stable deduplication key for external targets.

    Browsers may expose the same dragged link through multiple MIME
    representations with insignificant differences, for example
    `https://site.example` and `https://site.example/`.
    """
    web_url = normalize_external_web_url(target)
    if not web_url:
        try:
            return os.path.normcase(os.path.normpath(target))
        except Exception:
            return target.casefold()
    try:
        parsed = urlparse(web_url)
        path = parsed.path or ""
        if path == "/":
            path = ""
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                parsed.query,
                "",
            )
        )
    except Exception:
        logger.debug("Failed to normalize dedup key for %s", target, exc_info=True)
        return web_url


def normalize_external_link_target(candidate: str) -> str:
    """Return a clean web URL or local path for external drops."""
    if not isinstance(candidate, str):
        return ""
    value = candidate.strip().strip("'\"")
    if not value:
        return ""

    web_url = normalize_external_web_url(value)
    if web_url:
        return web_url

    if _WINDOWS_ABS_RE.match(value) or value.startswith("\\\\"):
        return value

    try:
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme.lower() != "file":
            return ""
        qurl = QUrl(value)
        if qurl.isLocalFile():
            local = qurl.toLocalFile().strip()
            return os.path.normpath(local)
    except Exception:
        logger.debug("Failed to normalize local URL target %s", value, exc_info=True)

    if value.startswith("/"):
        return value
    return ""


# Helpers to access configured MIME types centrally


def get_link_mime() -> str:
    return app_config.get_link_mime_type()


def get_category_mime() -> str:
    return app_config.get_category_mime_type()
