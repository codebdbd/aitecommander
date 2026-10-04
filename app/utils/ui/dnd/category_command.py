"""Команда перемещения одиночной категории (обёртка над MoveCategoriesCommand)."""

from __future__ import annotations

from app.utils.ui.dnd.categories_command import MoveCategoriesCommand


class MoveCategoryCommand(MoveCategoriesCommand):
    """Move single category between sections, delegating to MoveCategoriesCommand."""

    def __init__(self, category_id, new_section_id, main_window) -> None:
        super().__init__(
            category_ids=[category_id],
            new_section_id=new_section_id,
            target_row=0,
            main_window=main_window,
        )
