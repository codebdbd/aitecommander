"""Mixin handling inline script creation and editing inside `LinkDialogHandlers`."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QDialog

from app.services.script_storage_service import ScriptStorageService
from app.views.windows.dialogs.script_editor_dialog import ScriptEditorDialog

logger = logging.getLogger(__name__)


class ScriptEditorMixin:
    """Mixin providing the inline script editor for LinkDialog."""

    def _on_script_editor(self) -> None:
        """Open `ScriptEditorDialog` to paste/edit script code or pick a script file on disk."""
        try:
            current_path_str = self.dialog._get_url_le().text().strip()
            initial_code = ""
            initial_ext = ".ps1"

            existing_file: Path | None = None
            if current_path_str:
                try:
                    candidate = Path(current_path_str)
                    if candidate.is_file():
                        existing_file = candidate.resolve()
                        initial_code, initial_ext = ScriptStorageService.read_script(
                            existing_file
                        )
                except Exception as read_err:
                    logger.debug(
                        "Could not read existing script file '%s': %s",
                        current_path_str,
                        read_err,
                    )

            args_text = self.dialog._get_args_le().text()
            has_existing_script = bool(
                current_path_str or getattr(self.dialog, "link", None)
            )
            if has_existing_script:
                initial_keep_open = bool(
                    getattr(self.dialog, "_script_keep_open", False)
                    or "--keep-open" in args_text
                )
            else:
                initial_keep_open = True

            dlg = ScriptEditorDialog(
                self.dialog,
                initial_code=initial_code,
                initial_ext=initial_ext,
                initial_keep_open=initial_keep_open,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            # Store "Keep console open" choice from ScriptEditorDialog on LinkDialog
            self.dialog._script_keep_open = bool(dlg.get_keep_console_open())

            # Case 1: User selected an existing file from disk via "Find on computer"
            disk_path = dlg.get_selected_disk_path()
            if disk_path:
                self.dialog.ui.set_widget_value("url_le", disk_path)
                name_widget = self.dialog._get_name_le()
                if not name_widget.text().strip():
                    self.dialog.ui.set_widget_value("name_le", Path(disk_path).stem)
                self.dialog._processing_timer.stop()
                self.trigger_link_processing(disk_path)
                return

            # Case 2: User pasted/wrote script code inside the editor
            code = dlg.get_script_code()
            if not code.strip():
                return

            ext = dlg.get_selected_extension()
            name_widget = self.dialog._get_name_le()
            current_name = name_widget.text().strip()
            suggested_name = (
                current_name
                or ScriptStorageService.suggest_script_name(code)
                or (existing_file.stem if existing_file else "")
            )
            if not suggested_name:
                suggested_name = QCoreApplication.translate("LinkDialogUI", "Script")

            created_files: set[Path] = getattr(
                self.dialog, "_created_script_files", set()
            )
            pending_writes: dict[Path, tuple[str, str]] = getattr(
                self.dialog, "_pending_script_writes", {}
            )

            if existing_file is not None and existing_file not in created_files:
                # Defer modifying existing file on disk until user clicks OK in LinkDialog
                pending_writes[existing_file] = (code, ext)
                self.dialog._pending_script_writes = pending_writes
                saved_path = existing_file
            else:
                saved_path = ScriptStorageService.save_script(
                    code=code,
                    ext=ext,
                    name_hint=suggested_name,
                    existing_path=existing_file,
                )
                if existing_file is not None and existing_file != saved_path:
                    if existing_file in created_files:
                        try:
                            existing_file.unlink(missing_ok=True)
                        except Exception:
                            pass
                        created_files.discard(existing_file)
                created_files.add(saved_path)
                self.dialog._created_script_files = created_files

            saved_path_str = str(saved_path)
            self.dialog.ui.set_widget_value("url_le", saved_path_str)
            if not current_name and suggested_name:
                self.dialog.ui.set_widget_value("name_le", suggested_name)

            self.dialog._processing_timer.stop()
            self.trigger_link_processing(saved_path_str)

        except Exception as e:
            logger.error("Error in ScriptEditorMixin._on_script_editor: %s", e, exc_info=True)
