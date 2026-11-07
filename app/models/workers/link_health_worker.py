"""Background worker for checking local link paths and discovering moved targets."""

from __future__ import annotations

import logging
import os
import re
import string
import threading
from concurrent.futures import CancelledError
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, pyqtSignal

from app.models.types.link_type import LinkType

if TYPE_CHECKING:
    from app.models import Database

logger = logging.getLogger(__name__)

LOCAL_LINK_TYPES: tuple[str, ...] = (
    LinkType.FILE.value,
    LinkType.FOLDER.value,
    LinkType.PROGRAM.value,
    LinkType.SCRIPT.value,
)

_FULL_LINK_COLUMNS: tuple[str, ...] = (
    "id",
    "category_id",
    "name",
    "url",
    "type",
    "notes",
    "is_favorite",
    "is_group_launch",
    "last_used",
    "icon_path",
    "args",
    "browser_key",
    "position",
    "chrome_rotation",
    "rotation_index",
    "rotation_profiles",
)


def expand_local_path(raw_path: str) -> str:
    """Expand environment variables and user home in a raw local path string."""
    cleaned = (raw_path or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ('"', "'"):
        cleaned = cleaned[1:-1].strip()
    if not cleaned:
        return ""
    return os.path.expanduser(os.path.expandvars(cleaned))


def propagate_folder_relink(
    items: list[dict[str, Any]],
    old_path_str: str,
    new_path_str: str,
    existing_keys: set[tuple[int, str, str, str]] | None = None,
) -> list[int]:
    """Propagate a folder prefix change across broken link items.

    When a user manually locates a file/folder or accepts a candidate fix,
    this function checks whether a common parent directory was moved/renamed
    and automatically resolves other broken items under that same old directory
    if the corresponding target exists on disk.

    Returns:
        List of link IDs whose ``suggested_url`` was updated.
    """
    expanded_old = expand_local_path(old_path_str)
    expanded_new = expand_local_path(new_path_str)
    if not expanded_old or not expanded_new:
        return []

    try:
        old_p = Path(expanded_old)
        new_p = Path(expanded_new)
    except Exception:
        return []

    # Determine the moved ancestor directory pair (old_dir -> new_dir).
    # Walk up while the trailing part names match case-insensitively.
    old_cur = old_p
    new_cur = new_p
    while (
        old_cur.name
        and new_cur.name
        and old_cur.name.lower() == new_cur.name.lower()
        and old_cur.parent != old_cur
        and new_cur.parent != new_cur
    ):
        old_cur = old_cur.parent
        new_cur = new_cur.parent

    # If the leaf file itself was renamed in the same folder, use its parent only if
    # the parent directories actually differ.
    if old_cur == old_p and new_cur == new_p:
        if old_p.parent != new_p.parent:
            old_dir = old_p.parent
            new_dir = new_p.parent
        else:
            return []
    else:
        old_dir = old_cur
        new_dir = new_cur

    old_dir_norm = os.path.normcase(os.path.normpath(str(old_dir)))
    if not old_dir_norm or old_dir_norm in (".", "\\", "/"):
        return []

    # Prevent treating a drive root alone (e.g. "C:\") as a folder rename unless
    # new_dir is also a valid directory and we have a relative path.
    prefix_with_sep = old_dir_norm.rstrip("\\/") + os.sep
    updated_ids: list[int] = []

    for item in items:
        link_id = int(item.get("id") or 0)
        raw_url = str(item.get("url") or "")
        item_exp = expand_local_path(raw_url)
        if not item_exp:
            continue
        item_norm = os.path.normcase(os.path.normpath(item_exp))
        if not item_norm.startswith(prefix_with_sep):
            continue

        # Preserve original case of relative tail using Path.relative_to where possible
        try:
            rel_tail = Path(os.path.normpath(item_exp)).relative_to(
                Path(os.path.normpath(str(old_dir)))
            )
        except ValueError:
            rel_str = os.path.normpath(item_exp)[len(prefix_with_sep) :]
            rel_tail = Path(rel_str)

        candidate_path = new_dir / rel_tail
        link_type = str(item.get("type") or LinkType.FILE.value)
        if not _path_matches_link_type(candidate_path, link_type):
            continue

        candidate_str = str(candidate_path)
        if candidate_str == raw_url:
            continue
        if (
            candidate_str == str(item.get("suggested_url") or "")
            and item.get("status") == LinkHealthWorker.STATUS_FIX_FOUND
        ):
            continue

        cat_id = int(item.get("category_id") or 0)
        name = str(item.get("name") or "")
        args = str(item.get("args") or "")
        if existing_keys is not None and (cat_id, name, candidate_str, args) in existing_keys:
            item["suggested_url"] = candidate_str
            item["status"] = LinkHealthWorker.STATUS_DUPLICATE_EXISTS
        else:
            item["suggested_url"] = candidate_str
            item["status"] = LinkHealthWorker.STATUS_FIX_FOUND
        updated_ids.append(link_id)

    return updated_ids


def _path_matches_link_type(path: Path, link_type: str) -> bool:
    """Return True if ``path`` exists and matches the expected link type."""
    try:
        if not path.exists():
            return False
        if link_type == LinkType.FOLDER.value:
            return path.is_dir()
        return path.is_file() or path.is_dir()
    except OSError:
        return False


class LinkHealthSignals(QObject):
    """Signals for LinkHealthWorker."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    issue_found = pyqtSignal(dict)  # issue metadata dict
    finished = pyqtSignal(list)  # list of all found issues
    error = pyqtSignal(str)  # error message


class LinkHealthWorker(QRunnable):
    """Background worker that audits local links and suggests relink targets.

    Scans ``file``, ``folder``, ``program``, and ``script`` links in SQLite,
    checks path availability with a root/UNC reachability cache to prevent
    blocking on disconnected network shares, and searches adjacent/sibling
    directories or alternate drives for moved targets.
    """

    STATUS_FIX_FOUND = "fix_found"
    STATUS_NOT_FOUND = "not_found"
    STATUS_DRIVE_OFFLINE = "drive_offline"
    STATUS_DUPLICATE_EXISTS = "duplicate_exists"

    def __init__(
        self,
        db: Database,
        *,
        max_search_dirs: int = 120,
    ) -> None:
        super().__init__()
        self.db = db
        self.max_search_dirs = max(10, int(max_search_dirs))
        self.signals = LinkHealthSignals()
        self._is_cancelled = False
        self._cancel_event = threading.Event()
        self._root_cache: dict[str, bool] = {}
        self._available_drives: list[str] | None = None
        self._folder_mappings: list[tuple[str, Path]] = []
        self._existing_keys: set[tuple[int, str, str, str]] = set()

    def cancel(self) -> None:
        """Request worker cancellation."""
        self._is_cancelled = True
        self._cancel_event.set()
        logger.info("[link_health] Cancellation requested")

    def is_cancelled(self) -> bool:
        """Return True if cancellation was requested."""
        return self._is_cancelled or self._cancel_event.is_set()

    def _raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise CancelledError()

    def _load_all_category_hierarchies(self) -> dict[int, dict[str, Any]]:
        """Preload all category hierarchies in a single query."""
        default_path = QCoreApplication.translate("LinkHealthWorker", "No Category")
        hierarchies: dict[int, dict[str, Any]] = {}
        try:
            query = """
                SELECT
                    c.id AS category_id,
                    c.name AS category_name,
                    c.icon_path AS category_icon,
                    s.name AS section_name,
                    s.icon_path AS section_icon,
                    sp.name AS sphere_name,
                    sp.icon_path AS sphere_icon
                FROM category c
                LEFT JOIN section s ON c.section_id = s.id
                LEFT JOIN sphere sp ON s.sphere_id = sp.id
            """
            rows = self.db.connection.execute(query).fetchall()
            for row in rows:
                row_data = dict(row)
                cat_id = int(row_data["category_id"])
                category_name = row_data.get("category_name") or ""
                section_name = row_data.get("section_name") or ""
                sphere_name = row_data.get("sphere_name") or ""
                parts = [p for p in (sphere_name, section_name, category_name) if p]
                path = " / ".join(parts) if parts else category_name or default_path
                hierarchies[cat_id] = {
                    "path": path,
                    "sphere_name": sphere_name,
                    "sphere_icon_path": row_data.get("sphere_icon") or "",
                    "section_name": section_name,
                    "section_icon_path": row_data.get("section_icon") or "",
                    "category_name": category_name,
                    "category_icon_path": row_data.get("category_icon") or "",
                }
        except Exception as exc:
            logger.error("Failed to load category hierarchies: %s", exc, exc_info=True)
        return hierarchies

    def _load_local_links_and_keys(self) -> tuple[list[dict[str, Any]], set[tuple[int, str, str, str]]]:
        """Load all local links and build the set of existing UNIQUE keys."""
        self._raise_if_cancelled()
        cols_sql = ", ".join(f"l.{c}" for c in _FULL_LINK_COLUMNS)
        placeholders = ", ".join("?" for _ in LOCAL_LINK_TYPES)
        query = f"""
            SELECT {cols_sql}
            FROM link l
            WHERE l.type IN ({placeholders})
            ORDER BY l.id ASC
        """
        rows = self.db.connection.execute(query, LOCAL_LINK_TYPES).fetchall()
        links: list[dict[str, Any]] = []
        existing_keys: set[tuple[int, str, str, str]] = set()

        # Also load all (category_id, name, url, args) keys from the table to guard UNIQUE constraint
        all_keys_rows = self.db.connection.execute(
            "SELECT category_id, name, url, args FROM link"
        ).fetchall()
        for kr in all_keys_rows:
            kd = dict(kr)
            existing_keys.add(
                (
                    int(kd.get("category_id") or 0),
                    str(kd.get("name") or ""),
                    str(kd.get("url") or ""),
                    str(kd.get("args") or ""),
                )
            )

        for row in rows:
            links.append(dict(row))
        return links, existing_keys

    def _get_available_drives(self) -> list[str]:
        """Return list of reachable drive roots (e.g. ['C:\\', 'D:\\'])."""
        if self._available_drives is not None:
            return self._available_drives
        drives: list[str] = []
        if os.name == "nt":
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                try:
                    if os.path.exists(root):
                        drives.append(root)
                except OSError:
                    continue
        self._available_drives = drives
        return drives

    def _extract_root(self, expanded_path: str) -> str:
        """Extract drive or UNC share root from an expanded path."""
        try:
            p = Path(expanded_path)
            if p.drive:
                return p.drive + ("\\" if not p.drive.endswith(("\\", "/")) else "")
        except Exception:
            pass
        if expanded_path.startswith("\\\\"):
            parts = [pt for pt in expanded_path.lstrip("\\").split("\\") if pt]
            if len(parts) >= 2:
                return f"\\\\{parts[0]}\\{parts[1]}\\"
            if len(parts) == 1:
                return f"\\\\{parts[0]}\\"
        return ""

    def _is_root_online(self, expanded_path: str) -> bool:
        """Return True if the drive or UNC root of ``expanded_path`` is reachable."""
        root = self._extract_root(expanded_path)
        if not root:
            # Relative path or no drive specified
            return True
        norm_root = os.path.normcase(root)
        if norm_root in self._root_cache:
            return self._root_cache[norm_root]

        online = False
        try:
            online = os.path.exists(root)
        except OSError:
            online = False
        self._root_cache[norm_root] = online
        return online

    def _record_folder_mapping(self, old_dir: Path, new_dir: Path) -> None:
        """Cache a discovered directory relocation (old_dir -> new_dir)."""
        old_norm = os.path.normcase(os.path.normpath(str(old_dir)))
        if not old_norm or old_norm in (".", "\\", "/"):
            return
        # Avoid duplicate mappings
        for existing_old, _ in self._folder_mappings:
            if existing_old == old_norm:
                return
        self._folder_mappings.append((old_norm, new_dir))

    def find_relink_candidate(self, raw_path: str, link_type: str) -> str | None:
        """Attempt to locate a moved local file/folder near its original path.

        Strategies (in priority order):
        1. Previously discovered folder mapping (``OldDir -> NewDir``).
        2. Versioned or renamed intermediate directory under the deepest existing ancestor.
        3. Search by target filename/dirname in deepest existing ancestor, its parent,
           and their immediate subdirectories (bounded by ``max_search_dirs``).
        4. Same relative path on another available local drive (e.g. ``C:\\...`` -> ``D:\\...``).
        """
        expanded = expand_local_path(raw_path)
        if not expanded:
            return None

        try:
            norm_expanded = os.path.normpath(expanded)
            old_path = Path(norm_expanded)
        except Exception:
            return None

        target_name = old_path.name
        if not target_name:
            return None

        # Strategy 1: Check cached folder prefix mappings
        item_norm = os.path.normcase(norm_expanded)
        for old_dir_norm, new_dir_path in self._folder_mappings:
            prefix = old_dir_norm.rstrip("\\/") + os.sep
            if item_norm.startswith(prefix):
                rel_str = norm_expanded[len(prefix) :]
                candidate = new_dir_path / rel_str
                if _path_matches_link_type(candidate, link_type):
                    return str(candidate)

        # Find the deepest existing ancestor directory
        ancestors: list[Path] = []
        cur = old_path.parent
        while cur != cur.parent:
            ancestors.append(cur)
            cur = cur.parent
        if cur:
            ancestors.append(cur)

        existing_anc: Path | None = None
        missing_chain: list[str] = []
        for anc in ancestors:
            self._raise_if_cancelled()
            try:
                if anc.is_dir():
                    existing_anc = anc
                    break
            except OSError:
                pass
            if anc.name:
                missing_chain.append(anc.name)

        missing_chain.reverse()  # From top-most missing dir down to immediate parent

        # Strategy 2: If an intermediate folder was renamed or bumped in version
        # (e.g. "App v1.0/bin/app.exe" -> "App v1.1/bin/app.exe")
        if existing_anc is not None and missing_chain:
            first_missing = missing_chain[0]
            rel_under_missing = Path(*missing_chain[1:]) / target_name if len(missing_chain) > 1 else Path(target_name)
            best_match: tuple[float, Path] | None = None
            try:
                with os.scandir(existing_anc) as it:
                    for entry in it:
                        self._raise_if_cancelled()
                        try:
                            if not entry.is_dir(follow_symlinks=False):
                                continue
                        except OSError:
                            continue
                        candidate_sub = Path(entry.path) / rel_under_missing
                        if _path_matches_link_type(candidate_sub, link_type):
                            score = _folder_similarity(first_missing, entry.name)
                            if best_match is None or score > best_match[0]:
                                best_match = (score, candidate_sub)
            except OSError:
                pass

            if best_match is not None:
                chosen = best_match[1]
                # Record mapping for the renamed directory
                old_missing_dir = existing_anc / first_missing
                # Walk up from chosen to get the corresponding new dir
                new_missing_dir = chosen
                for _ in range(len(missing_chain)):
                    new_missing_dir = new_missing_dir.parent
                self._record_folder_mapping(old_missing_dir, new_missing_dir)
                return str(chosen)

        # Strategy 3: Bounded BFS search for target_name around existing_anc and its parent
        if existing_anc is not None:
            target_lower = target_name.lower()
            search_roots: list[Path] = [existing_anc]
            if existing_anc.parent != existing_anc:
                try:
                    if existing_anc.parent.is_dir():
                        search_roots.append(existing_anc.parent)
                except OSError:
                    pass

            visited_dirs: set[str] = set()
            dirs_checked = 0
            queue: list[tuple[Path, int]] = [(r, 0) for r in search_roots]

            while queue and dirs_checked < self.max_search_dirs:
                self._raise_if_cancelled()
                current_dir, depth = queue.pop(0)
                norm_dir = os.path.normcase(os.path.normpath(str(current_dir)))
                if norm_dir in visited_dirs:
                    continue
                visited_dirs.add(norm_dir)
                dirs_checked += 1

                # Direct check in current_dir
                direct_candidate = current_dir / target_name
                if _path_matches_link_type(direct_candidate, link_type):
                    if old_path.parent != current_dir:
                        self._record_folder_mapping(old_path.parent, current_dir)
                    return str(direct_candidate)

                if depth >= 2:
                    continue

                try:
                    with os.scandir(current_dir) as it:
                        for entry in it:
                            self._raise_if_cancelled()
                            name_lower = entry.name.lower()
                            if name_lower == target_lower:
                                entry_path = Path(entry.path)
                                if _path_matches_link_type(entry_path, link_type):
                                    if old_path.parent != current_dir:
                                        self._record_folder_mapping(old_path.parent, current_dir)
                                    return str(entry_path)
                            try:
                                if (
                                    entry.is_dir(follow_symlinks=False)
                                    and not entry.name.startswith(".")
                                    and name_lower not in ("node_modules", "__pycache__", ".git", ".venv", "windows", "$recycle.bin", "system volume information")
                                ):
                                    queue.append((Path(entry.path), depth + 1))
                            except OSError:
                                continue
                except OSError:
                    continue

        # Strategy 4: Drive letter swap (e.g. C:\Projects\... -> D:\Projects\...)
        if old_path.drive and len(old_path.drive) == 2 and old_path.drive[1] == ":":
            orig_drive = old_path.drive.upper()
            try:
                rel_from_root = old_path.relative_to(old_path.anchor)
            except ValueError:
                rel_from_root = None
            if rel_from_root is not None:
                for drive_root in self._get_available_drives():
                    self._raise_if_cancelled()
                    if drive_root[:2].upper() == orig_drive:
                        continue
                    alt_candidate = Path(drive_root) / rel_from_root
                    if _path_matches_link_type(alt_candidate, link_type):
                        return str(alt_candidate)

        return None

    def run(self) -> None:
        """Execute the local link health scan."""
        try:
            self._raise_if_cancelled()
            logger.info("[link_health] Starting local link health check...")
            hierarchies = self._load_all_category_hierarchies()
            links, existing_keys = self._load_local_links_and_keys()
            self._existing_keys = existing_keys

            total = len(links)
            if total == 0:
                self.signals.progress.emit(
                    0,
                    0,
                    QCoreApplication.translate(
                        "LinkHealthWorker", "No local links to check"
                    ),
                )
                self.signals.finished.emit([])
                return

            issues: list[dict[str, Any]] = []
            default_hierarchy = {
                "path": QCoreApplication.translate("LinkHealthWorker", "No Category"),
                "sphere_name": "",
                "sphere_icon_path": "",
                "section_name": "",
                "section_icon_path": "",
                "category_name": "",
                "category_icon_path": "",
            }

            for idx, link in enumerate(links, start=1):
                self._raise_if_cancelled()
                raw_url = str(link.get("url") or "")
                name = str(link.get("name") or "")
                link_type = str(link.get("type") or LinkType.FILE.value)
                cat_id = int(link.get("category_id") or 0)
                args = str(link.get("args") or "")

                if idx == 1 or idx % 5 == 0 or idx == total:
                    self.signals.progress.emit(
                        idx,
                        total,
                        QCoreApplication.translate(
                            "LinkHealthWorker", "Checking ({0}/{1}): {2}"
                        ).format(idx, total, name or raw_url),
                    )

                expanded = expand_local_path(raw_url)
                if not expanded:
                    status = self.STATUS_NOT_FOUND
                    suggested_url = ""
                elif not self._is_root_online(expanded):
                    status = self.STATUS_DRIVE_OFFLINE
                    suggested_url = ""
                else:
                    target_path = Path(os.path.normpath(expanded))
                    if _path_matches_link_type(target_path, link_type):
                        # Healthy local path
                        continue

                    candidate = self.find_relink_candidate(raw_url, link_type)
                    if candidate:
                        suggested_url = candidate
                        if (cat_id, name, suggested_url, args) in existing_keys:
                            status = self.STATUS_DUPLICATE_EXISTS
                        else:
                            status = self.STATUS_FIX_FOUND
                    else:
                        status = self.STATUS_NOT_FOUND
                        suggested_url = ""

                hierarchy = hierarchies.get(cat_id, default_hierarchy)
                issue_item: dict[str, Any] = {
                    "id": int(link["id"]),
                    "category_id": cat_id,
                    "name": name,
                    "url": raw_url,
                    "suggested_url": suggested_url,
                    "status": status,
                    "type": link_type,
                    "args": args,
                    "category_path": hierarchy["path"],
                    "hierarchy": hierarchy,
                    "link_data": dict(link),
                }
                issues.append(issue_item)
                self.signals.issue_found.emit(issue_item)

            # Second pass: if folder mappings were discovered mid-scan, propagate them to
            # earlier items that were marked STATUS_NOT_FOUND before the mapping was known.
            if self._folder_mappings:
                for item in issues:
                    if item["status"] != self.STATUS_NOT_FOUND:
                        continue
                    candidate = self.find_relink_candidate(item["url"], item["type"])
                    if candidate:
                        item["suggested_url"] = candidate
                        key = (
                            int(item["category_id"]),
                            str(item["name"]),
                            candidate,
                            str(item["args"]),
                        )
                        if key in existing_keys:
                            item["status"] = self.STATUS_DUPLICATE_EXISTS
                        else:
                            item["status"] = self.STATUS_FIX_FOUND

            self.signals.finished.emit(issues)
            logger.info(
                "[link_health] Scan finished: %d issues out of %d local links",
                len(issues),
                total,
            )
        except CancelledError:
            logger.info("[link_health] Check cancelled by user")
            self.signals.finished.emit([])
        except Exception as exc:
            logger.error("[link_health] Error during health check: %s", exc, exc_info=True)
            self.signals.error.emit(str(exc))


_VERSION_TOKEN_RE = re.compile(r"\d+(?:\.\d+)*")


def _folder_similarity(old_name: str, new_name: str) -> float:
    """Compute similarity score between an old directory name and a candidate directory."""
    old_clean = _VERSION_TOKEN_RE.sub("", old_name.lower()).strip(" _-.")
    new_clean = _VERSION_TOKEN_RE.sub("", new_name.lower()).strip(" _-.")
    if old_clean and old_clean == new_clean:
        return 1.0
    return SequenceMatcher(None, old_name.lower(), new_name.lower()).ratio()
