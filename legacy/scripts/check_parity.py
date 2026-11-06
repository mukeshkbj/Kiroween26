"""Live parity check: do the captured stand-in screens carry the fake's screen_ids?

    mcp-server/.venv/Scripts/python legacy/scripts/check_parity.py

Reads legacy/captures/seance-insurance/capture.json (recorded live through the
real bridge) and compares each screen_id with seance_mcp.fake.fake_insurance().
enquiry_result must equal enquiry: output data is volatile (contract 10.4).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from seance_mcp.fake import FakeApp, fake_insurance

CAP = Path(__file__).resolve().parents[2] / "legacy" / "captures" / "seance-insurance" / "capture.json"


def main() -> int:
    fake = {n: s.model().screen_id for n, s in fake_insurance().screens.items()}
    cap = json.loads(CAP.read_text(encoding="utf-8"))
    ok = True
    for s in cap["screens"]:
        name = s["name"]
        base = "enquiry" if name == "enquiry_result" else name
        live = s["screen"]["screen_id"]
        match = live == fake[base]
        ok &= match
        print(f"{name:15} live={live[:10]} fake={fake[base][:10]} {'MATCH' if match else 'DIFF'}")
    FakeApp.from_capture(CAP)
    print("from_capture: OK")
    print("PARITY OK" if ok else "PARITY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
