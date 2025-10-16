"""Compatibility wrapper for legacy `app.models.link_model` imports."""

from app.models.entities.link_model import LinkModel  # noqa: F401

__all__ = ["LinkModel"]
