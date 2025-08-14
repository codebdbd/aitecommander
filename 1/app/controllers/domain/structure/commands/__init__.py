# app/controllers/domain/structure/commands/__init__.py
"""Фасад для команд структуры и ссылок (локальные импорты)."""

from .base import BaseCommand
from .category_commands import (
    SaveCategoryCommand,
    DeleteCategoryCommand,
)
from .link_commands import (
    SaveLinkCommand,
    DeleteLinkCommand,
    BatchSaveLinksCommand,
)
from .section_commands import (
    SaveSectionCommand,
    DeleteSectionCommand,
)

__all__ = [
    'BaseCommand',
    'SaveCategoryCommand', 'DeleteCategoryCommand',
    'SaveLinkCommand', 'DeleteLinkCommand', 'BatchSaveLinksCommand',
    'SaveSectionCommand', 'DeleteSectionCommand',
]
