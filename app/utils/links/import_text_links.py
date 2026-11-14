"""Plain text, CSV, and Markdown links importer."""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any
from urllib.parse import urlparse

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from app.models.types.constants import (
    MAX_NAME_LENGTH,
    MAX_URL_LENGTH,
)
from app.utils.links.dropped_web_link import (
    classify_dropped_link_target,
    derive_dropped_local_link_name,
    derive_dropped_web_link_name,
)
from app.utils.validators.link_validators import validate_link_form_data

logger = logging.getLogger(__name__)

_LINKS_IMPORT_CONTEXT = "TextLinksImporter"
_IMPORT_TITLE = QT_TRANSLATE_NOOP("TextLinksImporter", "Import links from file")
_FILE_FILTER = QT_TRANSLATE_NOOP(
    "TextLinksImporter",
    "Supported Files (*.txt *.csv *.tsv *.md);;Text Files (*.txt);;CSV Files (*.csv *.tsv);;Markdown Files (*.md);;All Files (*.*)",
)
_IMPORT_ADDED = QT_TRANSLATE_NOOP("TextLinksImporter", "Added links: {count}")

_MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_URL_PATTERN = re.compile(
    r"(https?://[^\s<>\"'`]+|ftp://[^\s<>\"'`]+|file://[^\s<>\"'`]+)", re.IGNORECASE
)
_QUOTED_PATH_PATTERN = re.compile(r'["\']([a-zA-Z]:[/\\][^"\']+|\\\\(?:[^"\']+))["\']')
_UNQUOTED_PATH_PATTERN = re.compile(r"([a-zA-Z]:[/\\][^\s<>\"'`]+|\\\\[^\s<>\"'`]+)")
_URL_OR_PATH_START_RE = re.compile(
    r"^(?:https?://|ftp://|file://|[a-zA-Z]:[/\\]|//|\\\\)", re.IGNORECASE
)
_COMMON_DELIMITERS = ("\t", "|", ";", ",", " - ", " -- ", " :: ")


def _tr_import(text: str) -> str:
    return QCoreApplication.translate(_LINKS_IMPORT_CONTEXT, text)


def is_likely_target(candidate: str) -> bool:
    """Return True if candidate string represents a URL, file/folder path or network target."""
    text = (candidate or "").strip()
    if not text:
        return False

    if _URL_OR_PATH_START_RE.match(text):
        return True

    # Check for domain-like strings (e.g. "github.com", "sub.domain.org/path")
    if not any(c in text for c in ("\n", "\r", "\t", " ")):
        parsed = urlparse(f"http://{text}")
        if parsed.netloc and "." in parsed.netloc and not parsed.netloc.endswith("."):
            labels = parsed.netloc.split(".")
            if len(labels) >= 2 and len(labels[-1]) >= 2 and labels[-1].isalpha():
                return True

    return False


def normalize_import_url(raw_target: str) -> str:
    """Normalize target string, adding https:// if domain-only."""
    if not isinstance(raw_target, str):
        return ""
    target = raw_target.strip()
    if not target:
        return ""

    if target.startswith("//"):
        return f"https:{target}"

    # If it's a domain-like web address without protocol, default to https://
    parsed = urlparse(target)
    if (
        not parsed.scheme
        and not re.match(r"^[a-zA-Z]:[/\\]", target)
        and not target.startswith(("\\\\", "//"))
    ):
        candidate = f"https://{target}"
        candidate_parsed = urlparse(candidate)
        if (
            candidate_parsed.netloc
            and "." in candidate_parsed.netloc
            and " " not in candidate_parsed.netloc
        ):
            return candidate

    return target


class TextLinksImporter:
    """Imports links from plain text, CSV, TSV, or Markdown files into a category."""

    def select_file(self, parent_widget: Any) -> str:
        """Open file selection dialog. Return chosen file path or empty string."""
        from PyQt6.QtWidgets import QFileDialog

        from app.services.dialog_path_service import DialogPathService

        start_dir = DialogPathService.get_downloads_dir("TextLinks")
        path, _ = QFileDialog.getOpenFileName(
            parent_widget,
            _tr_import(_IMPORT_TITLE),
            start_dir,
            _tr_import(_FILE_FILTER),
        )
        if path:
            DialogPathService.remember_dir("TextLinks", path)
        return path or ""

    def read_file_with_encoding(self, file_path: str) -> str:
        """Read text from file attempting common encodings."""
        encodings = ("utf-8", "utf-8-sig", "cp1251", "latin-1")
        last_error = None
        for enc in encodings:
            try:
                with open(file_path, encoding=enc) as fp:
                    return fp.read()
            except (OSError, UnicodeDecodeError) as err:
                last_error = err

        try:
            with open(file_path, "rb") as f_bin:
                return f_bin.read().decode("utf-8", errors="replace")
        except OSError as err:
            logger.warning(
                "Failed to read links file %s: %s", file_path, err, exc_info=True
            )
            raise (last_error or err) from err

    def parse_links_from_text(self, text: str) -> list[dict[str, str]]:
        """Parse text into raw link dicts: [{'name': ..., 'url': ...}, ...]."""
        if not text:
            return []

        results: list[dict[str, str]] = []
        lines = text.splitlines()

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            # Skip pure markdown headers without links (e.g. '# Section')
            if line.startswith("#") and not ("(" in line and ")" in line):
                continue

            # Strip leading list markers: "- ", "* ", "+ ", "1. ", "01. "
            line = re.sub(r"^(?:[-*+]\s+|\d+[\.)]\s+)", "", line).strip()
            if not line:
                continue

            item = self._parse_single_line(line)
            if item and item.get("url"):
                results.append(item)

        return results

    def _parse_single_line(self, line: str) -> dict[str, str] | None:
        """Parse a single line containing a markdown link, URL, CSV/TSV, delimited text or single target."""
        # 1. Check for Markdown link: [Title](URL)
        md_match = _MARKDOWN_LINK_PATTERN.search(line)
        if md_match:
            name = md_match.group(1).strip()
            url = md_match.group(2).strip()
            # If URL has optional title: (url "title")
            if " " in url:
                parts = url.split(" ", 1)
                url = parts[0].strip()
            return {"name": name, "url": url}

        # 2. Check CSV-style parsing if comma, tab or semicolon is present
        if any(d in line for d in (",", "\t", ";")):
            for delim in ("\t", ";", ","):
                if delim not in line:
                    continue
                try:
                    reader = csv.reader(io.StringIO(line), delimiter=delim)
                    row = next(reader)
                    non_empty = [c.strip() for c in row if c and c.strip()]
                    if len(non_empty) >= 2:
                        first, second = non_empty[0], non_empty[1]
                        if is_likely_target(first) and not is_likely_target(second):
                            return {"name": second, "url": first}
                        if is_likely_target(second) and not is_likely_target(first):
                            return {"name": first, "url": second}
                        if is_likely_target(first):
                            return {"name": second, "url": first}
                        if is_likely_target(second):
                            return {"name": first, "url": second}
                except Exception:
                    pass

        # 3. Check text delimiters: " | ", " - ", " -- ", " :: "
        for delim in (" | ", " :: ", " -- ", " - "):
            if delim in line:
                parts = [p.strip() for p in line.split(delim, 1)]
                if len(parts) == 2 and parts[0] and parts[1]:
                    first, second = parts[0], parts[1]
                    if is_likely_target(first) and not is_likely_target(second):
                        return {"name": second, "url": first}
                    if is_likely_target(second) and not is_likely_target(first):
                        return {"name": first, "url": second}
                    if is_likely_target(first):
                        return {"name": second, "url": first}
                    if is_likely_target(second):
                        return {"name": first, "url": second}

        # 4. Check for quoted local/network path: '"C:\Program Files\..." Name'
        qp_match = _QUOTED_PATH_PATTERN.search(line)
        if qp_match:
            path = qp_match.group(1).strip()
            name = (line[: qp_match.start()] + " " + line[qp_match.end() :]).strip(
                " \t-–—|:;,"
            )
            return {"name": name, "url": path}

        # 5. Check for explicit web/network URL on the line: "Name https://..." or "https://... Name"
        url_match = _URL_PATTERN.search(line)
        if url_match:
            url = url_match.group(1).rstrip(".,;:)]}'\"`")
            name = (line[: url_match.start()] + " " + line[url_match.end() :]).strip(
                " \t-–—|:;,"
            )
            return {"name": name, "url": url}

        # 6. Check for unquoted local/network path: 'C:\Windows\notepad.exe Name' or 'Name C:\Windows\notepad.exe'
        up_match = _UNQUOTED_PATH_PATTERN.search(line)
        if up_match:
            path = up_match.group(1).rstrip(".,;:)]}'\"`")
            name = (line[: up_match.start()] + " " + line[up_match.end() :]).strip(
                " \t-–—|:;,"
            )
            return {"name": name, "url": path}

        # 7. Fallback: single URL or path on the line
        clean_target = line.strip(" '\"`")
        if is_likely_target(clean_target):
            return {"name": "", "url": clean_target}

        return None

    def parse_file(self, file_path: str) -> list[dict[str, str]]:
        """Read and parse links from a given file path."""
        text = self.read_file_with_encoding(file_path)
        return self.parse_links_from_text(text)

    def prepare_link_payload(
        self, item: dict[str, str], category_id: int
    ) -> dict[str, Any] | None:
        """Validate and prepare a single link payload for database insertion."""
        raw_url = item.get("url", "")
        url = normalize_import_url(raw_url)
        if not url or len(url) > MAX_URL_LENGTH:
            return None

        link_type = classify_dropped_link_target(url)

        name = (item.get("name") or "").strip()
        if not name:
            name = (
                derive_dropped_web_link_name(url)
                if link_type == "web"
                else derive_dropped_local_link_name(url)
            )

        if len(name) > MAX_NAME_LENGTH:
            name = name[:MAX_NAME_LENGTH].strip()

        if not validate_link_form_data(name, url, link_type):
            return None

        return {
            "category_id": int(category_id),
            "name": name,
            "url": url,
            "type": link_type,
            "notes": "",
            "is_favorite": 0,
            "icon_path": "",
            "args": "",
        }

    def sync_to_db(
        self,
        links: list[dict[str, str]],
        category_id: int,
        links_business: Any,
    ) -> tuple[bool, str, dict[str, int]]:
        """Insert links into database and return (success, message, statistics)."""
        payloads: list[dict[str, Any]] = []
        for item in links:
            payload = self.prepare_link_payload(item, category_id)
            if payload:
                payloads.append(payload)

        if not payloads:
            return (
                False,
                _tr_import("No valid links to import"),
                {"added": 0, "http_count": 0, "https_count": 0},
            )

        added = 0
        if hasattr(links_business, "create_links_for_import_bulk"):
            try:
                added = int(links_business.create_links_for_import_bulk(payloads) or 0)
            except Exception as exc:
                logger.exception("Bulk link import failed: %s", exc)
                return False, str(exc), {"added": 0, "http_count": 0, "https_count": 0}
        elif hasattr(links_business, "create_link_for_import"):
            for p in payloads:
                if links_business.create_link_for_import(p):
                    added += 1

        http_count = sum(1 for p in payloads if p.get("url", "").startswith("http://"))
        https_count = sum(
            1 for p in payloads if p.get("url", "").startswith("https://")
        )

        stats = {
            "added": added,
            "http_count": http_count,
            "https_count": https_count,
        }
        msg = _tr_import(_IMPORT_ADDED).format(count=added)
        return True, msg, stats
