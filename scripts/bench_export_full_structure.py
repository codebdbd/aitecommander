import argparse
import time
import sqlite3
import sys
import os
from typing import List, Dict, Any, Optional

# Ensure project root (one level up from tests, same style as tests/conftest.py) is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.models.db import Database


def build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark export_full_structure bulk vs N+1")
    p.add_argument("--db-path", default=None, help="Path to SQLite DB file. If omitted, uses app-config default DB.")
    p.add_argument("--rounds", type=int, default=5, help="Number of measured rounds per method")
    p.add_argument("--warmup", type=int, default=2, help="Number of warmup runs per method (not measured)")
    return p.parse_args()


def export_full_structure_n_plus_one(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
    """Reference N+1 implementation to compare with bulk method. Do NOT use in production code."""
    spheres_data: List[Dict[str, Any]] = []
    spheres = conn.execute("SELECT * FROM sphere ORDER BY position").fetchall()
    for s in spheres:
        sd = dict(s)
        sections_data: List[Dict[str, Any]] = []
        sections = conn.execute(
            "SELECT * FROM section WHERE sphere_id=? ORDER BY position", (s["id"],)
        ).fetchall()
        for sec in sections:
            sc = dict(sec)
            categories_data: List[Dict[str, Any]] = []
            categories = conn.execute(
                "SELECT * FROM category WHERE section_id=? ORDER BY position", (sec["id"],)
            ).fetchall()
            for cat in categories:
                cd = dict(cat)
                links = conn.execute(
                    "SELECT * FROM link WHERE category_id=? ORDER BY position", (cat["id"],)
                ).fetchall()
                cd["links"] = [dict(l) for l in links]
                categories_data.append(cd)
            sc["categories"] = categories_data
            sections_data.append(sc)
        sd["sections"] = sections_data
        spheres_data.append(sd)
    return {"spheres": spheres_data}


def _measure(fn, rounds: int, warmup: int) -> Dict[str, float]:
    for _ in range(warmup):
        fn()
    t0 = time.perf_counter()
    for _ in range(rounds):
        fn()
    t1 = time.perf_counter()
    total = (t1 - t0) * 1000.0
    return {"avg_ms": total / rounds, "total_ms": total, "rounds": rounds}


def main():
    args = build_args()

    db = Database()
    if args.db_path:
        db.db_path = args.db_path
    # Ensure connection is created with selected path
    _ = db.connection

    def bulk():
        return db.export_full_structure()

    def n_plus_one():
        return export_full_structure_n_plus_one(db.connection)

    print("Benchmark export_full_structure on DB:", db.db_path)
    print(f"Rounds={args.rounds}, Warmup={args.warmup}")

    bulk_stats = _measure(bulk, args.rounds, args.warmup)
    n1_stats = _measure(n_plus_one, args.rounds, args.warmup)

    print("\nResults:")
    print(f"  Bulk    : avg={bulk_stats['avg_ms']:.2f} ms  total={bulk_stats['total_ms']:.2f} ms / {int(bulk_stats['rounds'])} rounds")
    print(f"  N+1     : avg={n1_stats['avg_ms']:.2f} ms  total={n1_stats['total_ms']:.2f} ms / {int(n1_stats['rounds'])} rounds")

    if n1_stats["avg_ms"] > 0:
        speedup = n1_stats["avg_ms"] / bulk_stats["avg_ms"] if bulk_stats["avg_ms"] > 0 else float("inf")
        print(f"  Speedup : {speedup:.2f}x (N+1 / Bulk)")

    try:
        db.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
