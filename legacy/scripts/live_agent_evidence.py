"""Record evidence of a live agent turn (for D's request-a-live-e2e). Agent A only.

Runs D's agent exactly the way D's ``tests/test_live_e2e.py`` does: its
TestClient, the scripted LLM, read-only, a fresh connect_system, one turn. It
also keeps what the test throws away: the full event stream and the agent's
hash-chained audit log, written under ``--out``. Then it checks D's stream
rules (``tests/_stream.check_stream``) and prints a value-free summary.

    $env:GSS_LIVE_OK="1"; $env:TN3270_HOST="localhost"; $env:TN3270_PORT="3270"
    agent/.venv/Scripts/python legacy/scripts/live_agent_evidence.py --app tk4-builtins --out <dir>

Optional ``--lookup P0000003``: instead of read_screen, the scripted model calls
the business tool ``lookup_policy`` (for seance-insurance, once the agent loads
its tool pack). Never proposes a commit; SEANCE_ALLOW_COMMIT is forced to 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))  # so "tests._stream" / "tests.test_api" import

from seance_agent.llm.base import ToolUse  # noqa: E402
from seance_agent.llm.scripted import ScriptedLlm  # noqa: E402
from tests._stream import check_stream  # noqa: E402
from tests.test_api import make_client, open_ws  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default="tk4-builtins")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lookup", help="policy number: call lookup_policy instead of read_screen")
    ap.add_argument("--text", default="What is on the screen?")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SEANCE_ALLOW_COMMIT="0")
    call = (ToolUse("tu1", "lookup_policy", {"policy_number": args.lookup}) if args.lookup
            else ToolUse("tu1", "read_screen", {}))
    llm = ScriptedLlm([[call], ["Done."]])
    audit = out / "agent.audit.jsonl"
    if audit.exists():
        audit.unlink()
    with make_client(llm=(llm, True), env=env, allow_commit=False, audit_log_path=audit) as c, open_ws(c) as s:
        s.until("session_state")
        s.send(id="c1", type="connect_system", app_id=args.app)
        s.until("session_state", lambda e: e["data"]["state"] in ("connected", "error", "session_lost"))
        if not any(e["type"] == "session_state" and e["data"]["state"] == "connected" for e in s.seen):
            (out / "events.jsonl").write_text("\n".join(json.dumps(e) for e in s.seen), encoding="utf-8")
            print("FAIL: not connected:", [e["data"] for e in s.seen if e["type"] in ("error", "session_state")][-2:])
            return 1
        s.until("screen", lambda e: e["data"]["phase"] == "snapshot")
        s.send(id="u1", type="user_message", text=args.text)
        s.until("turn_finished")
        events = list(s.seen)
    (out / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    check_stream(events)
    hidden_leak = [f for e in events if e["type"] == "screen" for f in e["data"]["screen"]["fields"]
                   if f["hidden"] and f["value"] is not None]
    confirms = [e for e in events if e["type"] == "confirmation_required"]
    results = [e["data"] for e in events if e["type"] == "tool_result"]
    screens = [e["data"] for e in events if e["type"] == "screen"]
    print(f"app={args.app} events={len(events)} check_stream=OK hidden_leaks={len(hidden_leak)} "
          f"confirmations={len(confirms)}")
    for sc in screens:
        rows = [r.strip() for r in sc["screen"]["rows"] if r.strip()]
        print(f"  screen phase={sc['phase']:<8} id={sc['screen']['screen_id'][:10]} first_row={rows[0][:50] if rows else '(blank)'!r}")
    for r in results:
        print(f"  tool_result status={r['status']} error={r['error_code']} summary={r['summary'][:80]!r}")
    finish = [e["data"]["reason"] for e in events if e["type"] == "turn_finished"]
    print(f"  turn_finished={finish}")
    return 0 if not hidden_leak and not confirms and finish == ["completed"] else 1


if __name__ == "__main__":
    sys.exit(main())
