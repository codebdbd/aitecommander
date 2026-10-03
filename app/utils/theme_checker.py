from __future__ import annotations

import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtGui import QColor

from app.utils.theme_placeholders import resolve_token_placeholders

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


def parse_color(c_str: str, bg_rgb: tuple[float, float, float] | None = None) -> tuple[float, float, float] | None:
    """Parse a Qt color (#RGB, #RRGGBB, #AARRGGBB, rgb()/rgba()) to opaque (r, g, b).

    8-digit hex follows Qt semantics (#AARRGGBB). Alpha is composited over ``bg_rgb``.
    """
    if not isinstance(c_str, str):
        return None
    c_str = c_str.strip()
    if c_str.startswith("#"):
        qc = QColor(c_str)
        if not qc.isValid():
            return None
        r, g, b, a = qc.redF(), qc.greenF(), qc.blueF(), qc.alphaF()
    elif c_str.startswith("rgb"):
        m = re.findall(r"[\d.]+%?", c_str)
        if len(m) < 3:
            return None
        try:
            r, g, b = (float(v.rstrip("%")) / 100.0 if v.endswith("%") else float(v) / 255.0 for v in m[:3])
            a = 1.0
            if len(m) >= 4:
                raw = m[3]
                a = float(raw.rstrip("%")) / 100.0 if raw.endswith("%") else float(raw)
                if a > 1.0:
                    a /= 255.0
        except ValueError:
            return None
    else:
        return None
    if a < 1.0 and bg_rgb is not None:
        r = r * a + bg_rgb[0] * (1.0 - a)
        g = g * a + bg_rgb[1] * (1.0 - a)
        b = b * a + bg_rgb[2] * (1.0 - a)
    return (r, g, b)


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


def _with_default_tokens(tokens: dict[str, str] | None, is_dark: bool) -> dict[str, str]:
    from app.services.theme_registry import DEFAULT_DARK_TOKENS, DEFAULT_LIGHT_TOKENS

    merged = dict(DEFAULT_DARK_TOKENS if is_dark else DEFAULT_LIGHT_TOKENS)
    if isinstance(tokens, dict):
        merged.update(tokens)
    return merged


def validate_theme_contrast(qss_content: str, is_dark: bool, tokens: dict[str, str] | None = None) -> tuple[bool, float, str]:
    """Validate that theme QSS content and semantic tokens have readable contrast and match is_dark."""
    ref_bg = (0.0, 0.0, 0.0) if is_dark else (1.0, 1.0, 1.0)
    effective_tokens = _with_default_tokens(tokens, is_dark)
    qss_content = resolve_token_placeholders(qss_content, effective_tokens)
    m_dialog = re.search(r"QDialog\s*\{([^}]+)\}", qss_content)
    if not m_dialog:
        return False, 0.0, "Missing QDialog style block"

    d_block = m_dialog.group(1)
    m_bg = re.search(r"background(?:-color)?:\s*([^;]+);", d_block)
    m_fg = re.search(r"(?<![-\w])color:\s*([^;]+);", d_block)

    if not m_bg or not m_fg:
        return False, 0.0, "Missing background or color in QDialog"

    bg_rgb = parse_color(m_bg.group(1), ref_bg)
    fg_rgb = parse_color(m_fg.group(1), bg_rgb)

    if not bg_rgb or not fg_rgb:
        return False, 0.0, f"Cannot parse colors: bg={m_bg.group(1)}, color={m_fg.group(1)}"

    cr = contrast_ratio(bg_rgb, fg_rgb)
    lum = relative_luminance(bg_rgb)
    lum_is_dark = lum < 0.5

    if lum_is_dark != is_dark:
        return False, cr, f"Luminance mismatch: is_dark={is_dark}, but background luminance indicates {'dark' if lum_is_dark else 'light'}"

    if cr < 4.5:
        return False, cr, f"Insufficient QDialog contrast ratio {cr:.2f} < 4.5 (WCAG AA)"

    bg_canvas = parse_color(effective_tokens.get("bg_canvas", ""), ref_bg)
    bg_surface = parse_color(effective_tokens.get("bg_surface", ""), ref_bg)
    raw_text = effective_tokens.get("text_primary", "")
    text_canvas = parse_color(raw_text, bg_canvas)
    text_surface = parse_color(raw_text, bg_surface)
    sel_bg = parse_color(effective_tokens.get("selection_bg", ""), bg_canvas)
    sel_fg = parse_color(effective_tokens.get("selection_fg", ""), sel_bg)
    if not bg_canvas or not text_canvas:
        return False, 0.0, f"Cannot parse canvas or text color in tokens"
    if not bg_surface or not text_surface:
        return False, 0.0, f"Cannot parse surface or text color in tokens"
    if not sel_bg or not sel_fg:
        return False, 0.0, f"Cannot parse selection color in tokens"
    if bg_canvas and text_canvas:
        cr_canvas = contrast_ratio(bg_canvas, text_canvas)
        if cr_canvas < 4.5:
            return False, cr_canvas, f"Insufficient canvas text contrast {cr_canvas:.2f} < 4.5 (WCAG AA)"
    if bg_surface and text_surface:
        cr_surface = contrast_ratio(bg_surface, text_surface)
        if cr_surface < 4.5:
            return False, cr_surface, f"Insufficient surface text contrast {cr_surface:.2f} < 4.5 (WCAG AA)"
    if sel_bg and sel_fg:
        cr_sel = contrast_ratio(sel_bg, sel_fg)
        if cr_sel < 4.5:
            return False, cr_sel, f"Insufficient selection contrast {cr_sel:.2f} < 4.5 (WCAG AA)"

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
            tokens = meta.get("tokens")
            passed, cr, msg = validate_theme_contrast(qss_text, is_dark, tokens)
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
