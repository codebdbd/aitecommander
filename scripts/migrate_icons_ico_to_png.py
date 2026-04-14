from __future__ import annotations

import datetime as dt
import shutil
import sqlite3
from pathlib import Path

from PIL import Image


TABLES = ("link", "category", "section", "sphere")


def _appdata_root() -> Path:
    return Path.home() / "AppData" / "Roaming" / "Codebdbd" / "Aite Commander"


def _pick_best_ico_frame(im: Image.Image) -> Image.Image:
    try:
        n_frames = int(getattr(im, "n_frames", 1) or 1)
    except Exception:
        n_frames = 1
    best = im.copy()
    best_area = best.size[0] * best.size[1]
    for idx in range(n_frames):
        try:
            im.seek(idx)
            frame = im.copy()
            area = frame.size[0] * frame.size[1]
            if area >= best_area:
                best = frame
                best_area = area
        except Exception:
            continue
    return best


def _convert_ico_to_png(src: Path, dst: Path) -> bool:
    try:
        with Image.open(src) as im:
            best = _pick_best_ico_frame(im)
            if best.mode != "RGBA":
                best = best.convert("RGBA")
            best.save(dst, format="PNG")
        return True
    except Exception:
        return False


def main() -> int:
    root = _appdata_root()
    icons_dir = root / "icons"
    db_path = root / "links.db"
    if not icons_dir.exists():
        print(f"icons dir not found: {icons_dir}")
        return 2
    if not db_path.exists():
        print(f"db not found: {db_path}")
        return 2

    # Backup DB
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_db = root / f"links.db.backup_before_ico_to_png_{stamp}"
    shutil.copy2(db_path, backup_db)
    print(f"DB backup: {backup_db}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Collect all distinct .ico references from DB
    refs: set[str] = set()
    for table in TABLES:
        rows = cur.execute(
            f"select distinct icon_path from {table} where lower(icon_path) like '%.ico'"
        ).fetchall()
        for (v,) in rows:
            s = (v or "").strip()
            if s:
                refs.add(s)

    mapping: dict[str, str] = {}
    missing: list[str] = []
    failed: list[str] = []
    converted = 0
    reused = 0

    for icon_ref in sorted(refs):
        ico_name = Path(icon_ref).name
        src = icons_dir / ico_name
        if not src.exists():
            missing.append(icon_ref)
            continue

        png_name = f"{src.stem}.png"
        dst = icons_dir / png_name
        if dst.exists():
            mapping[icon_ref] = png_name
            reused += 1
            continue

        ok = _convert_ico_to_png(src, dst)
        if ok:
            mapping[icon_ref] = png_name
            converted += 1
        else:
            failed.append(icon_ref)

    # Update DB atomically
    updates = 0
    for old_ref, new_name in mapping.items():
        for table in TABLES:
            cur.execute(
                f"update {table} set icon_path = ? where icon_path = ?",
                (new_name, old_ref),
            )
            updates += int(cur.rowcount or 0)

    conn.commit()
    conn.close()

    print(f"refs_total={len(refs)}")
    print(f"converted={converted}")
    print(f"reused_existing_png={reused}")
    print(f"db_updates={updates}")
    print(f"missing={len(missing)}")
    for item in missing:
        print(f"  MISSING: {item}")
    print(f"failed={len(failed)}")
    for item in failed:
        print(f"  FAILED: {item}")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

