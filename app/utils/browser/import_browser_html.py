import base64
import binascii
import logging
import uuid
from collections import defaultdict
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.config_data import app_config
from app.models.entities.constants import CATEGORY_BULK_UUID_FIELD
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link
from app.utils.validators.link_validators import validate_link_form_data

logger = logging.getLogger(__name__)


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


class BrowserBookmarksImporter:
    """HTML bookmarks importer: file selection (UI), parsing (data), DB synchronization (business).

    WARNING: Methods do not show error/warning dialogs (except select_file).
    UI layer should display messages to user.
    """

    # === UI layer ===
    def select_file(self, parent_widget):
        """Opens HTML file selection dialog. Returns path or empty string."""
        from PyQt6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            parent_widget, "Import from browser", "", "HTML Files (*.html *.htm)"
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

    def _process_bookmark_node(self, node, current_cat, categories, icons_dir):
        """Process bookmark node recursively."""
        for child in node.find_all(recursive=False):
            if child.name == "h3":
                current_cat = child.get_text()
            elif child.name == "a":
                if current_cat not in categories:
                    categories[current_cat] = []
                url = child.get("href")
                name = child.get_text() or url
                icon_data = child.get("icon")
                icon_path = ""
                if icon_data and icon_data.startswith("data:image/"):
                    icon_path = self._save_icon_from_base64(icon_data, url, icons_dir)
                link = {"name": name, "url": url, "icon_path": icon_path}
                categories[current_cat].append(link)
            elif child.name == "dl":
                self._process_bookmark_node(child, current_cat, categories, icons_dir)
            elif child.name in ["p", "dt"]:
                self._process_bookmark_node(child, current_cat, categories, icons_dir)

    def parse_bookmarks(self, html_path: str) -> dict:
        """Parses HTML browser bookmarks export into structure {category_name: [links...]}."""
        text = self._read_file_with_encoding(html_path)
        logger.debug("DEBUG: file head = %s", text[:500])

        soup = BeautifulSoup(text, "html.parser")
        categories: dict[str, list] = defaultdict(list)
        icons_dir = app_config.paths.get_link_icons_dir()

        root_dl = soup.find("dl")
        logger.debug("DEBUG: soup.find('dl') = %s", root_dl)

        if root_dl:
            self._process_bookmark_node(root_dl, "Uncategorized", categories, icons_dir)
            total_links = sum(len(links) for links in categories.values())
            logger.debug("DEBUG: Total links found: %s", total_links)

        return dict(categories)

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

        if not name:
            name = url

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
            "name": name.strip(),
            "url": url.strip(),
            "type": "web",
            "notes": "",
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
            category_id = name_to_id.get(cat_name)
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
    ) -> tuple[bool, str, int]:
        """Synchronizes parsed categories/links with DB. Returns (success, msg, added)."""
        existing_categories = structure_business_logic.get_categories(section_id) or []
        existing_names = {c.get("name") for c in existing_categories}

        incoming_names = set(categories.keys())
        missing_names = [n for n in incoming_names if n not in existing_names]

        self._create_missing_categories(
            missing_names, section_id, structure_business_logic
        )

        categories_after = structure_business_logic.get_categories(section_id) or []
        name_to_id = {c.get("name"): c.get("id") for c in categories_after}

        links_by_category = self._prepare_link_payloads(categories, name_to_id)
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

        return True, f"Added links: {added}", added

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
