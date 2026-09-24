"""Legacy mixin preserved for backward compatibility.

All browser profile modes (Single, Rotation, Batch) are now unified in `ProfilesMixin`.
"""

import logging

logger = logging.getLogger(__name__)


class RotationMixin:
    """Legacy compatibility mixin. Active profile handling is in `ProfilesMixin`."""
    pass
