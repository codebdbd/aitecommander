"""Compatibility wrapper for legacy `app.models.sphere_model` imports."""

from app.models.entities.sphere_model import SphereModel  # noqa: F401

__all__ = ["SphereModel"]
