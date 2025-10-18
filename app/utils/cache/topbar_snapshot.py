"""Disk-backed snapshot storage for top bar panels."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config_data import app_config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TopBarSnapshot:
    """Serializable snapshot of favorites and recent links."""

    favorites: list[dict[str, Any]] = field(default_factory=list)
    recents: list[dict[str, Any]] = field(default_factory=list)
    saved_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    version: int = 1

    def to_json(self) -> dict[str, Any]:
        """Convert snapshot to JSON-serialisable structure."""
        return {
            "version": self.version,
            "saved_at": self.saved_at.isoformat(),
            "favorites": self.favorites,
            "recents": self.recents,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TopBarSnapshot | None":
        """Create snapshot from JSON payload if it is valid."""
        if not isinstance(payload, dict):
            return None

        version = payload.get("version", 1)
        if version != 1:
            logger.debug(
                "TopBarSnapshot: unsupported version %s", version
            )
            return None

        favorites = payload.get("favorites", [])
        recents = payload.get("recents", [])
        saved_at_raw = payload.get("saved_at")

        if not isinstance(favorites, list) or not isinstance(recents, list):
            return None

        try:
            if isinstance(saved_at_raw, str):
                saved_at = datetime.fromisoformat(saved_at_raw)
            else:
                saved_at = datetime.now(timezone.utc)
        except ValueError:
            saved_at = datetime.now(timezone.utc)

        # Ensure nested items are dicts to avoid surprises later.
        fav_list: list[dict[str, Any]] = []
        for item in favorites:
            if isinstance(item, dict):
                fav_list.append(item)

        rec_list: list[dict[str, Any]] = []
        for item in recents:
            if isinstance(item, dict):
                rec_list.append(item)

        return cls(
            favorites=fav_list,
            recents=rec_list,
            saved_at=saved_at,
            version=version,
        )


class TopBarSnapshotStore:
    """Manage persistence of top bar snapshots."""

    _FILENAME = "topbar_snapshot.json"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._path: Path | None = None

    def _get_snapshot_path(self) -> Path:
        if self._path is None:
            root = app_config.paths.get_user_data_dir() / "cache"
            root.mkdir(parents=True, exist_ok=True)
            self._path = root / self._FILENAME
        return self._path

    def load(self) -> TopBarSnapshot | None:
        """Load snapshot from disk."""
        path = self._get_snapshot_path()
        if not path.exists():
            return None

        with self._lock:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "TopBarSnapshotStore: failed to read %s: %s", path, exc
                )
                return None

        snapshot = TopBarSnapshot.from_payload(payload)
        if snapshot:
            logger.debug(
                "TopBarSnapshotStore: loaded snapshot (%s favorites, %s recents)",
                len(snapshot.favorites),
                len(snapshot.recents),
            )
        return snapshot

    def save(self, snapshot: TopBarSnapshot) -> None:
        """Persist snapshot atomically."""
        path = self._get_snapshot_path()
        payload = snapshot.to_json()

        with self._lock:
            tmp_path = path.with_suffix(".tmp")
            try:
                tmp_path.write_text(
                    json.dumps(payload, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp_path.replace(path)
                logger.debug(
                    "TopBarSnapshotStore: saved snapshot (%s favorites, %s recents)",
                    len(snapshot.favorites),
                    len(snapshot.recents),
                )
            except OSError as exc:
                logger.warning(
                    "TopBarSnapshotStore: failed to write snapshot: %s", exc
                )
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def clear(self) -> None:
        """Delete snapshot file if present."""
        path = self._get_snapshot_path()
        with self._lock:
            try:
                path.unlink(missing_ok=True)
                logger.debug("TopBarSnapshotStore: snapshot cleared")
            except OSError as exc:
                logger.debug(
                    "TopBarSnapshotStore: failed to clear snapshot: %s", exc
                )
