"""Fast, Unicode-aware search and ranking service for the Command Palette."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.models.base.db_base import row_to_dict

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedPaletteQuery:
    """Structured representation of a command palette search query."""

    raw: str
    text: str
    type_filter: frozenset[str] | None = None
    sphere_filter: str = ""


def parse_palette_query(query: str) -> ParsedPaletteQuery:
    """Parse prefix operators ('>', '/', '@sphere') from a palette query string."""
    raw = query or ""
    rem = raw.strip()
    if not rem:
        return ParsedPaletteQuery(raw=raw, text="")

    type_filter: frozenset[str] | None = None
    sphere_filter = ""

    # Support combining @sphere and > or / in any order at the start of the query
    for _ in range(2):
        if rem.startswith(">"):
            type_filter = frozenset({"script"})
            rem = rem[1:].strip()
        elif rem.startswith("/"):
            type_filter = frozenset({"file", "folder", "program"})
            rem = rem[1:].strip()
        elif rem.startswith("@"):
            rest = rem[1:].strip()
            if not rest:
                rem = ""
                break
            parts = rest.split(maxsplit=1)
            sphere_filter = parts[0].casefold()
            rem = parts[1].strip() if len(parts) > 1 else ""
        else:
            break

    return ParsedPaletteQuery(
        raw=raw,
        text=rem,
        type_filter=type_filter,
        sphere_filter=sphere_filter,
    )


def _fuzzy_subsequence_score(needle: str, haystack: str) -> int:
    """Return a positive score if all chars of needle appear in order in haystack, else 0."""
    if not needle or not haystack:
        return 0
    n_len = len(needle)
    h_len = len(haystack)
    if n_len > h_len:
        return 0

    n_idx = 0
    first_match = -1
    last_match = -1
    consecutive_bonus = 0
    prev_match = -2

    for h_idx, ch in enumerate(haystack):
        if ch == needle[n_idx]:
            if first_match == -1:
                first_match = h_idx
            if h_idx == prev_match + 1:
                consecutive_bonus += 12
            prev_match = h_idx
            last_match = h_idx
            n_idx += 1
            if n_idx == n_len:
                break

    if n_idx < n_len:
        return 0

    span = max(1, last_match - first_match + 1)
    gap_penalty = max(0, span - n_len) * 3
    start_bonus = 20 if first_match == 0 else 0
    return max(10, 80 + consecutive_bonus + start_bonus - gap_penalty)


def _score_item(item: dict[str, Any], query_cf: str, tokens_cf: list[str]) -> int:
    """Calculate relevance score for a link dictionary against casefolded query."""
    name_cf = str(item.get("name") or "").casefold()
    url_cf = str(item.get("url") or "").casefold()
    notes_cf = str(item.get("notes") or "").casefold()
    args_cf = str(item.get("args") or "").casefold()
    cat_cf = str(item.get("category_name") or "").casefold()
    sect_cf = str(item.get("section_name") or "").casefold()
    sph_cf = str(item.get("sphere_name") or "").casefold()

    combined_haystack = f"{name_cf} {cat_cf} {sect_cf} {sph_cf} {url_cf} {notes_cf} {args_cf}"

    # Every token must match either as a substring in any field or as a fuzzy subsequence in name
    total_score = 0
    for tok in tokens_cf:
        if tok in name_cf:
            total_score += 120
        elif tok in cat_cf or tok in sect_cf or tok in sph_cf:
            total_score += 80
        elif tok in url_cf or tok in notes_cf or tok in args_cf:
            total_score += 50
        else:
            fuzzy = _fuzzy_subsequence_score(tok, name_cf)
            if fuzzy <= 0 and tok not in combined_haystack:
                return 0
            total_score += fuzzy

    # Whole-query bonuses on name
    if name_cf == query_cf:
        total_score += 1000
    elif name_cf.startswith(query_cf):
        total_score += 600
    else:
        words = name_cf.replace("_", " ").replace("-", " ").split()
        if any(w.startswith(query_cf) for w in words):
            total_score += 400
        elif query_cf in name_cf:
            total_score += 300
        else:
            fuzzy_full = _fuzzy_subsequence_score(query_cf, name_cf)
            total_score += fuzzy_full

    if query_cf in cat_cf or query_cf in sph_cf:
        total_score += 100

    # Metadata tie-breakers
    if int(item.get("is_favorite") or 0) == 1:
        total_score += 25
    if item.get("last_used"):
        total_score += 15

    return total_score


class CommandPaletteService:
    """Service that loads link hierarchy snapshots and ranks results for the palette."""

    _SNAPSHOT_SQL = (
        "SELECT l.*, "
        "cat.name AS category_name, "
        "sect.id AS section_id, sect.name AS section_name, "
        "sph.id AS sphere_id, sph.name AS sphere_name "
        "FROM link l "
        "JOIN category cat ON l.category_id = cat.id "
        "JOIN section sect ON cat.section_id = sect.id "
        "JOIN sphere sph ON sect.sphere_id = sph.id "
        "ORDER BY sph.position ASC, sect.position ASC, cat.position ASC, l.position ASC"
    )

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._snapshot: list[dict[str, Any]] = []

    def set_database(self, db: Any) -> None:
        self._db = db

    def set_db(self, db: Any) -> None:
        self._db = db

    def refresh_snapshot(self) -> list[dict[str, Any]]:
        """Fetch all links with their Sphere/Section/Category hierarchy from SQLite."""
        db = self._db
        if db is None:
            self._snapshot = []
            return []

        executor = getattr(db, "links", None) or getattr(db, "_base", None) or db
        exec_fn = getattr(executor, "_execute_with_error_handling", None)
        if not callable(exec_fn):
            self._snapshot = []
            return []

        try:
            rows = exec_fn(self._SNAPSHOT_SQL, (), fetch_method="all")
            self._snapshot = [row_to_dict(r) for r in (rows or [])]
        except Exception as exc:
            logger.error("CommandPaletteService: failed to load snapshot: %s", exc)
            self._snapshot = []
        return list(self._snapshot)

    def set_snapshot(self, items: list[dict[str, Any]]) -> None:
        """Directly set snapshot items (useful for testing or cached state)."""
        self._snapshot = list(items or [])

    def set_snapshot_for_testing(self, items: list[dict[str, Any]]) -> None:
        """Alias for set_snapshot used in unit tests."""
        self.set_snapshot(items)

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Filter and rank snapshot links according to query and prefix operators."""
        if refresh or not self._snapshot:
            if self._db is not None and (refresh or not self._snapshot):
                self.refresh_snapshot()

        parsed = parse_palette_query(query)
        candidates = self._snapshot

        if parsed.type_filter is not None:
            candidates = [
                item
                for item in candidates
                if str(item.get("type") or "").strip().lower() in parsed.type_filter
            ]

        if parsed.sphere_filter:
            sph_needle = parsed.sphere_filter
            candidates = [
                item
                for item in candidates
                if sph_needle in str(item.get("sphere_name") or "").casefold()
            ]

        max_items = max(1, int(limit)) if limit and int(limit) > 0 else 10

        if not parsed.text:
            # Default view: recently used & favorites first, preserving hierarchy order as fallback
            indexed = list(enumerate(candidates))
            indexed.sort(
                key=lambda pair: (
                    1 if pair[1].get("last_used") else 0,
                    str(pair[1].get("last_used") or ""),
                    int(pair[1].get("is_favorite") or 0),
                    -pair[0],
                ),
                reverse=True,
            )
            return [item for _, item in indexed[:max_items]]

        query_cf = parsed.text.casefold()
        tokens_cf = [t for t in query_cf.split() if t]

        scored: list[tuple[int, str, int, int, dict[str, Any]]] = []
        for idx, item in enumerate(candidates):
            score = _score_item(item, query_cf, tokens_cf)
            if score > 0:
                last_used_str = str(item.get("last_used") or "")
                fav_int = int(item.get("is_favorite") or 0)
                scored.append((score, last_used_str, fav_int, -idx, item))

        scored.sort(key=lambda entry: (entry[0], entry[1], entry[2], entry[3]), reverse=True)
        return [entry[4] for entry in scored[:max_items]]
