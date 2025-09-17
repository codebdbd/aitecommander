"""Исключения для модуля links_ui."""


class LinksUIError(Exception):
    """Базовое исключение для LinksUI."""

    pass


class CategoryNotFoundError(LinksUIError):
    """Категория не найдена."""

    pass


class LinkValidationError(LinksUIError):
    """Ошибка валидации ссылки."""

    pass


class DatabaseError(LinksUIError):
    """Ошибка базы данных."""

    pass
