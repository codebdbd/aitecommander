"""Compatibility wrapper for legacy `app.models.category_model` imports."""

from app.models.entities.category_model import CategoryModel  # noqa: F401

__all__ = ["CategoryModel"]
