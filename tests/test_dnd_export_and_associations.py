"""Unit tests for drag-and-drop export, import destination dialog and file associations."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QModelIndex, QMimeData, Qt
from PyQt6.QtWidgets import QApplication

from app.services.file_association_service import FileAssociationService
from app.views.dialogs.import_destination_dialog import ImportDestinationDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_file_association_command_and_paths():
    """Verify open command and icon path formatting."""
    cmd = FileAssociationService._get_open_command()
    assert "%1" in cmd

    icon = FileAssociationService._get_icon_path()
    assert isinstance(icon, str)
    if icon:
        assert icon.endswith(".ico") or ",0" in icon


def test_import_destination_dialog_section(qapp):
    """Test destination dialog configured for section package."""
    spheres = [
        {"id": 1, "name": "Work"},
        {"id": 2, "name": "Personal"},
    ]
    dlg = ImportDestinationDialog(
        parent=None,
        package_type="section",
        item_name="My Section",
        spheres=spheres,
        sections_by_sphere={},
        default_sphere_id=2,
    )

    assert dlg.get_selected_sphere_id() == 2
    assert dlg.get_selected_section_id() is None
    # Section combo should not be instantiated for sections
    assert dlg.section_combo is None


def test_import_destination_dialog_category(qapp):
    """Test destination dialog configured for category package with dependent sections."""
    spheres = [
        {"id": 1, "name": "Work"},
        {"id": 2, "name": "Personal"},
    ]
    sections_by_sphere = {
        1: [{"id": 101, "name": "Work Sec 1"}, {"id": 102, "name": "Work Sec 2"}],
        2: [{"id": 201, "name": "Personal Sec 1"}],
    }

    dlg = ImportDestinationDialog(
        parent=None,
        package_type="category",
        item_name="My Category",
        spheres=spheres,
        sections_by_sphere=sections_by_sphere,
        default_sphere_id=1,
        default_section_id=102,
    )

    assert dlg.get_selected_sphere_id() == 1
    assert dlg.get_selected_section_id() == 102

    # Switch to sphere 2
    dlg.sphere_combo.setCurrentIndex(1)
    assert dlg.get_selected_sphere_id() == 2
    assert dlg.get_selected_section_id() == 201


def test_import_destination_dialog_category_empty_sphere(qapp):
    """Verify that Ok button is disabled when selected sphere has no sections."""
    from PyQt6.QtWidgets import QDialogButtonBox

    spheres = [
        {"id": 1, "name": "Empty Sphere"},
    ]
    sections_by_sphere = {1: []}

    dlg = ImportDestinationDialog(
        parent=None,
        package_type="category",
        item_name="My Category",
        spheres=spheres,
        sections_by_sphere=sections_by_sphere,
        default_sphere_id=1,
    )

    ok_btn = dlg.btn_box.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok_btn.isEnabled()


def test_inspect_package_extracts_actual_names(tmp_path: Path):
    """Verify that inspect_package properly extracts actual entity names from data.json."""
    from app.services.structure_share_service import StructureShareService

    service = StructureShareService(MagicMock())

    # 1. Section archive
    sec_data = {
        "section": {"id": 1, "name": "Учеба и Наука"},
        "categories": [],
    }
    sec_file = tmp_path / "custom_sec.aitesec"
    service._write_archive("section", sec_data, sec_file)

    manifest_sec = service.inspect_package(sec_file)
    assert manifest_sec["package_type"] == "section"
    assert manifest_sec["item_name"] == "Учеба и Наука"

    # 2. Category archive
    cat_data = {
        "category": {"id": 10, "name": "Музыка и Звук"},
        "links": [],
    }
    cat_file = tmp_path / "custom_cat.aitecat"
    service._write_archive("category", cat_data, cat_file)

    manifest_cat = service.inspect_package(cat_file)
    assert manifest_cat["package_type"] == "category"
    assert manifest_cat["item_name"] == "Музыка и Звук"


def test_file_association_registry_lifecycle():
    """Verify registration, verification and unregistration in Windows registry (HKCU)."""
    if not FileAssociationService.is_supported():
        pytest.skip("Windows only test")

    # Save original state
    was_registered = FileAssociationService.is_registered()

    try:
        # Register
        assert FileAssociationService.register_associations() is True
        assert FileAssociationService.is_registered() is True

        # Unregister
        assert FileAssociationService.unregister_associations() is True
        assert FileAssociationService.is_registered() is False
    finally:
        # Restore state
        if was_registered:
            FileAssociationService.register_associations()
        else:
            FileAssociationService.unregister_associations()
