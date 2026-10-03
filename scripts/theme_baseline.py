"""Developer tool: render ThemeGallery for every theme and save/compare PNG baselines.

Usage:
    python scripts/theme_baseline.py save      # write baseline to artifacts/theme_baseline
    python scripts/theme_baseline.py compare   # compare current rendering against baseline
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

BASE_DIR = ROOT / "artifacts" / "theme_baseline"
CUR_DIR = ROOT / "artifacts" / "theme_current"


def render_all(out_dir: Path) -> list[str]:
    import theme_gallery as tg

    out_dir.mkdir(parents=True, exist_ok=True)
    dlg = tg.ThemeGallery()
    dlg.resize(900, 700)
    ids: list[str] = []
    for i in range(dlg._combo.count()):
        theme_id = str(dlg._combo.itemData(i))
        dlg._combo.setCurrentIndex(i)
        dlg._on_changed(i)
        QApplication.processEvents()
        dlg.show()
        QApplication.processEvents()
        dlg.grab().save(str(out_dir / f"{theme_id}.png"))
        ids.append(theme_id)
    return ids


def diff_pixels(a: QImage, b: QImage) -> int:
    if a.size() != b.size():
        return -1
    n = 0
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixel(x, y) != b.pixel(x, y):
                n += 1
    return n


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"
    app = QApplication(sys.argv)  # noqa: F841
    if mode == "save":
        ids = render_all(BASE_DIR)
        print(f"Saved {len(ids)} baseline images to {BASE_DIR}")
        return 0
    ids = render_all(CUR_DIR)
    bad = 0
    for theme_id in ids:
        base = QImage(str(BASE_DIR / f"{theme_id}.png"))
        cur = QImage(str(CUR_DIR / f"{theme_id}.png"))
        if base.isNull():
            print(f"{theme_id:<18} NO BASELINE")
            bad += 1
            continue
        d = diff_pixels(base, cur)
        print(f"{theme_id:<18} {'OK' if d == 0 else f'DIFF ({d} px)'}")
        bad += d != 0
    print("RESULT:", "all identical" if bad == 0 else f"{bad} theme(s) differ")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
