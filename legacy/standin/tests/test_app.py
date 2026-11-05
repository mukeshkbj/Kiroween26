"""App flow tests with a fake COBOL client (no mainframe needed).

These assert the stand-in's screen flow and key behaviour match contracts
section 10.2, and that the only mutation is ENTER on the confirm screen.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from seance_standin.app import InsuranceApp  # noqa: E402
from seance_standin.cobol_client import Policy  # noqa: E402

SEED = {
    "P0000003": Policy("P0000003", "A. ROSE", "ACTIVE", "250.00", "2026-10-21"),
    "P0000004": Policy("P0000004", "T. NAKAMURA", "LAPSED", "410.00", "2026-06-30"),
}


class FakeCobol:
    def __init__(self) -> None:
        self.updates: list[tuple[str, str, str]] = []
        self.data = dict(SEED)

    def lookup(self, polno):
        return self.data.get(polno.strip().upper())

    def list_all(self):
        return list(self.data.values())

    def update(self, polno, status_code, premium):
        self.updates.append((polno, status_code, premium))
        return self.data.get(polno)


def make():
    return InsuranceApp(FakeCobol())


def test_menu_option_1_opens_enquiry() -> None:
    app = make()
    app.handle("Enter", {"option": "1"})
    assert app.current == "enquiry"


def test_menu_invalid_option_stays_with_message() -> None:
    app = make()
    app.handle("Enter", {"option": "9"})
    assert app.current == "menu"
    assert app.values["msg"] == "INVALID OPTION"


def test_enquiry_lookup_found() -> None:
    app = make()
    app.handle("Enter", {"option": "1"})
    app.handle("Enter", {"polno": "P0000003"})
    assert app.values["out_5_13"] == "A. ROSE"
    assert app.values["out_6_13"] == "ACTIVE"


def test_enquiry_not_found() -> None:
    app = make()
    app._goto("enquiry")
    app.handle("Enter", {"polno": "P9999999"})
    assert app.values["msg"] == "POLICY NOT FOUND"


def test_update_goes_to_confirm_without_mutating() -> None:
    app = make()
    app._goto("update")
    app.handle("Enter", {"polno": "P0000003", "status": "L", "premium": ""})
    assert app.current == "confirm"
    assert app.cobol.updates == []            # nothing written yet
    assert app.values["out_6_13"] == "A"      # old status A(CTIVE)
    assert app.values["out_6_25"] == "L"      # new status L(APSED)


def test_confirm_enter_commits_once() -> None:
    app = make()
    app._goto("update")
    app.handle("Enter", {"polno": "P0000003", "status": "L", "premium": ""})
    app.handle("Enter", {})                   # confirm
    assert app.cobol.updates == [("P0000003", "L", "")]


def test_premium_normalised_to_two_decimals_for_commit() -> None:
    app = make()
    app._goto("update")
    app.handle("Enter", {"polno": "P0000003", "status": "", "premium": "99"})
    assert app.values["out_7_25"] == "99.00"          # NEW column shows 99.00
    app.handle("Enter", {})
    assert app.cobol.updates == [("P0000003", "", "99.00")]
    assert app.current == "menu"
    assert app.values["msg"] == "POLICY UPDATED"


def test_confirm_pf3_cancels_no_mutation() -> None:
    app = make()
    app._goto("update")
    app.handle("Enter", {"polno": "P0000003", "status": "L", "premium": ""})
    app.handle("PF3", {})
    assert app.cobol.updates == []
    assert app.current == "menu"
    assert app.values["msg"] == "UPDATE CANCELLED"


def test_clear_returns_to_menu_from_anywhere() -> None:
    app = make()
    app._goto("confirm")
    app.handle("Clear", {})
    assert app.current == "menu"


def test_update_invalid_status_message() -> None:
    app = make()
    app._goto("update")
    app.handle("Enter", {"polno": "P0000003", "status": "X", "premium": ""})
    assert app.current == "update"
    assert app.values["msg"] == "STATUS MUST BE A, L OR C"
