import logging
import os
import time

from PyQt6.QtCore import QEvent, QObject

_LOGGER = logging.getLogger(__name__)
_ENABLED = os.getenv("AITE_FULL_DIAG", "0").strip().lower() not in {"0", "false", "no"}


def enabled() -> bool:
    return _ENABLED


class FullDiagEventFilter(QObject):
    """Event filter that logs key widget/window lifecycle events."""

    def __init__(self) -> None:
        super().__init__()
        self._paint_counts: dict[str, int] = {}
        self._last_resize_ts: dict[str, float] = {}

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if not _ENABLED:
            return False
        et = event.type()
        if et not in {
            QEvent.Type.Show,
            QEvent.Type.Hide,
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.Paint,
            QEvent.Type.WindowStateChange,
            QEvent.Type.Polish,
            QEvent.Type.LayoutRequest,
        }:
            return False

        name = _diag_name(obj)
        if et == QEvent.Type.Paint:
            count = self._paint_counts.get(name, 0)
            if count >= 3:
                return False
            self._paint_counts[name] = count + 1

        size = _safe_size(obj)
        pos = _safe_pos(obj)
        vis = _safe_visible(obj)
        state = _safe_window_state(obj)

        if et == QEvent.Type.Resize:
            self._last_resize_ts[name] = time.perf_counter()
            _LOGGER.info(
                "[FullDiag] %s Resize size=%s pos=%s vis=%s state=%s",
                name,
                size,
                pos,
                vis,
                state,
            )
            return False

        if et == QEvent.Type.Paint:
            elapsed_ms = _elapsed_ms(self._last_resize_ts.get(name))
            _LOGGER.info(
                "[FullDiag] %s Paint size=%s pos=%s vis=%s state=%s after_resize=%sms",
                name,
                size,
                pos,
                vis,
                state,
                elapsed_ms,
            )
            return False

        _LOGGER.info(
            "[FullDiag] %s %s size=%s pos=%s vis=%s state=%s",
            name,
            _event_name(et),
            size,
            pos,
            vis,
            state,
        )
        return False


def install_on(widget: QObject, name: str, event_filter: FullDiagEventFilter | None) -> None:
    if not _ENABLED or event_filter is None or widget is None:
        return
    try:
        widget.setProperty("diag_name", name)
    except Exception:
        pass
    try:
        widget.installEventFilter(event_filter)
    except Exception:
        _LOGGER.debug("FullDiag: failed to install filter on %s", name, exc_info=True)


def _diag_name(obj: QObject) -> str:
    try:
        prop = obj.property("diag_name")
        if prop:
            return str(prop)
    except Exception:
        pass
    try:
        name = obj.objectName()
        if name:
            return name
    except Exception:
        pass
    return obj.__class__.__name__


def _safe_size(obj: QObject) -> str:
    try:
        size = obj.size()
        return f"{size.width()}x{size.height()}"
    except Exception:
        return "?"


def _safe_pos(obj: QObject) -> str:
    try:
        pos = obj.pos()
        return f"({pos.x()},{pos.y()})"
    except Exception:
        return "?"


def _safe_visible(obj: QObject) -> str:
    try:
        return str(obj.isVisible())
    except Exception:
        return "?"


def _safe_window_state(obj: QObject) -> str:
    try:
        return str(int(obj.windowState()))
    except Exception:
        return "?"


def _event_name(event_type: QEvent.Type) -> str:
    return {
        QEvent.Type.Show: "Show",
        QEvent.Type.Hide: "Hide",
        QEvent.Type.Resize: "Resize",
        QEvent.Type.Move: "Move",
        QEvent.Type.Paint: "Paint",
        QEvent.Type.WindowStateChange: "WindowStateChange",
        QEvent.Type.Polish: "Polish",
        QEvent.Type.LayoutRequest: "LayoutRequest",
    }.get(event_type, str(int(event_type)))


def _elapsed_ms(last_ts: float | None) -> str:
    if last_ts is None:
        return "?"
    return f"{(time.perf_counter() - last_ts) * 1000.0:.1f}"
