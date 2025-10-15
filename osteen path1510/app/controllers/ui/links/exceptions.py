"""Exceptions for links_ui module."""


class LinksUIError(Exception):
    """Base exception for LinksUI."""

    pass


class CategoryNotFoundError(LinksUIError):
    """Category not found."""

    pass


class LinkValidationError(LinksUIError):
    """Link validation error."""

    pass


class DatabaseError(LinksUIError):
    """Database error."""

    pass
