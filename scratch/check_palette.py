import glob, os, re

def lum(c):
    if not c or not c.startswith('#') or len(c) != 7: return -1.0
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    return round(0.299 * r + 0.587 * g + 0.114 * b, 1)

themes = sorted(glob.glob('app/resources/qss/*.qss'))
print(f"{'Theme':18} | {'TopBar':9} | {'Window/Tree':11} | {'HdrSection':10} | {'TblBase':9} | {'TblAlt':9} | {'BottomBar':9} | {'StatusBar':9}")
print("-" * 105)

for qss in themes:
    name = os.path.basename(qss).replace('.qss', '')
    if name == 'common': continue
    txt = open(qss, encoding='utf-8').read()
    
    def get_bg(sel, prop='background-color'):
        m = re.search(re.escape(sel) + r'\s*\{([^}]+)\}', txt)
        if not m: return '-'
        bg = re.search(r'(?:' + prop + r'|background)\s*:\s*([^;]+);', m.group(1))
        return bg.group(1).strip() if bg else '-'

    tb = get_bg('QWidget#topBarHost', 'background')
    lp = get_bg('QMainWindow')
    
    hdr_m = re.search(r'QTableView\s+QHeaderView::section:horizontal\s*\{([^}]+)\}', txt)
    hdr = '-'
    if hdr_m:
        bg = re.search(r'background(?:-color)?\s*:\s*([^;]+);', hdr_m.group(1))
        if bg: hdr = bg.group(1).strip()
    
    tbl_m = re.search(r'(?:QTableView,\s*\n*QTableWidget|QTableView)\s*\{([^}]+)\}', txt)
    tbl_base = '-'
    tbl_alt = '-'
    if tbl_m:
        b = re.search(r'background-color\s*:\s*([^;]+);', tbl_m.group(1))
        a = re.search(r'alternate-background-color\s*:\s*([^;]+);', tbl_m.group(1))
        if b: tbl_base = b.group(1).strip()
        if a: tbl_alt = a.group(1).strip()

    bb = get_bg('QWidget#bottomBarContainer')
    sb = get_bg('QStatusBar')

    print(f"{name:18} | {tb:7}({lum(tb):4.1f}) | {lp:7}({lum(lp):4.1f}) | {hdr:7}({lum(hdr):4.1f}) | {tbl_base:7}({lum(tbl_base):4.1f}) | {tbl_alt:7}({lum(tbl_alt):4.1f}) | {bb:7}({lum(bb):4.1f}) | {sb:7}({lum(sb):4.1f})")
