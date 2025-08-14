import ast
import hashlib
import json
import os
from typing import Dict, List, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
# Поднимемся к корню "app/"
while ROOT and os.path.basename(ROOT) != 'app':
    ROOT = os.path.dirname(ROOT)
if not ROOT:
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))

IGNORE_DIRS = {'.git', '.venv', 'venv', 'env', '__pycache__', '.mypy_cache', '.pytest_cache'}
# Исключаем отдельные файлы (бэкапы и т.п.)
EXCLUDE_FILES = {
    os.path.normpath(os.path.join('app', 'config_data', 'config_loader_backup.py')).lower(),
}

# Игнорируем некоторые имена функций как заведомо допустимые совпадения
IGNORED_FUNC_NAMES = { 'get', 'is_valid', 'get_browser_name' }

# Игнорируем слишком короткие функции-делегаты (по количеству строк)
# Примечание: считает по исходным строкам с момента объявления до конца функции
MIN_FUNC_LINES = 0  # поставьте 0, если хотите учитывать все; например 3, чтобы отсечь <=3 строк


def should_skip(dirpath: str) -> bool:
    parts = set(part.lower() for part in dirpath.split(os.sep))
    return bool(parts & {d.lower() for d in IGNORE_DIRS})


def norm_body_dump(body_nodes: List[ast.stmt]) -> str:
    """Нормализуем AST тела функции: без атрибутов, только структура."""
    mod = ast.Module(body=body_nodes, type_ignores=[])
    return ast.dump(mod, include_attributes=False)


def hash_str(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def scan() -> Dict:
    dups_by_name: Dict[Tuple[str, str], List[Dict]] = {}
    dups_ign_name: Dict[str, List[Dict]] = {}
    errors: List[Tuple[str, str]] = []
    files_scanned = 0

    for dirpath, dirnames, filenames in os.walk(ROOT):
        if should_skip(dirpath):
            continue
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            path = os.path.join(dirpath, fn)
            # Исключение конкретных файлов (по относительному пути от корня app)
            try:
                rel_from_root = os.path.relpath(path, ROOT).lower()
            except Exception:
                rel_from_root = path.lower()
            if rel_from_root in EXCLUDE_FILES:
                continue
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    src = f.read()
            except Exception as e:
                errors.append((path, f'io: {e}'))
                continue
            try:
                tree = ast.parse(src)
            except Exception as e:
                errors.append((path, f'parse: {e}'))
                continue
            files_scanned += 1

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if not hasattr(node, 'end_lineno'):
                        # Для очень старых версий Python, но у нас 3.13 — есть.
                        continue
                    # Фильтры: игнор имен и слишком коротких функций
                    if node.name in IGNORED_FUNC_NAMES:
                        continue
                    func_lines = (node.end_lineno or node.lineno) - node.lineno
                    if MIN_FUNC_LINES and func_lines <= MIN_FUNC_LINES:
                        continue
                    dump = norm_body_dump(node.body)
                    h = hash_str(dump)
                    rec = {
                        'file': path.replace('\\', '/'),
                        'func': node.name,
                        'lineno': node.lineno,
                        'end': node.end_lineno,
                    }
                    dups_by_name.setdefault((h, node.name), []).append(rec)
                    dups_ign_name.setdefault(h, []).append(rec)

    groups_by_name = []
    for (h, name), items in dups_by_name.items():
        if len(items) < 2:
            continue
        keyset = {(it['file'], it['lineno'], it['end']) for it in items}
        if len(keyset) < 2:
            continue
        groups_by_name.append({
            'name': name,
            'hash': h,
            'occurrences': sorted(items, key=lambda x: (x['file'], x['lineno']))
        })

    groups_ign_name = []
    for h, items in dups_ign_name.items():
        if len(items) < 2:
            continue
        keyset = {(it['file'], it['lineno'], it['end']) for it in items}
        if len(keyset) < 2:
            continue
        # Сгруппируем по имени внутри, чтобы видеть возможные переименования
        groups_ign_name.append({
            'hash': h,
            'occurrences': sorted(items, key=lambda x: (x['func'], x['file'], x['lineno']))
        })

    groups_by_name.sort(key=lambda g: (-len(g['occurrences']), g['name']))
    groups_ign_name.sort(key=lambda g: (-len(g['occurrences']), g['hash']))

    return {
        'root': ROOT.replace('\\', '/'),
        'files_scanned': files_scanned,
        'errors_count': len(errors),
        'errors': errors,
        'duplicate_groups_by_name_count': len(groups_by_name),
        'duplicate_groups_by_name': groups_by_name,
        'duplicate_groups_ignoring_name_count': len(groups_ign_name),
        'duplicate_groups_ignoring_name': groups_ign_name,
    }


if __name__ == '__main__':
    data = scan()
    out_path = os.path.abspath(os.path.join(ROOT, os.pardir, 'dup_report.json'))
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(out_path)
