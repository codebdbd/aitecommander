from __future__ import annotations

import re
from pathlib import Path


def _load_source_map(ts_path: Path) -> dict[tuple[str, tuple[tuple[str | None, str | None], ...]], str]:
    lines = ts_path.read_text(encoding="utf-8").splitlines()
    mapping: dict[tuple[str, tuple[tuple[str | None, str | None], ...]], str] = {}
    context: str | None = None
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("<name>") and stripped.endswith("</name>"):
            context = stripped[len("<name>") : -len("</name>")]
            i += 1
            continue
        if stripped.startswith("<message"):
            block: list[str] = []
            while i < len(lines):
                block.append(lines[i])
                if lines[i].strip() == "</message>":
                    i += 1
                    break
                i += 1
            else:  # pragma: no cover - defensive
                break
            locs: list[tuple[str | None, str | None]] = []
            for row in block:
                row_stripped = row.strip()
                if row_stripped.startswith("<location"):
                    filename_match = re.search(r'filename="([^"]+)"', row_stripped)
                    line_match = re.search(r'line="([^"]+)"', row_stripped)
                    locs.append(
                        (
                            filename_match.group(1) if filename_match else None,
                            line_match.group(1) if line_match else None,
                        )
                    )
            source_line = next((row for row in block if row.strip().startswith("<source>")), None)
            if context and source_line and locs:
                start = source_line.find(">") + 1
                end = source_line.rfind("</source>")
                mapping[(context, tuple(locs))] = source_line[start:end]
            continue
        i += 1
    return mapping


def restore_sources(eng_ts: Path, ru_ts: Path) -> int:
    eng_map = _load_source_map(eng_ts)
    ru_lines = ru_ts.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    context: str | None = None
    i = 0
    inserted = 0
    while i < len(ru_lines):
        line = ru_lines[i]
        stripped = line.strip()
        if stripped.startswith("<name>") and stripped.endswith("</name>"):
            context = stripped[len("<name>") : -len("</name>")]
            output.append(line)
            i += 1
            continue
        if stripped.startswith("<message"):
            block: list[str] = []
            while i < len(ru_lines):
                block.append(ru_lines[i])
                if ru_lines[i].strip() == "</message>":
                    i += 1
                    break
                i += 1
            else:  # pragma: no cover - defensive
                break
            if context and not any(row.strip().startswith("<source>") for row in block):
                locations: list[tuple[str | None, str | None]] = []
                for row in block:
                    row_stripped = row.strip()
                    if row_stripped.startswith("<location"):
                        filename_match = re.search(r'filename="([^"]+)"', row_stripped)
                        line_match = re.search(r'line="([^"]+)"', row_stripped)
                        locations.append(
                            (
                                filename_match.group(1) if filename_match else None,
                                line_match.group(1) if line_match else None,
                            )
                        )
                key = (context, tuple(locations))
                source_text = eng_map.get(key)
                if source_text:
                    for idx, row in enumerate(block):
                        if row.strip().startswith("<translation"):
                            indent = row[: len(row) - len(row.lstrip())]
                            block.insert(idx, f"{indent}<source>{source_text}</source>")
                            inserted += 1
                            break
            output.extend(block)
            continue
        output.append(line)
        i += 1
    if inserted:
        ru_ts.write_text("\n".join(output) + "\n", encoding="utf-8")
    return inserted


def main() -> None:
    root = Path("i18n")
    inserted = restore_sources(root / "app_en.ts", root / "app_ru.ts")
    print(f"Inserted {inserted} <source> tags")


if __name__ == "__main__":
    main()
