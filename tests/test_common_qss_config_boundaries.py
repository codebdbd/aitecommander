from __future__ import annotations

from pathlib import Path
import re


QSS_BLOCK_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", re.MULTILINE)


def _load_common_qss() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "app" / "resources" / "qss" / "common.qss").read_text(
        encoding="utf-8"
    )


def _collect_selector_properties(qss_text: str) -> dict[str, set[str]]:
    selector_props: dict[str, set[str]] = {}
    for match in QSS_BLOCK_RE.finditer(qss_text):
        selectors = [
            selector.strip()
            for selector in match.group("selectors").split(",")
            if selector.strip()
        ]
        body = match.group("body")
        props = {
            prop.strip().lower()
            for prop in re.findall(r"([A-Za-z-]+)\s*:", body)
            if prop.strip()
        }
        for selector in selectors:
            selector_props.setdefault(selector, set()).update(props)
    return selector_props


def test_common_qss_does_not_override_config_owned_menu_and_header_metrics() -> None:
    selector_props = _collect_selector_properties(_load_common_qss())

    config_owned_props = {
        "QMenu": {"font-size"},
        "QMenu::item": {"font-size", "min-height", "max-height"},
        "QMenuBar": {"font-size", "min-height", "max-height"},
        "QMenuBar::item": {"font-size", "min-height", "max-height"},
        "QMenuBar::item:selected": {"font-size", "min-height", "max-height"},
        "QMenuBar::item:hover": {"font-size", "min-height", "max-height"},
        "QMenuBar::item:pressed": {"font-size", "min-height", "max-height"},
        "QHeaderView": {"font-size"},
        "QTableView QHeaderView": {"font-size"},
        "QTreeView QHeaderView": {"font-size"},
    }

    violations: list[str] = []
    for selector, forbidden_props in config_owned_props.items():
        present_props = selector_props.get(selector, set())
        overlap = sorted(present_props & forbidden_props)
        if overlap:
            violations.append(f"{selector}: {', '.join(overlap)}")

    assert not violations, (
        "common.qss must not define config-owned metrics that are generated later "
        f"from app_config overrides: {violations}"
    )


def test_common_qss_has_no_empty_property_values() -> None:
    common_qss = _load_common_qss()
    assert "font-size: ;" not in common_qss
