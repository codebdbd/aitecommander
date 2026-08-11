"""Background icon enrichment for persisted links."""

from __future__ import annotations

import logging
import os
import weakref
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QCoreApplication, QObject, QRunnable, pyqtSignal, pyqtSlot

from app.config_data.runtime_config import runtime_app_config as app_config
from app.controllers.ui.state.task_scheduler import get_task_scheduler
from app.models import LinkType
from app.utils.links.link_parser import parse_local_link
from app.utils.links.parser.fetcher import fetch_web_link_info
from app.utils.ui.db_tasks import run_db
from app.utils.ui.icon.icon_resolver import resolve_icon_for_link

logger = logging.getLogger(__name__)


def _normalized_path(value: object) -> str:
    raw = str(value or "").strip()
    return os.path.normcase(os.path.abspath(raw)) if raw else ""


def _can_replace_icon(link: dict[str, Any]) -> bool:
    """Return whether an automatically resolved icon may replace the current one."""
    link_type = str(link.get("type") or link.get("link_type") or LinkType.WEB.value)
    current = str(link.get("icon_path") or "").strip()
    if not current:
        return True
    try:
        default = resolve_icon_for_link({"type": link_type, "icon_path": ""}) or ""
        resolved_current = resolve_icon_for_link(link) or ""
    except Exception:
        default = ""
        resolved_current = ""
    return bool(
        default
        and resolved_current
        and _normalized_path(resolved_current) == _normalized_path(default)
    )


class _FetchIconTask(QRunnable):
    def __init__(
        self,
        service: "LinkIconEnrichmentService",
        link_id: int,
        url: str,
        link_type: str,
        generation: int,
    ) -> None:
        super().__init__()
        self._service_ref = weakref.ref(service)
        self._link_id = link_id
        self._url = url
        self._link_type = link_type
        self._generation = generation

    def run(self) -> None:
        icon_path = ""
        try:
            if self._link_type == LinkType.WEB.value:
                info = fetch_web_link_info(
                    self._url,
                    app_config,
                    force_refresh=True,
                    defer_icon=False,
                )
            else:
                info = parse_local_link(self._link_type, self._url, app_config)
            candidate = str(info.get("icon") or "").strip()
            if (
                candidate
                and Path(candidate).exists()
                and not _can_replace_icon(
                    {"type": self._link_type, "icon_path": candidate}
                )
            ):
                icon_path = candidate
        except Exception:
            logger.exception(
                "Background icon parsing failed for %s (%s)",
                self._url,
                self._link_type,
            )

        service = self._service_ref()
        if service is not None:
            service._network_finished.emit(
                {
                    "link_id": self._link_id,
                    "url": self._url,
                    "link_type": self._link_type,
                    "generation": self._generation,
                    "icon_path": icon_path,
                }
            )


class LinkIconEnrichmentService(QObject):
    """Own favicon jobs independently from dialogs and update saved links."""

    _network_finished = pyqtSignal(object)

    def __init__(self, main_window: Any) -> None:
        parent = main_window if isinstance(main_window, QObject) else None
        super().__init__(parent)
        self._main_ref = weakref.ref(main_window)
        self._generation_by_link: dict[int, int] = {}
        self._network_finished.connect(self._on_network_finished)

    def enqueue(self, link: dict[str, Any]) -> bool:
        link_id = link.get("id")
        url = str(link.get("url") or "").strip()
        link_type = str(link.get("type") or link.get("link_type") or "").lower()
        if (
            not isinstance(link_id, int)
            or link_id <= 0
            or link_type
            not in {LinkType.WEB.value, LinkType.PROGRAM.value, LinkType.FILE.value}
            or not url
            or not _can_replace_icon(link)
        ):
            return False

        generation = self._generation_by_link.get(link_id, 0) + 1
        self._generation_by_link[link_id] = generation
        get_task_scheduler().submit_task(
            _FetchIconTask(self, link_id, url, link_type, generation)
        )
        return True

    @pyqtSlot(object)
    def _on_network_finished(self, result: object) -> None:
        if not isinstance(result, dict):
            return
        link_id = result.get("link_id")
        generation = result.get("generation")
        url = str(result.get("url") or "")
        link_type = str(result.get("link_type") or "")
        icon_path = str(result.get("icon_path") or "")
        if not isinstance(link_id, int) or self._generation_by_link.get(link_id) != generation:
            return
        if not icon_path or not Path(icon_path).exists():
            self._generation_by_link.pop(link_id, None)
            return

        main = self._main_ref()
        links_business = getattr(main, "links_business", None) if main is not None else None
        links_service = getattr(links_business, "links", None)
        if links_service is None:
            self._generation_by_link.pop(link_id, None)
            return

        def _persist_if_current() -> dict[str, Any] | None:
            current_raw = links_service.get_link_by_id(link_id)
            current = dict(current_raw) if current_raw else None
            if (
                not current
                or str(current.get("url") or "") != url
                or str(current.get("type") or "") != link_type
            ):
                return None
            if not _can_replace_icon(current):
                return None
            current["icon_path"] = Path(icon_path).name
            links_service.create_or_update_link(current)
            refreshed = links_service.get_link_by_id(link_id)
            return dict(refreshed) if refreshed else current

        run_db(
            _persist_if_current,
            description=f"persist_favicon:{link_id}",
            on_finished=lambda updated: self._publish_update(
                link_id, generation, updated
            ),
            on_error=lambda exc: self._finish_with_error(link_id, generation, exc),
        )

    def _finish_with_error(self, link_id: int, generation: int, exc: Exception) -> None:
        if self._generation_by_link.get(link_id) == generation:
            self._generation_by_link.pop(link_id, None)
        logger.warning("Failed to persist favicon for link %s: %s", link_id, exc)

    def _publish_update(
        self,
        link_id: int,
        generation: int,
        updated: object,
    ) -> None:
        if self._generation_by_link.get(link_id) != generation:
            return
        self._generation_by_link.pop(link_id, None)
        if not isinstance(updated, dict):
            return

        main = self._main_ref()
        if main is None:
            return
        links_business = getattr(main, "links_business", None)
        try:
            if links_business is not None:
                invalidate = getattr(links_business, "invalidate_cache", None)
                if not callable(invalidate):
                    invalidate = getattr(links_business, "_invalidate_cache", None)
                if callable(invalidate):
                    invalidate()
                links_business.link_updated.emit(updated)
        except Exception:
            logger.debug("Failed to publish favicon business update", exc_info=True)

        link_ops = getattr(main, "link_operations", None)
        try:
            if link_ops is not None and hasattr(link_ops, "emit_link_saved"):
                link_ops.emit_link_saved(updated)
            if link_ops is not None and hasattr(link_ops, "emit_top_panels_changed"):
                link_ops.emit_top_panels_changed(favorites=True, recents=True)
        except Exception:
            logger.debug("Failed to publish favicon UI update", exc_info=True)


def enqueue_link_icon_enrichment(main_window: Any, link: dict[str, Any]) -> bool:
    """Queue favicon parsing after a link has a stable database id."""
    if QCoreApplication.instance() is None or main_window is None:
        return False
    service = getattr(main_window, "_link_icon_enrichment_service", None)
    if not isinstance(service, LinkIconEnrichmentService):
        service = LinkIconEnrichmentService(main_window)
        setattr(main_window, "_link_icon_enrichment_service", service)
    return service.enqueue(link)


__all__ = ["LinkIconEnrichmentService", "enqueue_link_icon_enrichment"]
