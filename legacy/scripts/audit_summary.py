"""Summarise an audit log for a committed handoff (audit logs are gitignored runtime data).

    python legacy/scripts/audit_summary.py RUN.audit.jsonl > RUN.audit-summary.txt

One line per entry: seq, time, tool, outcome, key, field index, screen_id prefix.
Field VALUES are never printed (they are already redacted in the log; this just
makes sure). The hash chain is checked, and the last line says whether it held.
"""
from __future__ import annotations

import json
import sys
from collections import Counter


def main() -> int:
    rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
    prev = None
    chain_ok = True
    for r in rows:
        if prev is not None and r.get("prev_hash") != prev:
            chain_ok = False
        prev = r.get("hash")
        print(f"{r['seq']:>4} {r['ts'][11:19]} {r['tool']:<11} {r['outcome']:<15} "
              f"key={r.get('key') or '-':<6} field={r.get('field') if r.get('field') is not None else '-':<3} "
              f"screen={(r.get('screen_id') or '-')[:10]}")
    keys = Counter(r["key"] for r in rows if r.get("key"))
    print(f"# {len(rows)} entries; outcomes={dict(Counter(r['outcome'] for r in rows))}; "
          f"keys={dict(keys)}; hash chain linked: {chain_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
