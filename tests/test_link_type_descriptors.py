from __future__ import annotations

from app.config_data.settings_config import SettingsConfig
from app.models.types.link_type import LinkType
from app.utils.links.type_labels import (
    LINK_TYPE_DESCRIPTORS,
    link_type_address_tooltip,
    translate_link_type_label,
)


def test_link_type_descriptors_cover_link_type_enum() -> None:
    descriptor_keys = {descriptor.key for descriptor in LINK_TYPE_DESCRIPTORS}

    assert descriptor_keys == {item.value for item in LinkType}


def test_settings_link_type_choices_use_same_labels_as_table() -> None:
    config = SettingsConfig({})
    choices = config.get_link_types()

    assert [choice[0] for choice in choices] == [
        descriptor.key for descriptor in LINK_TYPE_DESCRIPTORS
    ]
    assert {key: label for key, label in choices} == {
        descriptor.key: translate_link_type_label(descriptor.key)
        for descriptor in LINK_TYPE_DESCRIPTORS
    }


def test_quick_types_follow_same_descriptor_order_and_icons() -> None:
    config = SettingsConfig({})
    quick_types = config.get_quick_types()

    assert quick_types == [
        [
            descriptor.key,
            descriptor.default_icon,
            translate_link_type_label(descriptor.key),
        ]
        for descriptor in LINK_TYPE_DESCRIPTORS
    ]


def test_note_type_tooltip_prefers_note_text() -> None:
    tooltip = link_type_address_tooltip(
        {
            "type": "note",
            "url": "https://example.invalid",
            "notes": "Important note body",
        }
    )

    assert tooltip == "Important note body"
