"""Compatibility wrapper for legacy `app.models.section_model` imports."""

from app.models.entities.section_model import SectionModel  # noqa: F401

__all__ = ["SectionModel"]
