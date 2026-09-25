from __future__ import annotations

import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


@dataclass
class ThemeCheckResult:
    theme_id: str
    passed: bool
    contrast: float
    is_dark_ok: bool
    error: str = ""


def parse_color(c_str: str) -> tuple[float, float, float] | None:
    """Parse HEX (#RGB, #RRGGBB) or RGB/RGBA string to (r, g, b) float in [0, 1]."""
    c_str = c_str.strip()
    if c_str.startswith("#"):
        hex_val = c_str[1:]
        if len(hex_val) == 3:
            hex_val = "".join(ch * 2 for ch in hex_val)
        if len(hex_val) == 6:
            try:
                r = int(hex_val[0:2], 16) / 255.0
                g = int(hex_val[2:4], 16) / 255.0
                b = int(hex_val[4:6], 16) / 255.0
                return (r, g, b)
            except ValueError:
                return None
    elif c_str.startswith("rgba") or c_str.startswith("rgb"):
        m = re.findall(r"[\d\.]+", c_str)
        if len(m) >= 3:
            try:
                r = float(m[0]) / 255.0
                g = float(m[1]) / 255.0
                b = float(m[2]) / 255.0
                return (r, g, b)
            except ValueError:
                return None
    return None


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    """Calculate WCAG 2.1 relative luminance."""
    r, g, b = (srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(rgb1: tuple[float, float, float], rgb2: tuple[float, float, float]) -> float:
    """Calculate WCAG 2.1 contrast ratio between two colors."""
    l1 = relative_luminance(rgb1)
    l2 = relative_luminance(rgb2)
    bright, dark = max(l1, l2), min(l1, l2)
    return (bright + 0.05) / (dark + 0.05)


def validate_theme_contrast(qss_content: str, is_dark: bool) -> tuple[bool, float, str]:
    """Validate that theme QSS content has readable dialog text contrast and matches is_dark."""
    m_dialog = re.search(r"QDialog\s*\{([^}]+)\}", qss_content)
    if not m_dialog:
        return False, 0.0, "Missing QDialog style block"

    d_block = m_dialog.group(1)
    m_bg = re.search(r"background(?:-color)?:\s*([^;]+);", d_block)
    m_fg = re.search(r"(?<![-\w])color:\s*([^;]+);", d_block)

    if not m_bg or not m_fg:
        return False, 0.0, "Missing background or color in QDialog"

    bg_rgb = parse_color(m_bg.group(1))
    fg_rgb = parse_color(m_fg.group(1))

    if not bg_rgb or not fg_rgb:
        return False, 0.0, f"Cannot parse colors: bg={m_bg.group(1)}, color={m_fg.group(1)}"

    cr = contrast_ratio(bg_rgb, fg_rgb)
    lum = relative_luminance(bg_rgb)
    lum_is_dark = lum < 0.5

    if lum_is_dark != is_dark:
        return False, cr, f"Luminance mismatch: is_dark={is_dark}, but background luminance indicates {'dark' if lum_is_dark else 'light'}"

    if cr < 4.5:
        return False, cr, f"Insufficient contrast ratio {cr:.2f} < 4.5 (WCAG AA)"

    return True, cr, "OK"


def check_bundled_themes(themes_dir: str = "app/resources/themes") -> list[ThemeCheckResult]:
    """Inspect all bundled themes and verify contrast and metadata."""
    results: list[ThemeCheckResult] = []
    theme_json_paths = sorted(glob.glob(f"{themes_dir}/*/theme.json"))

    for t_json in theme_json_paths:
        t_id = os.path.basename(os.path.dirname(t_json))
        try:
            with open(t_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
            t_id = meta.get("id", t_id)
            is_dark = meta.get("is_dark", True)
            qss_rel = meta.get("qss", "")
            qss_path = os.path.join("app", qss_rel)
            if not os.path.exists(qss_path):
                results.append(ThemeCheckResult(t_id, False, 0.0, False, f"QSS not found: {qss_path}"))
                continue
            with open(qss_path, "r", encoding="utf-8") as f:
                qss_text = f.read()
            passed, cr, msg = validate_theme_contrast(qss_text, is_dark)
            results.append(ThemeCheckResult(t_id, passed, cr, passed, msg))
        except Exception as exc:
            results.append(ThemeCheckResult(t_id, False, 0.0, False, str(exc)))
    return results


def main() -> int:
    results = check_bundled_themes()
    all_passed = all(r.passed for r in results)
    print("========================================================================")
    print(f"{'Theme':<18} | {'Status':<6} | {'Contrast':<8} | Details")
    print("========================================================================")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{r.theme_id:<18} | {status:<6} | {r.contrast:<8.2f} | {r.error}")
    print("========================================================================")
    if all_passed:
        print(f"[RESULT] All {len(results)} themes passed WCAG contrast & luminance check.")
        return 0
    else:
        print(f"[RESULT] Failures detected in themes validation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
