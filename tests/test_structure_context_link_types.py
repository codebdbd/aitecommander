from __future__ import annotations

from app.services.structure_context_service import StructureContextService


def test_prepare_link_payload_normalizes_unknown_link_type() -> None:
    service = StructureContextService.__new__(StructureContextService)

    payload = service._prepare_link_payload(
        {"name": "Imported", "url": "https://example.com", "type": "mystery"},
        category_id=10,
    )

    assert payload is not None
    assert payload["type"] == "web"


def test_prepare_link_payload_preserves_note_link_type() -> None:
    service = StructureContextService.__new__(StructureContextService)

    payload = service._prepare_link_payload(
        {
            "name": "Note",
            "url": "note://local",
            "type": "note",
            "notes": "body",
        },
        category_id=10,
    )

    assert payload is not None
    assert payload["type"] == "note"
    assert payload["notes"] == "body"


def test_link_key_uses_normalized_type() -> None:
    service = StructureContextService.__new__(StructureContextService)

    assert service._link_key_from_record(
        {"name": "A", "url": "u", "type": "unknown", "args": ""}
    ) == ("u", "web", "", "A")
