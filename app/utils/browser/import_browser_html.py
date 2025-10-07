import base64
import binascii
import logging
from collections import defaultdict
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.config_data import app_config
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

logger = logging.getLogger(__name__)


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
    def parse_bookmarks(self, html_path: str) -> dict:
        """Parses HTML browser bookmarks export into structure {category_name: [links...]}."""
        encodings_to_try = ("utf-8", "utf-8-sig", "cp1251", "latin-1")
        last_err = None
        text = None
        used_encoding = None
        for enc in encodings_to_try:
            try:
                with open(html_path, "r", encoding=enc) as f:
                    text = f.read()
                    used_encoding = enc
                    break
            except (OSError, UnicodeDecodeError) as e:
                last_err = e
                logger.debug(
                    "parse_bookmarks: failed to read %s with encoding %s: %s",
                    html_path,
                    enc,
                    e,
                    exc_info=True,
                )
                continue
        if text is None:
            try:
                with open(html_path, "rb") as fb:
                    raw = fb.read()
                    text = raw.decode("utf-8", errors="replace")
                    used_encoding = "utf-8(replace)"
            except OSError as e:
                logger.warning(
                    "parse_bookmarks: failed to read file %s: %s", html_path, e, exc_info=True
                )
                raise last_err or e
        logger.debug("DEBUG: using encoding = %s", used_encoding)
        logger.debug("DEBUG: file head = %s", text[:500])
        soup = BeautifulSoup(text, "html.parser")
        categories = defaultdict(list)
        icons_dir = app_config.paths.get_link_icons_dir()

        def save_icon_from_base64(icon_data, url):
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
                    logger.debug("save_icon_from_base64 failed for %s: %s", url, e, exc_info=True)
                    return ""
            return icon_fname

        root_dl = soup.find("dl")
        logger.debug("DEBUG: soup.find('dl') = %s", root_dl)

        def process_node(node, current_cat):
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
                        icon_path = save_icon_from_base64(icon_data, url)
                    link = {"name": name, "url": url, "icon_path": icon_path}
                    categories[current_cat].append(link)
                elif child.name == "dl":
                    process_node(child, current_cat)
                elif child.name in ["p", "dt"]:
                    process_node(child, current_cat)

        if root_dl:
            process_node(root_dl, "Uncategorized")
            total_links = sum(len(links) for links in categories.values())
            logger.debug("DEBUG: Total links found: %s", total_links)
        return dict(categories)

    # === Business слой ===
    def sync_to_db(
        self,
        categories: dict,
        section_id: int,
        structure_business_logic,
        links_business_logic=None,
    ) -> tuple[bool, str, int]:
        """Synchronizes parsed categories/links with DB. Returns (success, msg, added)."""
        # 1) Current state of section categories
        existing_categories = structure_business_logic.get_categories(section_id) or []
        existing_names = {c.get("name") for c in existing_categories}

        # 2) Which categories are missing
        incoming_names = set(categories.keys())
        missing_names = [n for n in incoming_names if n not in existing_names]

        # 3) Batch insert missing categories
        try:
            default_icon = resolve_icon_for_link({"type": "category", "icon_path": ""})
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning("resolve_icon_for_link failed, using empty icon: %s", e, exc_info=True)
            default_icon = ""
        bulk_items = [
            {"name": name, "section_id": section_id, "icon_path": default_icon}
            for name in missing_names
        ]
        if bulk_items:
            try:
                created = (
                    structure_business_logic.create_categories_bulk(bulk_items) or []
                )
                logger.debug(
                    "DEBUG: Batch created/confirmed categories: %s for section %s",
                    len(created),
                    section_id,
                )
            except Exception as e:
                # Use exception to preserve stack (unexpected service layer errors)
                logger.exception(
                    "ERROR: Batch category creation failed: %s", e
                )

        # 4) Actual name->id map
        categories_after = structure_business_logic.get_categories(section_id) or []
        name_to_id = {c.get("name"): c.get("id") for c in categories_after}

        # 5) Insert links without duplicates
        added = 0
        for cat_name, links in categories.items():
            logger.debug(
                "DEBUG: Processing category '%s', links: %s", cat_name, len(links)
            )
            category_id = name_to_id.get(cat_name)
            if not category_id:
                logger.error(
                    f"ERROR: Category ID '{cat_name}' not found after batch insert; skipping links"
                )
                continue

            existing_name_url = set()
            try:
                if links_business_logic:
                    existing_links = links_business_logic.get_links(category_id)
                elif hasattr(structure_business_logic, "links_business"):
                    existing_links = structure_business_logic.links_business.get_links(
                        category_id
                    )
                else:
                    existing_links = []
            except Exception as e:
                logger.warning(
                    "Failed to get existing links for category %s: %s",
                    category_id,
                    e,
                )
                existing_links = []

            for el in existing_links:
                try:
                    existing_name_url.add(
                        (
                            str(el.get("name", "")).strip(),
                            str(el.get("url", "")).strip(),
                        )
                    )
                except (AttributeError, ValueError, TypeError) as ex:
                    logger.debug("skip malformed existing link entry: %s", ex, exc_info=True)

            for link in links:
                icon_path = link.get("icon_path", "")
                url = link.get("url", "")
                name = link.get("name", "")
                logger.debug(
                    "DEBUG: Checking duplicate: name='%s', url='%s', category_id=%s",
                    name,
                    url,
                    category_id,
                )
                if (name.strip(), url.strip()) in existing_name_url:
                    logger.debug(
                        "DEBUG: Skipped duplicate '%s' (%s) in category '%s' (id=%s)",
                        name,
                        url,
                        cat_name,
                        category_id,
                    )
                    continue

                link_data = {
                    "category_id": category_id,
                    "name": link.get("name", ""),
                    "type": "web",
                    "notes": "",
                    "is_favorite": 0,
                    "last_used": None,
                    "icon_path": icon_path,
                    "args": "",
                }

                try:
                    if links_business_logic:
                        link_id = links_business_logic.create_link_for_import(link_data)
                    else:
                        link_id = (
                            structure_business_logic.links_business.create_link_for_import(
                                link_data
                            )
                            if hasattr(structure_business_logic, "links_business")
                            else None
                        )
                    if link_id:
                        logger.debug(
                            "DEBUG: Added link '%s' to category '%s' (id=%s)",
                            link.get("name", ""),
                            cat_name,
                            category_id,
                        )
                        added += 1
                    else:
                        logger.error(
                            "ERROR: Failed to add link '%s' to category '%s'",
                            link.get("name", ""),
                            cat_name,
                        )
                except Exception as e:
                    logger.exception(
                        "ERROR: Failed to add link '%s' to category '%s': %s",
                        link.get("name", ""),
                        cat_name,
                        e,
                    )

        return True, f"Added links: {added}", added
