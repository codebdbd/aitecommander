from __future__ import annotations

import collections
import json
from pathlib import Path
import xml.etree.ElementTree as ET


MessageInfo = collections.namedtuple(
    "MessageInfo",
    "context source translation_state translation_text locations"
)


def load_messages(ts_path: Path) -> list[MessageInfo]:
    tree = ET.parse(ts_path)
    root = tree.getroot()
    messages: list[MessageInfo] = []
    for context in root.findall("context"):
        name_elem = context.find("name")
        if name_elem is None or name_elem.text is None:
            continue
        context_name = name_elem.text
        for message in context.findall("message"):
            source_elem = message.find("source")
            translation_elem = message.find("translation")
            translation_state = translation_elem.get("type") if translation_elem is not None else None
            translation_text = translation_elem.text if translation_elem is not None else None
            locations = [
                {
                    "filename": loc.get("filename"),
                    "line": loc.get("line"),
                }
                for loc in message.findall("location")
            ]
            messages.append(
                MessageInfo(
                    context=context_name,
                    source=source_elem.text if source_elem is not None else None,
                    translation_state=translation_state,
                    translation_text=translation_text,
                    locations=locations,
                )
            )
    return messages


def normalise_key(msg: MessageInfo) -> tuple[str, str | None, tuple[tuple[str | None, str | None], ...]]:
    if msg.source is None:
        location_key = tuple((loc["filename"], loc["line"]) for loc in msg.locations)
        return msg.context, None, location_key
    return msg.context, msg.source, tuple()


def audit_translations(root: Path) -> dict:
    ts_files = sorted(root.glob("app_*.ts"))
    baseline = root / "app_en.ts"
    if baseline not in ts_files:
        raise RuntimeError("Baseline app_en.ts not found")

    reports: dict[str, dict] = {}
    baseline_msgs = load_messages(baseline)
    baseline_index = {normalise_key(msg): msg for msg in baseline_msgs}

    for ts_path in ts_files:
        msgs = load_messages(ts_path)
        key_index = collections.Counter(normalise_key(msg) for msg in msgs)
        missing_sources = [msg for msg in msgs if msg.source is None]
        unfinished = [msg for msg in msgs if msg.translation_state in {"unfinished", "vanished"}]
        duplicate_keys = {key: count for key, count in key_index.items() if count > 1}

        missing_from_baseline = []
        extra_vs_baseline = []

        for key in baseline_index:
            if key_index[key] == 0:
                missing_from_baseline.append(key)
        if ts_path != baseline:
            for key in key_index:
                if key not in baseline_index:
                    extra_vs_baseline.append(key)

        total_messages = len(msgs)
        contexts = collections.Counter(msg.context for msg in msgs)

        reports[ts_path.name] = {
            "total_messages": total_messages,
            "contexts": contexts.most_common(),
            "missing_source_entries": len(missing_sources),
            "unfinished_entries": len(unfinished),
            "duplicate_keys": len(duplicate_keys),
            "missing_from_baseline": missing_from_baseline,
            "extra_vs_baseline": extra_vs_baseline,
        }

    return {
        "baseline": "app_en.ts",
        "reports": reports,
    }


def main() -> None:
    root = Path("i18n")
    report = audit_translations(root)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
