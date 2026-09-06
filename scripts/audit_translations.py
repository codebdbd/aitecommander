"""Find literal Qt translation keys, including wrappers missed by pylupdate6."""
from __future__ import annotations

import ast
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def source_keys():
    keys = set()
    for path in (ROOT / "app").rglob("*.py"):
        if path.name.endswith("_rc.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        constants = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value

        def visit(node, class_name=None):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
            if isinstance(node, ast.Call):
                name = (node.func.id if isinstance(node.func, ast.Name) else
                        node.func.attr if isinstance(node.func, ast.Attribute) else "")
                args = [arg.value if isinstance(arg, ast.Constant) else
                        constants.get(arg.id) if isinstance(arg, ast.Name) else None
                        for arg in node.args]
                pair = None
                if name in ("translate", "QT_TRANSLATE_NOOP") and len(args) > 1:
                    pair = tuple(args[:2])
                elif name == "_tr" and args:
                    context = constants.get("_TR_CONTEXT")
                    pair = (context, args[0]) if context or len(args) < 2 else tuple(args[:2])
                elif name == "tr" and args:
                    pair = (class_name, args[0])
                if pair and all(isinstance(value, str) for value in pair):
                    keys.add(pair)
            for child in ast.iter_child_nodes(node):
                visit(child, class_name)

        visit(tree)
    return keys


def catalog_keys(path):
    return {(context.findtext("name"), message.findtext("source")):
            message.findtext("translation")
            for context in ET.parse(path).getroot().findall("context")
            for message in context.findall("message")}


if __name__ == "__main__":
    catalog = catalog_keys(ROOT / "i18n/app_uk.ts")
    missing = sorted(key for key in source_keys() if not catalog.get(key))
    for context, source in missing:
        print(f"{context}: {source!r}")
    raise SystemExit(bool(missing))
