from __future__ import annotations

import re
from pathlib import Path

TAG_PATTERN = re.compile(r"<(/?)([A-Za-z0-9_:-]+)([^>]*)>")
SELF_CLOSING = {"location"}


def scan(ts_path: Path) -> None:
    stack: list[tuple[str, int, int]] = []
    text = ts_path.read_text(encoding="utf-8")
    line_starts = [0]
    for idx, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(idx + 1)
    def line_col(pos: int) -> tuple[int, int]:
        import bisect
        line_idx = bisect.bisect_right(line_starts, pos) - 1
        col = pos - line_starts[line_idx] + 1
        return line_idx + 1, col

    for match in TAG_PATTERN.finditer(text):
        closing, name, rest = match.groups()
        pos = match.start()
        line, col = line_col(pos)
        if rest.strip().endswith("/") or name in SELF_CLOSING:
            continue
        if closing:
            if not stack:
                print(f"Extra closing tag </{name}> at {line}:{col}")
                return
            top_name, top_line, top_col = stack.pop()
            if top_name != name:
                print(
                    f"Mismatched closing tag </{name}> at {line}:{col}, expected </{top_name}> opened at {top_line}:{top_col}"
                )
                return
        else:
            stack.append((name, line, col))
    if stack:
        print("Unclosed tag stack:")
        for name, line, col in stack:
            print(f"  <{name}> opened at {line}:{col} not closed")
    else:
        print("No structural mismatches detected by regex scan")


def main() -> None:
    scan(Path("i18n/app_ru.ts"))


if __name__ == "__main__":
    main()
