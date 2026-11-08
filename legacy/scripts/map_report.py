"""Describe a spirit map for a handoff: nodes (first non-blank row), edges, frontier,
and where an audit log says the run stopped.

    python legacy/scripts/map_report.py MAP.json [AUDIT.jsonl]
"""
from __future__ import annotations

import json
import sys
from collections import Counter


def main() -> int:
    m = json.load(open(sys.argv[1], encoding="utf-8"))
    run = m["run"]
    print(f"run: status={run['status']} reason={run.get('reason')} steps={run.get('steps')}")
    print(f"nodes={len(m['nodes'])} edges={len(m['edges'])} frontier={len(m['frontier'])} home={m.get('home')}")
    for n in m["nodes"]:
        rows = [r.strip() for r in n["rows"] if r.strip()]
        unprot = [f for f in n["fields"] if not f["protected"]]
        big = max((f["length"] for f in unprot), default=0)
        print(f"  {n['id']}  {('blank' if not rows else repr(rows[0][:44])):<48} "
              f"inputs={len(unprot)} largest_input={big}")
    print("edges:")
    for e in m["edges"]:
        print(f"  {e['from']} --{e['key']}{'+fill' if e['fills'] else ''}--> {e['to']}")
    print("frontier by reason:", dict(Counter(f["reason"] for f in m["frontier"])))
    if len(sys.argv) > 2:
        rows = [json.loads(l) for l in open(sys.argv[2], encoding="utf-8") if l.strip()]
        bad = [r for r in rows if r["outcome"] != "ok"]
        for r in bad:
            prev = [x for x in rows if x["seq"] < r["seq"]][-2:]
            print(f"stop: seq {r['seq']} {r['tool']} key={r.get('key')} -> {r['outcome']} "
                  f"on screen n_{(r.get('screen_id') or '')[:10]}; before it: "
                  + ", ".join(f"{p['tool']}({p.get('key') or ''}) on n_{(p.get('screen_id') or '')[:10]}" for p in prev))
    return 0


if __name__ == "__main__":
    sys.exit(main())
