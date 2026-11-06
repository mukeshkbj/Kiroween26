"""Compare a live spirit map with B's fake-insurance map (nodes, edges, frontier).

    mcp-server/.venv/Scripts/python legacy/scripts/compare_maps.py LIVE_MAP [FAKE_MAP]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(p: str | Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def edge_set(m: dict) -> set[tuple]:
    return {(e["from"], e["key"], tuple(sorted((f["field"], f.get("probe")) for f in e["fills"])), e["to"])
            for e in m["edges"]}


def main() -> int:
    live = load(sys.argv[1])
    fake = load(sys.argv[2] if len(sys.argv) > 2 else ROOT / "docs/spirit-map/fake-insurance/spirit-map.json")
    ln, fn = {n["id"] for n in live["nodes"]}, {n["id"] for n in fake["nodes"]}
    print(f"run: {live['run']['status']} steps={live['run'].get('steps')}")
    print(f"nodes live={len(ln)} fake={len(fn)} same={ln == fn}")
    le, fe = edge_set(live), edge_set(fake)
    print(f"edges live={len(le)} fake={len(fe)} same={le == fe}")
    for e in sorted(le - fe):
        print("  only live:", e)
    for e in sorted(fe - le):
        print("  only fake:", e)
    lf = {(f["from"], f["key"], f["reason"]) for f in live["frontier"]}
    ff = {(f["from"], f["key"], f["reason"]) for f in fake["frontier"]}
    print(f"frontier live={sorted(lf)}")
    print(f"frontier same={lf == ff}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
