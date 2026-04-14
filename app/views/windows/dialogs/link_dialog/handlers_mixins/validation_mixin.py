"""Mixin handling form validation and error reporting for `LinkDialog`."""

import logging
from typing import Any

from PyQt6.QtCore import QCoreApplication

logger = logging.getLogger(__name__)

_TR_CONTEXT = "ValidationMixin"


def _tr(text: str, disambiguation: str | None = None) -> str:
    return QCoreApplication.translate(_TR_CONTEXT, text, disambiguation)


# Reusable field labels for messaging/focus handling
NAME_LABEL = QCoreApplication.translate("ValidationMixin", "Name")
URL_LABEL = QCoreApplication.translate("ValidationMixin", "URL")
LINK_TYPE_LABEL = QCoreApplication.translate("ValidationMixin", "Link type")
CATEGORY_LABEL = QCoreApplication.translate("ValidationMixin", "Category")
ARGS_LABEL = QCoreApplication.translate("ValidationMixin", "Arguments")


class ValidationMixin:
    def _validate_and_save_data(self, form_data: dict[str, Any]) -> dict[str, Any]:
        """Validate and persist form data."""
        if hasattr(self.dialog, "link_controller") and self.dialog.link_controller:
            return self.dialog.link_controller.validate_and_save(form_data)
        else:
            return self.dialog.dialog_controller.validate_and_save(form_data)

    def _handle_validation_errors(
        self, form_data: dict[str, Any], result: dict[str, Any]
    ) -> None:
        """Process validation errors and display appropriate messages."""
        # Soft handling for completely empty form (no URL or name)
        name_empty = not (form_data.get("name") or "").strip()
        url_empty = not (form_data.get("url") or "").strip()

        if name_empty and url_empty:
            self._show_empty_form_message()
        else:
            errors = result.get("errors", [])
            problems = self._extract_problematic_fields(errors)
            self._show_validation_error_message(errors, problems)
            self._focus_problematic_field(problems)

    def _show_empty_form_message(self) -> None:
        """Show message when form is empty."""
        self.dialog.show_info(
            QCoreApplication.translate("ValidationMixin", "The form is empty—add at least a URL or a name before saving."),
            QCoreApplication.translate("ValidationMixin", "Hint"),
            informative_text=QCoreApplication.translate("ValidationMixin", "Enter a URL or a name and try again."),
            silent=True,
        )

    def _extract_problematic_fields(self, errors: list[str]) -> set:
        """Extract problematic fields from validation errors."""
        problems = set()
        lower_errors = [e.lower() for e in errors]
        field_map = {
            "name": NAME_LABEL,
            "url": URL_LABEL,
            "link_type": LINK_TYPE_LABEL,
            "type": LINK_TYPE_LABEL,
            "category": CATEGORY_LABEL,
            "category_id": CATEGORY_LABEL,
            "args": ARGS_LABEL,
        }
        for key, label in field_map.items():
            if any(key in e for e in lower_errors):
                problems.add(label)
        return problems

    def _generate_error_messages(self, problems: set) -> tuple[str, str]:
        """Build primary and informative messages based on problematic fields."""
        hint_map = {
            NAME_LABEL: QCoreApplication.translate("ValidationMixin", "Provide a clear name (for example, 'API documentation')."),
            URL_LABEL: QCoreApplication.translate("ValidationMixin", "Enter a valid URL such as https://example.com."),
            LINK_TYPE_LABEL: QCoreApplication.translate("ValidationMixin", "Choose a link type (web, file, folder, etc.)."),
            CATEGORY_LABEL: QCoreApplication.translate("ValidationMixin", "Select a category for the link."),
            ARGS_LABEL: QCoreApplication.translate("ValidationMixin", "Review launch arguments—only safe values are allowed."),
        }
        hints = [hint_map[p] for p in sorted(problems) if p in hint_map]
        # Limit total hints to avoid overwhelming the dialog
        short_hints = hints[:2]

        if problems:
            main_msg = QCoreApplication.translate("ValidationMixin", "Complete or correct: {fields}.").format(
                fields=", ".join(sorted(problems))
            )
            extra = (" " + " ".join(short_hints)) if short_hints else ""
            info_msg = (
                QCoreApplication.translate("ValidationMixin", "Check the field hints.")
                + extra
                + " "
                + QCoreApplication.translate("ValidationMixin", "Full details are available in the More Information section.")
            )
        else:
            main_msg = QCoreApplication.translate("ValidationMixin", "Please review the data before saving.")
            info_msg = QCoreApplication.translate("ValidationMixin", "Check highlighted fields and tooltip hints.")

        return main_msg, info_msg

    def _show_validation_error_message(self, errors: list[str], problems: set) -> None:
        """Show validation error message to the user."""
        error_text = "\n".join(errors)
        main_msg, info_msg = self._generate_error_messages(problems)

        self.dialog.show_info(
            main_msg,
            QCoreApplication.translate("ValidationMixin", "Quick hint"),
            informative_text=info_msg,
            details=error_text,
            silent=True,
        )

    def _focus_problematic_field(self, problems: set) -> None:
        """Set focus to the first problematic field if possible."""
        try:
            if URL_LABEL in problems:
                self.dialog._get_url_le().setFocus()
            elif NAME_LABEL in problems:
                self.dialog._get_name_le().setFocus()
            elif CATEGORY_LABEL in problems:
                self.dialog._get_category_cb().setFocus()
            elif ARGS_LABEL in problems:
                self.dialog._get_args_le().setFocus()
        except (AttributeError, RuntimeError) as e:
            logger.warning("Failed to set focus to problematic field: %s", e)
