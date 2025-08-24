"""Строители меню для приложения."""

from .category_menu_builder import CategoryMenuBuilder
from .links_menu_builder import LinksMenuBuilder
from .main_menu_builder import MainMenuBuilder
from .menu_actions import ActionBuilder, Shortcuts, StructureItemType
from .structure_menu_builder import StructureMenuBuilder

__all__ = [
    "MainMenuBuilder",
    "StructureMenuBuilder",
    "LinksMenuBuilder",
    "CategoryMenuBuilder",
    "ActionBuilder",
    "Shortcuts",
    "StructureItemType",
]
