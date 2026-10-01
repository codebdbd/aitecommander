"""Unit tests for DialogPathService initial directory resolution and memory."""

from pathlib import Path
from PyQt6.QtCore import QSettings

from app.services.dialog_path_service import DialogPathService


def test_dialog_path_service_programs_dir_exists() -> None:
    """DialogPathService.get_programs_dir must return an existing directory."""
    prog_dir = DialogPathService.get_programs_dir()
    assert prog_dir
    assert Path(prog_dir).is_dir()


def test_dialog_path_service_downloads_dir_exists() -> None:
    """DialogPathService.get_downloads_dir must return an existing directory."""
    dl_dir = DialogPathService.get_downloads_dir("TestContext")
    assert dl_dir
    assert Path(dl_dir).is_dir()


def test_dialog_path_service_remembers_last_directory(tmp_path: Path) -> None:
    """remember_dir must save the folder into QSettings and get_downloads_dir must recall it."""
    test_context = "CustomTestingContext_123"
    custom_folder = tmp_path / "SubFolder"
    custom_folder.mkdir()
    sample_file = custom_folder / "test_file.txt"
    sample_file.write_text("hello")

    # Remember the folder of sample_file
    DialogPathService.remember_dir(test_context, sample_file)

    recalled = DialogPathService.get_downloads_dir(test_context)
    assert recalled == str(custom_folder)

    # Clean up QSettings
    QSettings().remove(f"FilePicker/LastDir_{test_context}")
