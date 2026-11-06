"""Seance Insurance screen flow (contracts section 10), backed by real COBOL.

One instance per 3270 session. It holds the current screen name and the values
to paint, interprets each inbound AID + typed fields, calls SEANCSVC on TK4- for
lookup/list/update, and returns the next screen to send.

Key behaviour matches contracts section 10.2 exactly:
  menu    ENTER selects 1/2/3, CLEAR exits
  enquiry ENTER looks up, PF3 back
  list    PF7/PF8 page (single page here), PF3 back
  update  ENTER -> confirm (writes nothing), PF3 back
  confirm ENTER commits (the only mutation), PF3 cancels
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .cobol_client import CobolClient, Policy
from .screens import Screen, all_screens

_STATUS = {"A": "ACTIVE", "L": "LAPSED", "C": "CANCELLED"}
_STATUS_CODE = {"ACTIVE": "A", "LAPSED": "L", "CANCELLED": "C"}


def _format_premium(raw: str) -> str:
    """A whole-number premium entry becomes NNN.00; an already-decimal value is
    kept. Non-numeric input is returned unchanged (the numeric field guards it)."""
    raw = raw.strip()
    if raw.isdigit():
        return f"{int(raw)}.00"
    return raw


@dataclass
class Pending:
    polno: str
    status_code: str
    premium: str


class InsuranceApp:
    def __init__(self, cobol: CobolClient):
        self.cobol = cobol
        self.screens = all_screens()
        self.current = "menu"
        self.values: dict[str, str] = {}
        self.pending: Pending | None = None

    # -- rendering --------------------------------------------------------

    def screen(self) -> Screen:
        return self.screens[self.current]

    def render_values(self) -> dict[str, str]:
        return dict(self.values)

    def reset(self) -> None:
        self.current = "menu"
        self.values = {}
        self.pending = None

    # -- input handling ---------------------------------------------------

    def handle(self, aid: str, typed: dict[str, str]) -> None:
        """Advance the flow given an AID key and typed input field values."""
        if aid == "Clear":
            self._goto("menu")
            return
        handler = getattr(self, f"_on_{self.current}", None)
        if handler is not None:
            handler(aid, typed)

    # -- per-screen handlers ---------------------------------------------

    def _on_menu(self, aid: str, typed: dict[str, str]) -> None:
        if aid != "Enter":
            return
        opt = typed.get("option", "").strip()
        if opt == "1":
            self._goto("enquiry")
        elif opt == "2":
            self._load_list()
        elif opt == "3":
            self._goto("update")
        else:
            self.values["msg"] = "INVALID OPTION"

    def _on_enquiry(self, aid: str, typed: dict[str, str]) -> None:
        if aid == "PF3":
            self._goto("menu")
            return
        if aid != "Enter":
            return
        polno = typed.get("polno", "").strip().upper()
        pol = self.cobol.lookup(polno)
        self.values = {"polno": polno}
        if pol is None:
            self.values["msg"] = "POLICY NOT FOUND"
        else:
            self.values.update({
                "out_5_13": pol.holder, "out_6_13": pol.status,
                "out_7_13": pol.premium, "out_8_13": pol.upddate, "msg": "",
            })

    def _on_list(self, aid: str, typed: dict[str, str]) -> None:
        if aid == "PF3":
            self._goto("menu")
        elif aid == "PF7":
            self.values["msg"] = "TOP OF LIST"
        elif aid == "PF8":
            self.values["msg"] = "BOTTOM OF LIST"

    def _on_update(self, aid: str, typed: dict[str, str]) -> None:
        if aid == "PF3":
            self._goto("menu")
            return
        if aid != "Enter":
            return
        polno = typed.get("polno", "").strip().upper()
        status = typed.get("status", "").strip().upper()
        premium = typed.get("premium", "").strip()
        pol = self.cobol.lookup(polno)
        if pol is None:
            self.values = {"polno": polno, "msg": "POLICY NOT FOUND"}
            return
        if status and status not in _STATUS:
            self.values["msg"] = "STATUS MUST BE A, L OR C"
            return
        if not status and not premium:
            self.values["msg"] = "ENTER A NEW STATUS OR PREMIUM"
            return
        new_status = _STATUS.get(status, pol.status)
        # Normalise a whole-number premium to two decimals (contract shows
        # "250.00"); blank means "unchanged" and is sent as blank to the COBOL.
        new_premium = _format_premium(premium) if premium else pol.premium
        commit_premium = _format_premium(premium) if premium else ""
        self.pending = Pending(polno=polno, status_code=status, premium=commit_premium)
        self.current = "confirm"
        self.values = {
            "polno": polno,
            "out_3_13": polno, "out_4_13": pol.holder,
            "out_6_13": pol.status[:1], "out_6_25": new_status[:1],
            "out_7_13": pol.premium[:7], "out_7_25": new_premium[:7],
            "msg": "ENTER=CONFIRM  PF3=CANCEL",
        }

    def _on_confirm(self, aid: str, typed: dict[str, str]) -> None:
        if aid == "PF3":
            self.pending = None
            self._goto("menu")
            self.values["msg"] = "UPDATE CANCELLED"
            return
        if aid != "Enter":
            return
        # The only mutation in the app: commit via the real COBOL update.
        if self.pending is not None:
            self.cobol.update(self.pending.polno, self.pending.status_code,
                              self.pending.premium)
            self.pending = None
        self._goto("menu")
        self.values["msg"] = "POLICY UPDATED"

    # -- helpers ----------------------------------------------------------

    def _goto(self, name: str) -> None:
        self.current = name
        self.values = {}

    def _load_list(self) -> None:
        self._goto("list")
        for i, pol in enumerate(self.cobol.list_all()[:8]):
            self.values[f"out_{6 + i}_1"] = pol.polno
            self.values[f"out_{6 + i}_11"] = pol.holder
            self.values[f"out_{6 + i}_33"] = pol.status
