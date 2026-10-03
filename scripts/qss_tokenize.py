"""Developer tool: replace hex literals in theme QSS with ``@token`` placeholders.

Only literals equal to a token of the *same theme* AND of a role compatible with the
CSS property are replaced (text colors -> text tokens, backgrounds -> bg tokens, ...).

Usage:
    python scripts/qss_tokenize.py --dry-run
    python scripts/qss_tokenize.py --apply     # backs up originals to artifacts/qss_backup
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.theme_registry import (  # noqa: E402
    DEFAULT_DARK_TOKENS,
    DEFAULT_LIGHT_TOKENS,
)

TEXT_ROLE = [
    "text_primary",
    "text_secondary",
    "text_muted",
    "text_accent",
    "text_on_accent",
    "selection_fg",
    "status_error",
    "status_warning",
    "status_success",
    "status_info",
]
BG_ROLE = [
    "bg_canvas",
    "bg_surface",
    "bg_header",
    "hover_bg",
    "selection_bg",
    "text_accent",
    "status_error",
    "status_warning",
    "status_success",
    "status_info",
]
BORDER_ROLE = [
    "border_subtle",
    "text_accent",
    "status_error",
    "status_warning",
    "status_success",
    "status_info",
]

DECL_RE = re.compile(r"(?P<prop>[A-Za-z-]+)(?P<sep>\s*:\s*)(?P<val>[^;{}]*)")
HEX_RE = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3}(?:[0-9a-fA-F]{2})?)?\b")


def norm_hex(h: str) -> str:
    h = h.lower()
    if len(h) == 4:
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def role_for(prop: str) -> list[str] | None:
    p = prop.lower()
    if p in ("color", "selection-color"):
        return TEXT_ROLE
    if p.startswith("background") or p == "selection-background-color":
        return BG_ROLE
    if p.startswith("border") or p.startswith("outline"):
        return BORDER_ROLE
    return None


def tokenize(qss: str, tokens: dict[str, str]) -> tuple[str, Counter]:
    by_value: dict[str, set[str]] = defaultdict(set)
    for k, v in tokens.items():
        by_value[norm_hex(v)].add(k)
    stats: Counter = Counter()

    def repl_decl(m: re.Match[str]) -> str:
        role = role_for(m.group("prop"))
        if role is None:
            return m.group(0)

        def repl_hex(hm: re.Match[str]) -> str:
            keys = by_value.get(norm_hex(hm.group(0)))
            if not keys:
                return hm.group(0)
            for k in role:
                if k in keys:
                    stats[k] += 1
                    return "@" + k
            return hm.group(0)

        return m.group("prop") + m.group("sep") + HEX_RE.sub(repl_hex, m.group("val"))

    # Do not touch comments
    parts = re.split(r"(/\*.*?\*/)", qss, flags=re.S)
    out = [p if p.startswith("/*") else DECL_RE.sub(repl_decl, p) for p in parts]
    return "".join(out), stats


def main() -> int:
    apply = "--apply" in sys.argv
    if not apply and "--dry-run" not in sys.argv:
        print(__doc__)
        return 2
    users: dict[Path, list[str]] = defaultdict(list)
    metas = {}
    for p in sorted((ROOT / "app" / "resources" / "themes").glob("*/theme.json")):
        meta = json.loads(p.read_text(encoding="utf-8"))
        metas[meta["id"]] = meta
        users[ROOT / "app" / meta["qss"]].append(meta["id"])

    backup = ROOT / "artifacts" / "qss_backup"
    total = 0
    for qss_path, ids in users.items():
        if len(ids) != 1:
            print(f"SKIP shared qss {qss_path.name}: {ids}")
            continue
        meta = metas[ids[0]]
        base = dict(DEFAULT_DARK_TOKENS if meta.get("is_dark") else DEFAULT_LIGHT_TOKENS)
        base.update(meta.get("tokens", {}))
        raw = qss_path.read_bytes().decode("utf-8")
        new, stats = tokenize(raw, base)
        n = sum(stats.values())
        total += n
        print(f"{ids[0]:<18} replaced {n:>4}  {dict(stats.most_common(4))}")
        if apply and new != raw:
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(qss_path, backup / qss_path.name)
            qss_path.write_bytes(new.encode("utf-8"))
    print(f"TOTAL replaced: {total}{' (applied)' if apply else ' (dry-run)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
