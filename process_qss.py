import re
import os
import sys

QSS_DIR = r"d:\01_Codebdbd\01_projects\aitecommander\app\resources\qss"

THEME_FILES = [
    "light.qss", "dark.qss", "violet_pulse.qss", "sakura_anime.qss",
    "sage_light.qss", "rasta_royale.qss", "pearl_gray.qss", "pastel_bloom.qss",
    "obsidian_luxe.qss", "nord_light.qss", "matrix.qss", "love.qss",
    "industrial_yellow.qss", "ghost_terminal.qss", "cyberpunk_neon.qss", "crimson_noir.qss"
]

CATEGORY_TILES_SELECTORS_HOVER = [
    "QListWidget#categoryTiles::item:hover,",
    "QListView#categoryTiles::item:hover,"
]

CATEGORY_TILES_SELECTORS_SELECTED = [
    "QListWidget#categoryTiles::item:selected,",
    "QListView#categoryTiles::item:selected,",
    "QListWidget#categoryTiles::item:selected:hover,",
    "QListView#categoryTiles::item:selected:hover,"
]

CATEGORY_TILES_SELECTORS_ALL = CATEGORY_TILES_SELECTORS_HOVER + CATEGORY_TILES_SELECTORS_SELECTED


def remove_trailing_comma_before_brace(block_text):
    return re.sub(r',\s*\{', ' {', block_text)


def remove_category_tiles_selectors(selectors_list, category_patterns):
    result = []
    for sel in selectors_list:
        stripped = sel.strip()
        is_cat = False
        for cat in category_patterns:
            if stripped == cat.strip() or stripped == cat.strip().rstrip(','):
                is_cat = True
                break
        if not is_cat:
            result.append(sel)
    return result


def split_selectors_and_body(block_text):
    m = re.match(r'^(?P<selectors>[\s\S]*?)\s*\{\s*(?P<body>[\s\S]*?)\s*\}\s*$', block_text)
    if not m:
        return None, None
    selectors_text = m.group('selectors').rstrip()
    body = m.group('body').strip()
    selectors_list = []
    for line in selectors_text.split('\n'):
        if line.strip():
            selectors_list.append(line)
    return selectors_list, body


def rebuild_block(selectors_list, body, indent=''):
    selectors_text = '\n'.join(selectors_list)
    selectors_text = remove_trailing_comma_before_brace(selectors_text)
    return f"{selectors_text} {{\n{indent}    {body}\n{indent}}}"


def extract_color(body, prop_name):
    m = re.search(fr'{prop_name}\s*:\s*([^;]+);', body)
    if m:
        return m.group(1).strip()
    return None


def process_file(filepath):
    print(f"\n=== Processing: {os.path.basename(filepath)} ===")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    m = re.search(
        r'/\* Unified state matrix: begin \*/\s*\n(?P<unified>[\s\S]*?)/\* Unified state matrix: end \*/',
        content
    )
    if not m:
        print(f"  SKIP: No unified state matrix found")
        return False

    unified_start = m.start()
    unified_end = m.end()
    unified_block = m.group('unified')

    block_pattern = re.compile(
        r'(?P<indent>^[ \t]*)(?P<selectors>[\s\S]*?)\s*\{\s*(?P<body>[\s\S]*?)\s*\}',
        re.MULTILINE
    )

    blocks = []
    pos = 0
    for bm in block_pattern.finditer(unified_block):
        if bm.start() >= pos:
            blocks.append({
                'match': bm,
                'start': bm.start(),
                'end': bm.end(),
                'indent': bm.group('indent'),
                'selectors_text': bm.group('selectors'),
                'body': bm.group('body').strip(),
            })
            pos = bm.end()

    if len(blocks) < 3:
        print(f"  ERROR: Found only {len(blocks)} blocks, need at least 3")
        return False

    hover_bg_color = None
    selected_bg_color = None
    selected_color = None
    selected_selection_color = None
    border_color = None

    hover_block_idx = None
    selected_block_idx = None
    border_block_idx = None

    for i, blk in enumerate(blocks):
        has_bg = 'background-color' in blk['body']
        has_border = 'border-color' in blk['body']
        has_cat_hover = any('categoryTiles::item:hover' in s for s in blk['selectors_text'].split('\n'))
        has_cat_selected = any('categoryTiles::item:selected' in s for s in blk['selectors_text'].split('\n'))

        if hover_block_idx is None and has_bg and has_cat_hover:
            hover_block_idx = i
            hover_bg_color = extract_color(blk['body'], 'background-color')
            print(f"  HOVER block #{i}: bg={hover_bg_color}")

        elif selected_block_idx is None and has_bg and has_cat_selected:
            selected_block_idx = i
            selected_bg_color = extract_color(blk['body'], 'background-color')
            selected_color = extract_color(blk['body'], 'color')
            selected_selection_color = extract_color(blk['body'], 'selection-color')
            print(f"  SELECTED block #{i}: bg={selected_bg_color}, color={selected_color}, sel-color={selected_selection_color}")

        elif border_block_idx is None and has_border and has_cat_hover and has_cat_selected:
            border_block_idx = i
            border_color = extract_color(blk['body'], 'border-color')
            print(f"  BORDER block #{i}: border={border_color}")

    if hover_block_idx is None or selected_block_idx is None or border_block_idx is None:
        print(f"  ERROR: Could not find all 3 blocks (h={hover_block_idx},s={selected_block_idx},b={border_block_idx})")
        return False

    XXX = hover_bg_color
    ZZZ = border_color
    SELECTED_COLOR = selected_color
    SELECTED_SEL_COLOR = selected_selection_color if selected_selection_color else selected_color

    print(f"  Colors: XXX={XXX}, ZZZ={ZZZ}, selected.color={SELECTED_COLOR}")

    new_unified_parts = []
    last_end = 0

    for i, blk in enumerate(blocks):
        new_unified_parts.append(unified_block[last_end:blk['start']])

        if i == hover_block_idx:
            sel_list, body = split_selectors_and_body(blk['match'].group(0))
            new_sel = remove_category_tiles_selectors(sel_list, CATEGORY_TILES_SELECTORS_HOVER)
            new_block_str = rebuild_block(new_sel, body, blk['indent'])
            new_unified_parts.append(new_block_str)

        elif i == selected_block_idx:
            sel_list, body = split_selectors_and_body(blk['match'].group(0))
            new_sel = remove_category_tiles_selectors(sel_list, CATEGORY_TILES_SELECTORS_SELECTED)
            new_block_str = rebuild_block(new_sel, body, blk['indent'])
            new_unified_parts.append(new_block_str)

        elif i == border_block_idx:
            sel_list, body = split_selectors_and_body(blk['match'].group(0))
            new_sel = remove_category_tiles_selectors(sel_list, CATEGORY_TILES_SELECTORS_ALL)
            new_block_str = rebuild_block(new_sel, body, blk['indent'])
            new_unified_parts.append(new_block_str)

            indent = blk['indent']
            new_category_block = f"""

{indent}/* Category tiles: independent from unified matrix (icons require neutral bg) */
{indent}QListWidget#categoryTiles::item:hover,
{indent}QListView#categoryTiles::item:hover {{
{indent}    background-color: {XXX};
{indent}    border-color: #FFFFFF;
{indent}}}
{indent}QListWidget#categoryTiles::item:selected,
{indent}QListView#categoryTiles::item:selected,
{indent}QListWidget#categoryTiles::item:selected:hover,
{indent}QListView#categoryTiles::item:selected:hover {{
{indent}    background-color: {XXX};
{indent}    color: {SELECTED_COLOR};
{indent}    selection-color: {SELECTED_SEL_COLOR};
{indent}    border-color: {ZZZ};
{indent}}}
"""
            new_unified_parts.append(new_category_block)

        else:
            new_unified_parts.append(blk['match'].group(0))

        last_end = blk['end']

    new_unified_parts.append(unified_block[last_end:])
    new_unified = ''.join(new_unified_parts)

    content = content[:unified_start] + "/* Unified state matrix: begin */\n" + new_unified + "/* Unified state matrix: end */" + content[unified_end:]

    first_block_pattern = re.compile(
        r'QListWidget#categoryTiles::item:hover,\s*\n'
        r'QListView#categoryTiles::item:hover\s*\{\s*\n'
        r'(?P<hbg>.*?)background:\s*(?P<hbgcolor>[^;]+);\s*\n'
        r'(?P<hbr>.*?)border-color:\s*(?P<hbrcolor>[^;]+);\s*\n'
        r'\s*\}\s*\n'
        r'QListWidget#categoryTiles::item:selected,\s*\n'
        r'QListView#categoryTiles::item:selected\s*\{\s*\n'
        r'(?P<sbg>.*?)background:\s*(?P<sbgcolor>[^;]+);\s*\n'
        r'(?P<sbr>.*?)border-color:\s*(?P<sbrcolor>[^;]+);\s*\n'
        r'\s*\}\s*\n'
        r'QListWidget#categoryTiles::item:selected:hover,\s*\n'
        r'QListView#categoryTiles::item:selected:hover\s*\{\s*\n'
        r'(?P<shbg>.*?)background:\s*(?P<shbgcolor>[^;]+);\s*\n'
        r'(?P<shbr>.*?)border-color:\s*(?P<shbrcolor>[^;]+);\s*\n'
        r'\s*\}',
        re.MULTILINE
    )

    fm = first_block_pattern.search(content)
    if fm:
        new_first_block = (
            f"QListWidget#categoryTiles::item:hover,\n"
            f"QListView#categoryTiles::item:hover {{\n"
            f"{fm.group('hbg')}background: {XXX};\n"
            f"{fm.group('hbr')}border-color: #FFFFFF;\n"
            f"}}\n"
            f"QListWidget#categoryTiles::item:selected,\n"
            f"QListView#categoryTiles::item:selected {{\n"
            f"{fm.group('sbg')}background: {XXX};\n"
            f"{fm.group('sbr')}border-color: {ZZZ};\n"
            f"}}\n"
            f"QListWidget#categoryTiles::item:selected:hover,\n"
            f"QListView#categoryTiles::item:selected:hover {{\n"
            f"{fm.group('shbg')}background: {XXX};\n"
            f"{fm.group('shbr')}border-color: {ZZZ};\n"
            f"}}"
        )
        content = content[:fm.start()] + new_first_block + content[fm.end():]
        print(f"  Updated first categoryTiles block")
    else:
        print(f"  WARNING: Could not find first categoryTiles block to update")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  OK: File saved")
    return True


def main():
    processed = []
    skipped = []
    errors = []

    for fname in THEME_FILES:
        fpath = os.path.join(QSS_DIR, fname)
        if not os.path.exists(fpath):
            print(f"FILE NOT FOUND: {fpath}")
            errors.append(fname)
            continue
        try:
            ok = process_file(fpath)
            if ok:
                processed.append(fname)
            else:
                skipped.append(fname)
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            errors.append(fname)

    print("\n" + "=" * 60)
    print(f"Processed OK: {len(processed)}")
    for f in processed:
        print(f"  + {f}")
    print(f"Skipped: {len(skipped)}")
    for f in skipped:
        print(f"  - {f}")
    print(f"Errors: {len(errors)}")
    for f in errors:
        print(f"  ! {f}")
    print("=" * 60)

    return len(errors) == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
