"""Qt utility functions for topbar components.

Provides safe wrappers for Qt object lifecycle management and deletion detection.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Enhanced sip.isdeleted() fallback with improved performance and logging
try:
    from sip import isdeleted as _sip_isdeleted

    _SIP_AVAILABLE = True
    logger.debug("sip.isdeleted() available - using native implementation")
except ImportError:
    _SIP_AVAILABLE = False
    _SIP_FALLBACK_WARNED = False
    _FALLBACK_CALL_COUNT = 0
    _FALLBACK_ERROR_COUNT = 0

    def _sip_isdeleted(obj: Any) -> bool:
        """Enhanced fallback when sip.isdeleted() is unavailable.

        Uses multiple detection strategies for better reliability:
        1. None check (fastest)
        2. Qt attribute access probe
        3. Type checking for non-Qt objects

        Performance: Caches warning to show only once per session.
        Logging: Tracks usage statistics for monitoring.
        """
        global _SIP_FALLBACK_WARNED, _FALLBACK_CALL_COUNT, _FALLBACK_ERROR_COUNT

        # Show warning only once per session
        if not _SIP_FALLBACK_WARNED:
            logger.info(
                "sip.isdeleted() unavailable - using enhanced fallback detection. "
                "For optimal performance, install PyQt6 with sip: "
                "pip install PyQt6[sip]"
            )
            _SIP_FALLBACK_WARNED = True

        _FALLBACK_CALL_COUNT += 1

        # Fast path: None check
        if obj is None:
            return True

        # Fast path: Non-QObject types are never "deleted" in Qt sense
        if not hasattr(obj, "parent"):
            return False

        # Qt object deletion detection
        try:
            # Multiple attribute probes for better detection
            # Different Qt objects may have different available attributes
            for attr in ("parent", "objectName", "isVisible"):
                if hasattr(obj, attr):
                    _ = getattr(obj, attr)
                    if callable(_):
                        _ = _()  # Call method if it's callable
                    break
            else:
                # No recognizable Qt attributes - assume not deleted
                return False
            return False
        except RuntimeError as e:
            # Qt object deleted: "wrapped C/C++ object has been deleted"
            if "deleted" in str(e).lower():
                return True
            # Other RuntimeError - object might still be valid
            _FALLBACK_ERROR_COUNT += 1
            return False
        except (AttributeError, TypeError):
            # Not a Qt object or attribute unavailable
            return False
        except Exception:
            # Unexpected error - assume object is valid to be safe
            _FALLBACK_ERROR_COUNT += 1
            return False


def is_deleted(obj: Any) -> bool:
    """Check if a Qt object has been deleted.

    Args:
        obj: Qt object to check.

    Returns:
        True if the object is None or has been deleted by Qt.

    Example:
        >>> widget = QWidget()
        >>> is_deleted(widget)
        False
        >>> widget.deleteLater()
        >>> # After event loop processes deletion
        >>> is_deleted(widget)
        True
    """
    return _sip_isdeleted(obj)


def get_sip_statistics() -> dict[str, Any]:
    """Get sip.isdeleted() usage statistics for monitoring.

    Returns:
        Dictionary with statistics about sip usage and fallback performance.
        Keys: sip_available, total_calls, error_count, success_rate.

    Example:
        >>> stats = get_sip_statistics()
        >>> print(f"SIP available: {stats['sip_available']}")
        >>> print(f"Success rate: {stats['success_rate']:.1f}%")
    """
    if _SIP_AVAILABLE:
        return {
            "sip_available": True,
            "total_calls": 0,
            "error_count": 0,
            "success_rate": 100.0,
        }

    return {
        "sip_available": False,
        "total_calls": _FALLBACK_CALL_COUNT,
        "error_count": _FALLBACK_ERROR_COUNT,
        "success_rate": (
            (_FALLBACK_CALL_COUNT - _FALLBACK_ERROR_COUNT)
            / max(_FALLBACK_CALL_COUNT, 1)
        ) * 100,
    }
