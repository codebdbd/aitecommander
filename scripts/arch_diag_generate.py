from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
    ".windsurf",
    ".tmp_pytest",
}

IO_IMPORT_MODULES = {
    "os",
    "pathlib",
    "sqlite3",
    "json",
    "shutil",
    "subprocess",
    "tempfile",
}

LOGIC_FN_MARKERS = (
    "validate",
    "normalize",
    "process",
    "apply",
    "handle",
    "compute",
    "build",
    "load",
    "update",
)

QT_SYMBOLS = (
    "QObject",
    "QWidget",
    "QAbstractListModel",
    "QToolButton",
    "pyqtSignal",
    "pyqtSlot",
)


@dataclass
class ModuleFile:
    module: str
    file: str


def relpath_str(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("/", "\\")


def iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def module_from_path(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def classify_layer(rel_file: str) -> str:
    p = rel_file.replace("\\", "/").lower()
    if "/views/" in p and "/models/" in p:
        return "ui"
    if "/controllers/ui/" in p or "/views/" in p or "/widgets/" in p:
        return "ui"
    if "/services/" in p:
        return "services"
    if "/core/" in p or "/models/" in p:
        return "domain"
    if "/utils/db/" in p or "/startup/" in p or "/resources/" in p:
        return "infra"
    return "other"


def resolve_relative_module(source_module: str, level: int, module: str | None) -> str:
    parts = source_module.split(".")
    if level > 0:
        base = parts[:-level]
    else:
        base = parts
    if module:
        return ".".join(base + module.split("."))
    return ".".join(base)


def get_call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def get_snippet(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].rstrip("\n")
    return ""


def tarjan_scc(nodes: list[str], edges: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    out: list[list[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlinks[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in edges.get(v, set()):
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indices[w])

        if lowlinks[v] == indices[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == v:
                    break
            out.append(scc)

    for n in nodes:
        if n not in indices:
            strongconnect(n)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate architecture diagnostics artifacts.")
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--import-graph", default="import_graph.json")
    parser.add_argument("--cycles", default="cycles.txt")
    parser.add_argument("--diag", default="arch_diag_data.json")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    py_files = iter_python_files(root)

    module_to_file: dict[str, str] = {}
    file_to_module: dict[str, str] = {}
    module_entries: list[ModuleFile] = []
    for file_path in py_files:
        mod = module_from_path(root, file_path)
        rel = relpath_str(root, file_path)
        if not mod:
            continue
        module_to_file[mod] = rel
        file_to_module[rel] = mod
        module_entries.append(ModuleFile(module=mod, file=rel))

    parse_errors: list[dict[str, Any]] = []
    import_edges: list[dict[str, Any]] = []
    file_features: dict[str, Any] = {}
    global_keywords: list[dict[str, Any]] = []
    module_level_objects: list[dict[str, Any]] = []
    ui_construct_calls: list[dict[str, Any]] = []
    dependency_hotspots_ui_handlers: list[dict[str, Any]] = []
    layer_violations: list[dict[str, Any]] = []
    entrypoints: list[dict[str, Any]] = []
    qapp_mentions: list[dict[str, Any]] = []
    main_window_candidates: list[dict[str, Any]] = []

    top_level_dirs = Counter()
    for p in py_files:
        rel_parts = p.relative_to(root).parts
        if rel_parts:
            top_level_dirs[rel_parts[0]] += 1

    for file_path in py_files:
        rel = relpath_str(root, file_path)
        module = file_to_module.get(rel, "")
        layer = classify_layer(rel)
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines(keepends=True)

        if "if __name__ == \"__main__\":" in text:
            for i, line in enumerate(lines, 1):
                if 'if __name__ == "__main__":' in line:
                    entrypoints.append(
                        {
                            "type": "__main__ guard",
                            "file": rel,
                            "line": i,
                            "snippet": line.strip(),
                        }
                    )
                    break
        if rel == "app\\main.py":
            for i, line in enumerate(lines, 1):
                if line.strip().startswith("def main"):
                    entrypoints.append(
                        {"type": "def main", "file": rel, "line": i, "snippet": line.strip()}
                    )
                    break
        for i, line in enumerate(lines, 1):
            if "QApplication" in line:
                qapp_mentions.append(
                    {
                        "type": "QApplication mention",
                        "file": rel,
                        "line": i,
                        "snippet": line.strip(),
                    }
                )
            if "class MainWindow(" in line:
                main_window_candidates.append(
                    {"type": "MainWindow candidate", "file": rel, "line": i, "snippet": line.strip()}
                )

        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError as exc:
            parse_errors.append({"file": rel, "line": exc.lineno or 0, "error": str(exc)})
            continue

        for n in ast.walk(tree):
            for child in ast.iter_child_nodes(n):
                setattr(child, "parent", n)

        ui_imports = []
        io_imports = []
        io_calls = []
        business_fns = []
        branch_count = 0
        imports_internal = []
        imports_external = []
        qt_usages = []
        construct_calls = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.BoolOp, ast.Match)):
                branch_count += 1
            if isinstance(node, ast.Global):
                global_keywords.append(
                    {
                        "file": rel,
                        "line": node.lineno,
                        "names": list(node.names),
                        "snippet": get_snippet(lines, node.lineno),
                    }
                )
            if isinstance(node, ast.Call):
                call_name = get_call_name(node.func)
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    io_calls.append({"line": node.lineno, "snippet": get_snippet(lines, node.lineno)})
                if call_name and call_name.endswith(("Service", "Manager", "Client")):
                    call_rec = {
                        "file": rel,
                        "line": node.lineno,
                        "call": call_name,
                        "function": "",
                        "class": "",
                        "snippet": get_snippet(lines, node.lineno),
                    }
                    construct_calls.append(call_rec)
            if isinstance(node, ast.ClassDef):
                if node.name == "MainWindow":
                    main_window_candidates.append(
                        {
                            "type": "MainWindow class",
                            "file": rel,
                            "line": node.lineno,
                            "snippet": get_snippet(lines, node.lineno),
                        }
                    )
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id in QT_SYMBOLS:
                        qt_usages.append(
                            {
                                "line": node.lineno,
                                "kind": "class_base",
                                "value": base.id,
                                "snippet": get_snippet(lines, node.lineno),
                            }
                        )
                        if layer == "domain":
                            layer_violations.append(
                                {
                                    "rule": "R4",
                                    "file": rel,
                                    "line": node.lineno,
                                    "snippet": get_snippet(lines, node.lineno),
                                    "why": "Qt widgets/signals usage detected in domain/infrastructure-layer file.",
                                    "source_module": module,
                                }
                            )
            if isinstance(node, ast.FunctionDef):
                if any(marker in node.name.lower() for marker in LOGIC_FN_MARKERS):
                    business_fns.append({"line": node.lineno, "name": node.name})

            if isinstance(node, ast.Assign) and isinstance(getattr(node, "parent", None), ast.Module):
                if isinstance(node.value, ast.Call):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            module_level_objects.append(
                                {
                                    "file": rel,
                                    "line": node.lineno,
                                    "name": target.id,
                                    "call": get_call_name(node.value.func) or "",
                                    "snippet": get_snippet(lines, node.lineno),
                                }
                            )

        # Import extraction (top-level + nested)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name
                    rec = {
                        "source": module,
                        "target": target,
                        "file": rel,
                        "line": node.lineno,
                        "snippet": get_snippet(lines, node.lineno),
                    }
                    if target.startswith("PyQt6"):
                        ui_imports.append({"line": node.lineno, "name": target, "snippet": rec["snippet"]})
                        if layer == "domain":
                            layer_violations.append(
                                {
                                    "rule": "R1",
                                    "file": rel,
                                    "line": node.lineno,
                                    "snippet": rec["snippet"],
                                    "why": "Domain-layer file imports Qt/PyQt6 GUI API.",
                                    "source_module": module,
                                }
                            )
                    if target.split(".")[0] in IO_IMPORT_MODULES:
                        io_imports.append({"line": node.lineno, "name": target, "snippet": rec["snippet"]})
                    if target in module_to_file:
                        imports_internal.append({"target": target, "line": node.lineno, "snippet": rec["snippet"]})
                        import_edges.append(rec)
                    else:
                        imports_external.append({"line": node.lineno, "name": target, "snippet": rec["snippet"]})

            if isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    base = resolve_relative_module(module, node.level, node.module)
                else:
                    base = node.module or ""
                for alias in node.names:
                    candidates = []
                    if alias.name != "*":
                        candidates.append(f"{base}.{alias.name}" if base else alias.name)
                    candidates.append(base)

                    resolved_target = None
                    for cand in candidates:
                        if cand in module_to_file:
                            resolved_target = cand
                            break

                    import_name = base
                    rec = {
                        "source": module,
                        "target": resolved_target or import_name,
                        "file": rel,
                        "line": node.lineno,
                        "snippet": get_snippet(lines, node.lineno),
                    }
                    if import_name.startswith("PyQt6"):
                        ui_imports.append({"line": node.lineno, "name": import_name, "snippet": rec["snippet"]})
                        if layer == "domain":
                            layer_violations.append(
                                {
                                    "rule": "R1",
                                    "file": rel,
                                    "line": node.lineno,
                                    "snippet": rec["snippet"],
                                    "why": "Domain-layer file imports Qt/PyQt6 GUI API.",
                                    "source_module": module,
                                }
                            )
                    if import_name.split(".")[0] in IO_IMPORT_MODULES:
                        io_imports.append({"line": node.lineno, "name": import_name, "snippet": rec["snippet"]})
                    if resolved_target:
                        imports_internal.append(
                            {"target": resolved_target, "line": node.lineno, "snippet": rec["snippet"]}
                        )
                        import_edges.append(rec)
                    else:
                        imports_external.append({"line": node.lineno, "name": import_name, "snippet": rec["snippet"]})

        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            call_name = get_call_name(n.func)
            if not call_name or not call_name.endswith(("Service", "Manager", "Client")):
                continue
            cur = n
            fn_name = ""
            cls_name = ""
            while hasattr(cur, "parent"):
                cur = cur.parent  # type: ignore[attr-defined]
                if isinstance(cur, ast.FunctionDef) and not fn_name:
                    fn_name = cur.name
                if isinstance(cur, ast.ClassDef) and not cls_name:
                    cls_name = cur.name
            rec = {
                "file": rel,
                "line": n.lineno,
                "call": call_name,
                "function": fn_name,
                "class": cls_name,
                "snippet": get_snippet(lines, n.lineno),
            }
            ui_construct_calls.append(rec)
            if layer == "ui" and (fn_name.startswith("handle_") or fn_name.startswith("on_")):
                dependency_hotspots_ui_handlers.append(rec)

        roles = []
        if ui_imports:
            roles.append("UI")
        if io_imports or io_calls:
            roles.append("IO")
        if business_fns or branch_count >= 20:
            roles.append("Logic")
        score = branch_count + (20 * len(roles))
        if len(roles) >= 2:
            file_features[rel] = {
                "layers": [layer],
                "ui_imports": ui_imports,
                "io_imports": io_imports,
                "io_calls": io_calls,
                "business_fns": business_fns,
                "branch_count": branch_count,
                "imports_internal": imports_internal,
                "imports_external": imports_external,
                "qt_usages": qt_usages,
                "construct_calls": construct_calls,
            }

    # Deduplicate violations by (rule,file,line)
    uniq_v: dict[tuple[str, str, int], dict[str, Any]] = {}
    for v in layer_violations:
        uniq_v[(v["rule"], v["file"], v["line"])] = v
    layer_violations = sorted(uniq_v.values(), key=lambda x: (x["rule"], x["file"], x["line"]))

    # Graph and degrees
    unique_edges = {(e["source"], e["target"]) for e in import_edges if e["source"] and e["target"]}
    out_deg = Counter()
    in_deg = Counter()
    import_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in import_edges:
        src = e["source"]
        tgt = e["target"]
        if not src or not tgt:
            continue
        out_deg[src] += 1
        in_deg[tgt] += 1
        if len(import_examples[tgt]) < 5:
            import_examples[tgt].append(
                {
                    "importer": src,
                    "file": e["file"],
                    "line": e["line"],
                    "snippet": e["snippet"],
                }
            )

    adjacency: dict[str, set[str]] = defaultdict(set)
    for s, t in unique_edges:
        adjacency[s].add(t)
    nodes = sorted(module_to_file.keys())
    sccs = tarjan_scc(nodes, adjacency)
    cycles = [sorted(s) for s in sccs if len(s) > 1]

    top20_modules = sorted(
        nodes,
        key=lambda m: (in_deg[m], out_deg[m]),
        reverse=True,
    )[:20]
    god_modules_top20 = []
    for m in top20_modules:
        god_modules_top20.append(
            {
                "module": m,
                "file": module_to_file.get(m, ""),
                "out_degree": out_deg[m],
                "in_degree": in_deg[m],
                "total_degree": out_deg[m] + in_deg[m],
                "importer_count": in_deg[m],
                "example_imports": import_examples.get(m, []),
                "symbols": {"classes": [], "funcs": []},
            }
        )

    # Inventory
    dir_counter = Counter()
    for p in py_files:
        dir_counter[relpath_str(root, p.parent)] += 1
    top_dirs_exact = [
        {"dir": d, "count": c} for d, c in sorted(dir_counter.items(), key=lambda x: x[1], reverse=True)[:20]
    ]

    level2_counter = Counter()
    for p in py_files:
        parts = p.relative_to(root).parts
        if len(parts) >= 2:
            level2_counter[f"{parts[0]}\\{parts[1]}"] += 1
    top_dirs_level2 = [
        {"dir": d, "count": c}
        for d, c in sorted(level2_counter.items(), key=lambda x: x[1], reverse=True)[:20]
    ]

    mixed_rows: list[dict[str, Any]] = []
    for f, feats in file_features.items():
        roles: list[str] = []
        if feats["ui_imports"]:
            roles.append("UI")
        if feats["io_imports"] or feats["io_calls"]:
            roles.append("IO")
        if feats["business_fns"] or feats["branch_count"] >= 20:
            roles.append("Logic")
        if len(roles) < 2:
            continue
        mixed_rows.append(
            {
                "file": f,
                "roles": roles,
                "score": feats["branch_count"] + 20 * len(roles),
                "branch_count": feats["branch_count"],
                "features": feats,
            }
        )
    mixed_responsibilities_top = sorted(mixed_rows, key=lambda x: x["score"], reverse=True)[:30]

    arch_diag = {
        "overview": {
            "entrypoints": entrypoints,
            "qapp_mentions": qapp_mentions,
            "main_window_candidates": main_window_candidates,
            "top_level_dirs": [{"dir": d, "count": c} for d, c in top_level_dirs.most_common()],
        },
        "inventory": {
            "python_file_count": len(py_files),
            "top_dirs_exact": top_dirs_exact,
            "top_dirs_level2": top_dirs_level2,
        },
        "parse_errors": parse_errors,
        "graph_summary": {
            "module_count": len(nodes),
            "edge_count": len(import_edges),
            "scc_count": len(sccs),
            "cycle_count": len(cycles),
        },
        "cycles": cycles,
        "god_modules_top20": god_modules_top20,
        "degrees": {
            m: {"in": in_deg[m], "out": out_deg[m], "total": in_deg[m] + out_deg[m]} for m in nodes
        },
        "layer_violations": layer_violations,
        "mixed_responsibilities_top": mixed_responsibilities_top,
        "dependency_hotspots_ui_handlers": dependency_hotspots_ui_handlers,
        "ui_construct_calls": ui_construct_calls,
        "module_level_objects": module_level_objects,
        "global_keywords": global_keywords,
        "module_to_file": module_to_file,
        "file_features": file_features,
    }

    import_graph = {
        "root": str(root),
        "module_count": len(nodes),
        "edge_count": len(import_edges),
        "modules": [m.__dict__ for m in module_entries],
        "edges": import_edges,
    }

    Path(args.import_graph).write_text(
        json.dumps(import_graph, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if cycles:
        lines = []
        for idx, cyc in enumerate(cycles, 1):
            lines.append(f"Cycle {idx}:")
            for m in cyc:
                lines.append(f"  - {m}")
        Path(args.cycles).write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        Path(args.cycles).write_text("No cycles found\n", encoding="utf-8")
    Path(args.diag).write_text(
        json.dumps(arch_diag, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"Generated: {args.import_graph}, {args.cycles}, {args.diag} "
        f"(modules={len(nodes)}, edges={len(import_edges)}, cycles={len(cycles)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
