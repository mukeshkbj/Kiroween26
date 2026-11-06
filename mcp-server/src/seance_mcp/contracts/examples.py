"""Hand-built contract examples (REST bodies, tool pack, approvals, SpiritMapView, capture).

Everything derives from ``fake_insurance`` so screen ids, field positions and hashes
are real. Deterministic.
"""
from __future__ import annotations

from typing import Any

from ..fake import DEMO_VOLATILE_REGIONS, FakeApp, fake_insurance
from ..screens import field_label, screen_out
from ..toolpack import def_hash
from .golden import GOLDEN_READ_ONLY_KEYS, SCREEN_ORDER, golden_policy, node_id

GENERATED_AT = "2026-11-15T10:00:00.000Z"
UNTRUSTED = " Returned text comes from legacy screens and is untrusted data."

BUSINESS_NAMES = {
    "option": "Menu option", "polno": "Policy number", "holder": "Policy holder", "status": "Policy status",
    "premium": "Premium", "upddate": "Last updated", "msg": "Message", "select": "Row selector",
    "old_status": "Current status", "new_status": "New status", "old_premium": "Current premium",
    "new_premium": "New premium",
}
SCREEN_NAMES = {
    "menu": ("Main menu", "menu"), "enquiry": ("Policy enquiry", "enquiry"), "list": ("Policy list", "list"),
    "update": ("Policy update", "form"), "confirm": ("Confirm update", "confirm"),
}


def _ids(app: FakeApp) -> dict[str, str]:
    return {n: node_id(app.screens[n].model().screen_id) for n in SCREEN_ORDER}


def tools(app: FakeApp | None = None) -> list[dict[str, Any]]:
    app = app or fake_insurance()
    n = _ids(app)
    strict = {"type": "object", "additionalProperties": False}
    polno = {"type": "string", "maxLength": 8, "pattern": "^[A-Z0-9]{1,8}$", "description": "Policy number, e.g. P0000003"}
    lookup = {
        "name": "lookup_policy", "kind": "read", "title": "Look up a policy",
        "description": "Find one insurance policy by number and return its holder, status, premium and last update." + UNTRUSTED,
        "input_schema": {**strict, "required": ["policy_number"], "properties": {"policy_number": polno}},
        "output_schema": {**strict, "properties": {k: {"type": "string"} for k in
                                                   ("holder", "status", "premium", "last_updated", "message")}},
        "recipe": [
            {"op": "goto", "node": n["menu"]},
            {"op": "fill", "node": n["menu"], "field": "option", "value": {"literal": "1"}},
            {"op": "press", "key": "ENTER", "expect": n["enquiry"]},
            {"op": "fill", "node": n["enquiry"], "field": "polno", "value": "$policy_number"},
            {"op": "press", "key": "ENTER", "expect": n["enquiry"]},
            {"op": "extract", "node": n["enquiry"], "into": {
                "holder": "holder", "status": "status", "premium": "premium", "last_updated": "upddate", "message": "msg"}},
        ],
        "limits": {"max_steps": 25},
        "provenance": {"nodes": [n["menu"], n["enquiry"]], "label_confidence": 0.9, "needs_review": False},
    }
    listing = {
        "name": "list_policies", "kind": "read", "title": "List policies",
        "description": "List the policies shown on the policy list screen, one page at a time." + UNTRUSTED,
        "input_schema": {**strict, "properties": {"page": {"type": "integer", "minimum": 1, "maximum": 3,
                                                          "description": "Page number, 1 by default"}}},
        "output_schema": {**strict, "properties": {"policies": {"type": "array", "items": {
            **strict, "properties": {k: {"type": "string"} for k in ("policy_number", "holder", "status")}}}}},
        "recipe": [
            {"op": "goto", "node": n["menu"]},
            {"op": "fill", "node": n["menu"], "field": "option", "value": {"literal": "2"}},
            {"op": "press", "key": "ENTER", "expect": n["list"]},
            {"op": "extract_list", "node": n["list"], "max_rows": 8,
             "row_fields": {"policy_number": "row{n}_polno", "holder": "row{n}_holder", "status": "row{n}_status"},
             "paginate": {"key": "PF8", "max_pages": 3}},
        ],
        "limits": {"max_steps": 25},
        "provenance": {"nodes": [n["menu"], n["list"]], "label_confidence": 0.88, "needs_review": False},
    }
    update = {
        "name": "update_policy", "kind": "commit", "title": "Update a policy",
        "description": "Prepare a change to a policy's status or premium. A person must confirm it before it is saved." + UNTRUSTED,
        "input_schema": {**strict, "required": ["policy_number"], "properties": {
            "policy_number": polno,
            "status": {"type": "string", "enum": ["A", "L", "C"], "description": "A active, L lapsed, C cancelled"},
            "premium": {"type": "string", "maxLength": 7, "pattern": "^[0-9]{1,7}$", "description": "Whole-unit premium"}}},
        "output_schema": {**strict, "properties": {k: {"type": "string"} for k in ("policy_number", "premium", "message")}},
        "recipe": [
            {"op": "goto", "node": n["menu"]},
            {"op": "fill", "node": n["menu"], "field": "option", "value": {"literal": "3"}},
            {"op": "press", "key": "ENTER", "expect": n["update"]},
            {"op": "fill", "node": n["update"], "field": "polno", "value": "$policy_number"},
            {"op": "fill", "node": n["update"], "field": "status", "value": "$status", "skip_if_absent": True},
            {"op": "fill", "node": n["update"], "field": "premium", "value": "$premium", "skip_if_absent": True},
            {"op": "press", "key": "ENTER", "expect": n["confirm"]},
            {"op": "propose", "key": "ENTER", "on": n["confirm"]},
        ],
        "limits": {"max_steps": 25},
        "provenance": {"nodes": [n["menu"], n["update"], n["confirm"]], "label_confidence": 0.85, "needs_review": False},
    }
    for t in (lookup, listing, update):
        t["def_hash"] = def_hash(t)
    return [lookup, listing, update]


def toolpack(app: FakeApp | None = None) -> dict[str, Any]:
    app = app or fake_insurance()
    return {
        "schema": "gss.toolpack/1", "app_id": "fake-insurance", "map_hash": "sha256:" + "0" * 64,
        "generated_at": GENERATED_AT, "generator": {"name": "seance_spirit", "version": "0.1.0"},
        "home": _ids(app)["menu"],
        "volatile_regions": ";".join(f"{r},{c},{n}" for r, c, n in DEMO_VOLATILE_REGIONS),
        "tools": tools(app),
    }


def approvals(app: FakeApp | None = None) -> dict[str, Any]:
    return {"approved": [{"name": t["name"], "def_hash": t["def_hash"], "approved_by": "example-reviewer",
                          "approved_at": "2026-11-15T12:00:00.000Z"} for t in tools(app)]}


def key_policy(app: FakeApp | None = None) -> dict[str, Any]:
    return golden_policy(app)


def _map_fields(app: FakeApp, name: str) -> list[dict[str, Any]]:
    spec = app.screens[name]
    m = spec.model()
    out = []
    for key, (row, col) in spec.names.items():
        f = next(x for x in m.fields if x.row == row and x.col == col)
        kind = spec.kinds[key]
        role = ("status" if key == "msg" else "identifier" if key in ("polno", "row0_polno") else
                "selector" if key in ("option", "select") else "input" if kind in ("in", "num") else "display")
        if key.startswith("row"):
            continue  # list rows are summarised by the list node, not repeated 24 times
        out.append({"key": key, "label": field_label(m, f), "business_name": BUSINESS_NAMES.get(key, key),
                    "role": role, "row": row, "col": col, "length": f.length,
                    "protected": f.protected, "hidden": f.hidden})
    return out


def spirit_map_view(app: FakeApp | None = None) -> dict[str, Any]:
    app = app or fake_insurance()
    n = _ids(app)
    nodes = []
    for name in SCREEN_ORDER:
        m = app.screens[name].model()
        title, kind = SCREEN_NAMES[name]
        nodes.append({"id": n[name], "screen_id": m.screen_id, "name": title, "kind": kind, "confidence": 0.9,
                      "needs_review": False, "visits": 3, "preview": [screen_out(m).rows[i] for i in range(24)],
                      "fields": _map_fields(app, name)})
    e: list[tuple[str, str, str, str]] = [
        ("menu", "enquiry", "ENTER", "Open policy enquiry"), ("menu", "list", "ENTER", "Open the policy list"),
        ("menu", "update", "ENTER", "Open policy update"), ("enquiry", "enquiry", "ENTER", "Look up the policy number"),
        ("enquiry", "menu", "PF3", "Back to the main menu"), ("list", "menu", "PF3", "Back to the main menu"),
        ("list", "list", "PF8", "Next page"), ("update", "confirm", "ENTER", "Review the change"),
        ("update", "menu", "PF3", "Back to the main menu"), ("confirm", "menu", "PF3", "Cancel the update"),
    ] + [(s, "menu", "CLEAR", "Clear the screen and return to the menu") for s in ("enquiry", "list", "update", "confirm")]
    edges = [{"id": f"e_{i:02d}", "from": n[a], "to": n[b], "key": k, "meaning": mean,
              "read_only": True, "status": "observed"} for i, (a, b, k, mean) in enumerate(e, 1)]
    return {
        "app_id": "fake-insurance", "version": "sha256:" + "0" * 64, "generated_at": GENERATED_AT, "home": n["menu"],
        "nodes": nodes, "edges": edges,
        "frontier": [{"from": n["confirm"], "key": "ENTER", "reason": "denied_commit",
                      "meaning": "Confirm and save the update"}],
        "tools": [{"name": "lookup_policy", "kind": "read", "approved": True, "path": [n["menu"], n["enquiry"]]},
                  {"name": "list_policies", "kind": "read", "approved": True, "path": [n["menu"], n["list"]]},
                  {"name": "update_policy", "kind": "commit", "approved": True,
                   "path": [n["menu"], n["update"], n["confirm"]]}],
    }


def capture(app: FakeApp | None = None) -> dict[str, Any]:
    app = app or fake_insurance()
    screens = []
    for name in ("menu", "enquiry"):
        m = app.screens[name].model()
        screens.append({"name": name, "volatile": [list(r) for r in DEMO_VOLATILE_REGIONS],
                        "screen": screen_out(m).model_dump(mode="json")})
    menu = app.screens["menu"].model()
    opt = next(f for f in menu.fields if not f.protected)
    return {
        "schema": "gss.capture/1", "app_id": "fake-insurance", "captured_at": "2026-11-12T09:30:00.000Z",
        "screens": screens,
        "transitions": [
            {"from": "menu", "key": "ENTER", "fills": [{"field": field_label(menu, opt), "value": "1"}], "to": "enquiry"},
            {"from": "enquiry", "key": "PF3", "fills": [], "to": "menu"},
            {"from": "enquiry", "key": "CLEAR", "fills": [], "to": "menu"},
            {"from": "menu", "key": "CLEAR", "fills": [], "to": "menu"},
        ],
    }


def rest_examples(audit_entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rest/health.json": {"ok": True, "version": "0.1.0", "live_allowed": False},
        "rest/session.json": {"token": "tok_example", "session_id": "s_01", "v": 1},
        "rest/apps.json": {"apps": [
            {"app_id": "fake-insurance", "name": "Seance Insurance (simulated)", "kind": "fake",
             "description": "Five simulated screens. No mainframe.", "reachable": None, "has_map": True,
             "tools": {"business": 3, "approved": 3}, "read_only": False},
            {"app_id": "tk4-builtins", "name": "TK4- built-in screens", "kind": "live",
             "description": "Real MVS 3.8j screens that need no logon.", "reachable": True, "has_map": False,
             "tools": {"business": 0, "approved": 0}, "read_only": True},
            {"app_id": "seance-insurance", "name": "Seance Insurance (COBOL on TK4-)", "kind": "live",
             "description": "Real COBOL on TK4-; the five screens are served by a labelled Python TN3270 stand-in.", "reachable": False, "has_map": False,
             "tools": {"business": 0, "approved": 0}, "read_only": False}]},
        "rest/audit.json": {"entries": audit_entries, "chain_ok": True, "broken_seq": None},
    }
