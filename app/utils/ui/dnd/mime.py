# app/utils/dnd/mime.py
"""Centralized JSON-only MIME utilities for drag-and-drop.

This module is the single source of truth for creating and parsing
MIME payloads across the app. Payload format is strictly JSON:

    { "ids": [int, ...] }

No CSV or legacy fallbacks are supported here.
"""

import json
import logging
from typing import List

from PyQt6.QtCore import QByteArray, QMimeData

from app.config_data import app_config


class MimeDataParser:
    """Utilities for creating and parsing drag-and-drop MIME data."""

    @staticmethod
    def extract_item_ids(mime_data: QMimeData, mime_type: str) -> List[int]:
        """Extracts list of IDs from JSON-only MIME payload.

        Returns empty list on any error or if format is missing/invalid.
        """
        try:
            if not mime_data or not mime_data.hasFormat(mime_type):
                return []
            raw = bytes(mime_data.data(mime_type)).decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                ids = data.get("ids", [])
                if isinstance(ids, list) and all(isinstance(x, int) for x in ids):
                    return ids
            return []
        except Exception as exc:
            logging.warning("Failed to extract IDs from MIME (%s): %s", mime_type, exc)
            return []

    @staticmethod
    def create_mime_data(item_ids: List[int], mime_type: str) -> QMimeData:
        """Creates JSON-only MIME payload with {"ids": [...]}.
        Returns empty QMimeData on error.
        """
        md = QMimeData()
        try:
            payload = json.dumps({"ids": list(map(int, item_ids))}).encode("utf-8")
            md.setData(mime_type, QByteArray(payload))
            return md
        except Exception as exc:
            logging.error("Failed to create MIME data (%s): %s", mime_type, exc)
            return md


# Helpers to access configured MIME types centrally


def get_link_mime() -> str:
    return app_config.get_link_mime_type()


def get_category_mime() -> str:
    return app_config.get_category_mime_type()
