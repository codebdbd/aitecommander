import base64
import binascii
import logging
import uuid
from collections import defaultdict
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from PyQt6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from app.config_data import app_config
from app.models.types.constants import (
    CATEGORY_BULK_UUID_FIELD,
    MAX_NAME_LENGTH,
    MAX_NOTES_LENGTH,
    MAX_URL_LENGTH,
)
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.validators.link_validators import validate_link_form_data

logger = logging.getLogger(__name__)
_BROWSER_IMPORT_CONTEXT = "BrowserBookmarksImporter"
_IMPORT_TITLE = QT_TRANSLATE_NOOP("BrowserBookmarksImporter", "Import from browser")
_HTML_FILTER = QT_TRANSLATE_NOOP("BrowserBookmarksImporter", "HTML Files (*.html *.htm)"
)
_IMPORT_ADDED = QT_TRANSLATE_NOOP("BrowserBookmarksImporter", "Added links: {count}"
)
_IMPORT_CATEGORIES = QT_TRANSLATE_NOOP("BrowserBookmarksImporter", "Categories created: {count}"
)


def _tr_import(text: str) -> str:
    return QCoreApplication.translate(_BROWSER_IMPORT_CONTEXT, text)


def _normalize_import_url(raw_url: str) -> str:
    """Normalize URLs coming from legacy bookmark exports."""
    if not isinstance(raw_url, str):
        return ""

    candidate = raw_url.strip()
    if not candidate:
        return ""

    # Handle protocol-relative URLs ("//example.com")
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"

    parsed = urlparse(candidate)

    if not parsed.scheme:
        host_candidate = ""
        if parsed.netloc:
            host_candidate = parsed.netloc
        elif parsed.path:
            host_candidate = parsed.path.split("/")[0]

        if host_candidate and "." in host_candidate and " " not in host_candidate:
            candidate = f"http://{candidate}"
            parsed = urlparse(candidate)

    if parsed.scheme:
        return candidate

    return candidate if parsed.netloc else ""


def _normalize_category_name(raw_name: object) -> str:
    """Normalize category name for robust matching during import."""
    if raw_name is None:
        return ""
    try:
        name = str(raw_name).strip()
    except Exception:
        return ""
    if len(name) > MAX_NAME_LENGTH:
        name = name[:MAX_NAME_LENGTH].strip()
    return name


def _category_key(name: object) -> str:
    """Case-insensitive key for category matching."""
    normalized = _normalize_category_name(name)
    return normalized.casefold()


class _NetscapeBookmarkParser(HTMLParser):
    """Event-driven parser for Netscape Bookmark HTML files with folder stack."""

    def __init__(self, icons_dir: Any, save_icon_callback: Any) -> None:
        super().__init__()
        self.categories: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.folder_stack: list[str] = ["Uncategorized"]
        self.pending_folder: str | None = None
        self.in_h3 = False
        self.current_h3_text: list[str] = []
        self.current_link: dict[str, str] | None = None
        self.current_a_text: list[str] = []
        self.icons_dir = icons_dir
        self.save_icon_callback = save_icon_callback

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        if t == "h3":
            self.in_h3 = True
            self.current_h3_text = []
        elif t == "dl":
            folder = (
                self.pending_folder
                if self.pending_folder
                else (self.folder_stack[-1] if self.folder_stack else "Uncategorized")
            )
            self.folder_stack.append(folder)
            self.pending_folder = None
        elif t == "a":
            url = attr_dict.get("href", "").strip()
            icon_data = attr_dict.get("icon", "")
            icon_path = ""
            if (
                icon_data
                and icon_data.startswith("data:image/")
                and self.save_icon_callback
                and self.icons_dir
            ):
                icon_path = self.save_icon_callback(icon_data, url, self.icons_dir)
            self.current_link = {
                "url": url,
                "icon_path": icon_path,
                "category": self.folder_stack[-1] if self.folder_stack else "Uncategorized",
            }
            self.current_a_text = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "h3":
            self.in_h3 = False
            raw_title = "".join(self.current_h3_text).strip()
            self.pending_folder = _normalize_category_name(raw_title) or "Uncategorized"
        elif t == "dl":
            if len(self.folder_stack) > 1:
                self.folder_stack.pop()
        elif t == "a":
            if self.current_link:
                name = "".join(self.current_a_text).strip() or self.current_link["url"]
                cat = _normalize_category_name(self.current_link["category"]) or "Uncategorized"
                self.categories[cat].append({
                    "name": name,
                    "url": self.current_link["url"],
                    "icon_path": self.current_link["icon_path"],
                })
                self.current_link = None

    def handle_data(self, data: str) -> None:
        if self.in_h3:
            self.current_h3_text.append(data)
        elif self.current_link is not None:
            self.current_a_text.append(data)


class BrowserBookmarksImporter:
    """HTML bookmarks importer: file selection (UI), parsing (data), DB synchronization (business).

    WARNING: Methods do not show error/warning dialogs (except select_file).
    UI layer should display messages to user.
    """

    # === UI layer ===
    def select_file(self, parent_widget):
        """Opens HTML file selection dialog. Returns path or empty string."""
        from PyQt6.QtWidgets import QFileDialog

        from app.utils.share_paths import (
            ensure_service_root,
            get_desktop_dir,
            get_entity_dir,
        )

        start_dir = ""
        desktop = get_desktop_dir()
        if desktop:
            root = ensure_service_root(desktop)
            if root:
                start_dir = str(get_entity_dir(root, "links"))

        path, _ = QFileDialog.getOpenFileName(
            parent_widget,
            _tr_import(_IMPORT_TITLE),
            start_dir,
            _tr_import(_HTML_FILTER),
        )
        return path or ""

    # === Data layer ===
    def _read_file_with_encoding(self, html_path):
        """Read file trying multiple encodings."""
        encodings_to_try = ("utf-8", "utf-8-sig", "cp1251", "latin-1")
        last_err = None

        for enc in encodings_to_try:
            try:
                with open(html_path, encoding=enc) as f:
                    text = f.read()
                    logger.debug("DEBUG: using encoding = %s", enc)
                    return text
            except (OSError, UnicodeDecodeError) as e:
                last_err = e
                logger.debug(
                    "parse_bookmarks: failed to read %s with encoding %s: %s",
                    html_path,
                    enc,
                    e,
                    exc_info=True,
                )

        # Fallback: read as binary with error replacement
        try:
            with open(html_path, "rb") as fb:
                raw = fb.read()
                text = raw.decode("utf-8", errors="replace")
                logger.debug("DEBUG: using encoding = utf-8(replace)")
                return text
        except OSError as e:
            logger.warning(
                "parse_bookmarks: failed to read file %s: %s",
                html_path,
                e,
                exc_info=True,
            )
            raise (last_err or e) from e

    def _save_icon_from_base64(self, icon_data, url, icons_dir):
        """Save base64 icon to file."""
        domain = ""
        if url:
            domain = urlparse(url).netloc.replace(":", "_").replace(".", "_")
        icon_fname = f"web_{domain}.png" if domain else "web_unknown.png"
        icon_file = icons_dir / icon_fname
        if not icon_file.exists():
            try:
                b64 = icon_data.split("base64,", 1)[-1]
                with open(icon_file, "wb") as f:
                    f.write(base64.b64decode(b64))
            except (binascii.Error, ValueError, OSError) as e:
                logger.debug(
                    "save_icon_from_base64 failed for %s: %s", url, e, exc_info=True
                )
                return ""
        return icon_fname

    def parse_bookmarks(self, html_path: str) -> dict:
        """Parses HTML browser bookmarks export into structure {category_name: [links...]}."""
        text = self._read_file_with_encoding(html_path)
        logger.debug("DEBUG: file head = %s", text[:500])

        icons_dir = app_config.paths.get_link_icons_dir()
        parser = _NetscapeBookmarkParser(icons_dir, self._save_icon_from_base64)
        parser.feed(text)

        total_links = sum(len(links) for links in parser.categories.values())
        logger.debug("DEBUG: Total links found: %s", total_links)

        return dict(parser.categories)

    # === Business слой ===
    def _get_default_icon(self):
        """Get default icon for categories."""
        try:
            from pathlib import Path
            full_path = resolve_icon_for_link({"type": "category", "icon_path": ""})
            # Return only filename, not full path
            return Path(full_path).name if full_path else ""
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning(
                "resolve_icon_for_link failed, using empty icon: %s", e, exc_info=True
            )
            return ""

    def _create_missing_categories(
        self, missing_names, section_id, structure_business_logic
    ):
        """Create missing categories in bulk."""
        if not missing_names:
            return

        default_icon = self._get_default_icon()
        bulk_items = []
        for name in missing_names:
            token = uuid.uuid4().hex
            bulk_items.append(
                {
                    "name": name,
                    "section_id": section_id,
                    "icon_path": default_icon,
                    CATEGORY_BULK_UUID_FIELD: token,
                }
            )

        try:
            created = structure_business_logic.create_categories_bulk(bulk_items) or []
            logger.debug(
                "DEBUG: Batch created/confirmed categories: %s for section %s",
                len(created),
                section_id,
            )
        except Exception as e:
            logger.exception("ERROR: Batch category creation failed: %s", e)

    def _prepare_link_payload(self, link, category_id, cat_name):
        """Prepare link payload for import."""
        raw_url = link.get("url", "")
        url = _normalize_import_url(raw_url)
        name = (link.get("name", "") or "").strip()

        if not url:
            logger.debug(
                "DEBUG: Skipping link '%s' in category '%s' due to missing URL (raw='%s')",
                name,
                cat_name,
                raw_url,
            )
            return None

        if len(url) > MAX_URL_LENGTH:
            logger.warning(
                "DEBUG: Skipping link '%s' in category '%s' due to URL exceeding max length %d (%d chars)",
                name,
                cat_name,
                MAX_URL_LENGTH,
                len(url),
            )
            return None

        if not name:
            name = url

        notes = (link.get("notes", "") or "").strip()
        if len(name) > MAX_NAME_LENGTH:
            if not notes:
                notes = name
            name = name[:MAX_NAME_LENGTH].strip()

        if len(notes) > MAX_NOTES_LENGTH:
            notes = notes[:MAX_NOTES_LENGTH]

        if not validate_link_form_data(name, url, "web"):
            logger.debug(
                "DEBUG: Skipping link '%s' in category '%s' due to failed validation (url='%s')",
                name,
                cat_name,
                url,
            )
            return None

        payload = {
            "category_id": int(category_id),
            "name": name,
            "url": url.strip(),
            "type": "web",
            "notes": notes,
            "is_favorite": int(link.get("is_favorite") or 0),
            "icon_path": link.get("icon_path", "") or "",
            "args": link.get("args", "") or "",
        }
        browser_key = link.get("browser_key")
        if browser_key is not None:
            payload["browser_key"] = browser_key
        return payload

    def _prepare_link_payloads(self, categories, name_to_id):
        """Prepare link payloads for all categories."""
        links_by_category: dict[int, list[dict]] = defaultdict(list)

        for cat_name, links in categories.items():
            logger.debug(
                "DEBUG: Processing category '%s', links: %s", cat_name, len(links)
            )
            category_id = name_to_id.get(_category_key(cat_name))
            if not category_id:
                logger.error(
                    "ERROR: Category ID '%s' not found after batch insert; skipping links",
                    cat_name,
                )
                continue

            for link in links:
                payload = self._prepare_link_payload(link, category_id, cat_name)
                if payload:
                    links_by_category[int(category_id)].append(payload)

        return links_by_category

    def _get_bulk_callable(self, links_business_logic, structure_business_logic):
        """Get bulk import callable if available."""
        if links_business_logic and hasattr(
            links_business_logic, "create_links_for_import_bulk"
        ):
            return links_business_logic.create_links_for_import_bulk
        elif hasattr(structure_business_logic, "links_business") and hasattr(
            structure_business_logic.links_business, "create_links_for_import_bulk"
        ):
            return structure_business_logic.links_business.create_links_for_import_bulk
        return None

    def _import_links(
        self,
        link_payloads,
        links_by_category,
        links_business_logic,
        structure_business_logic,
    ):
        """Import links using bulk or fallback method."""
        bulk_callable = self._get_bulk_callable(
            links_business_logic, structure_business_logic
        )

        if bulk_callable:
            try:
                return int(bulk_callable(link_payloads) or 0)
            except Exception as exc:
                logger.exception(
                    "Bulk link import failed, falling back to sequential mode: %s",
                    exc,
                    exc_info=True,
                )

        return self._fallback_import_links(
            links_business_logic,
            structure_business_logic,
            links_by_category,
        )

    def sync_to_db(
        self,
        categories: dict,
        section_id: int,
        structure_business_logic,
        links_business_logic=None,
    ) -> tuple[bool, str, dict]:
        """Synchronizes parsed categories/links with DB. Returns (success, msg, stats)."""
        existing_categories = structure_business_logic.get_categories(section_id) or []
        existing_name_keys = {
            _category_key(c.get("name"))
            for c in existing_categories
            if _category_key(c.get("name"))
        }

        incoming_names = [
            _normalize_category_name(name)
            for name in categories.keys()
            if _normalize_category_name(name)
        ]
        incoming_name_keys = {_category_key(name) for name in incoming_names}
        missing_names = [
            name
            for name in incoming_names
            if _category_key(name) and _category_key(name) not in existing_name_keys
        ]

        self._create_missing_categories(
            missing_names, section_id, structure_business_logic
        )

        categories_after = structure_business_logic.get_categories(section_id) or []
        name_to_id = {
            _category_key(c.get("name")): c.get("id")
            for c in categories_after
            if _category_key(c.get("name"))
        }
        unresolved_keys = sorted(
            key for key in incoming_name_keys if key and key not in name_to_id
        )
        if unresolved_keys:
            preview = unresolved_keys[:5]
            logger.warning(
                "Import sync: %d category names still unresolved after bulk insert; preview=%s",
                len(unresolved_keys),
                preview,
            )

        normalized_categories = {
            _normalize_category_name(name): links
            for name, links in categories.items()
            if _normalize_category_name(name)
        }
        links_by_category = self._prepare_link_payloads(
            normalized_categories,
            name_to_id,
        )
        link_payloads = [
            dict(payload)
            for payloads in links_by_category.values()
            for payload in payloads
        ]

        added = 0
        if link_payloads:
            added = self._import_links(
                link_payloads,
                links_by_category,
                links_business_logic,
                structure_business_logic,
            )

        # Collect statistics
        http_count = sum(1 for p in link_payloads if p.get("url", "").startswith("http://"))
        https_count = sum(1 for p in link_payloads if p.get("url", "").startswith("https://"))
        
        stats = {
            "added": added,
            "http_count": http_count,
            "https_count": https_count,
            "categories_created": len(missing_names),
        }
        
        # Build message
        msg = _tr_import(_IMPORT_ADDED).format(count=added)
        if len(missing_names) > 0:
            msg += "\n" + _tr_import(_IMPORT_CATEGORIES).format(
                count=len(missing_names)
            )
        
        return True, msg, stats

    def _fallback_import_links(
        self,
        links_business_logic,
        structure_business_logic,
        links_by_category: dict[int, list[dict]],
    ) -> int:
        """Sequential link import with duplicate checks as a safety fallback."""
        added = 0
        for category_id, payloads in links_by_category.items():
            existing_pairs = set()
            try:
                if links_business_logic:
                    existing_links = links_business_logic.get_links(category_id)
                elif hasattr(structure_business_logic, "links_business"):
                    existing_links = structure_business_logic.links_business.get_links(
                        category_id
                    )
                else:
                    existing_links = []
            except Exception as exc:
                logger.warning(
                    "Failed to load existing links for fallback import (category %s): %s",
                    category_id,
                    exc,
                )
                existing_links = []

            for el in existing_links:
                try:
                    existing_pairs.add(
                        (
                            str(el.get("name", "")).strip(),
                            str(el.get("url", "")).strip(),
                        )
                    )
                except (AttributeError, ValueError, TypeError):
                    continue

            for payload in payloads:
                normalized_pair = (
                    payload.get("name", "").strip(),
                    payload.get("url", "").strip(),
                )
                if normalized_pair in existing_pairs:
                    continue
                existing_pairs.add(normalized_pair)

                try:
                    target_logic = links_business_logic or getattr(
                        structure_business_logic, "links_business", None
                    )
                    link_id = (
                        target_logic.create_link_for_import(dict(payload))
                        if target_logic
                        else None
                    )
                    if link_id:
                        added += 1
                    else:
                        logger.error(
                            "ERROR: Failed to add link '%s' to category %s (fallback)",
                            payload.get("name", ""),
                            category_id,
                        )
                except Exception as exc:
                    logger.exception(
                        "ERROR: Fallback link import failed for '%s' (category %s): %s",
                        payload.get("name", ""),
                        category_id,
                        exc,
                    )
        return added
