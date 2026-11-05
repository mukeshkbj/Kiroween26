"""FakeBridge: a fake 3270 app behind the real ``BridgePort`` interface.

Shared by every component that must not touch the live container
(docs/contracts.md section 2). Screens are built from real bridge ``Buffer``s
and parsed by the real ``ScreenParser``, so ``screen_id``s, field layouts and
hidden fields are genuine.

Three layers:

* ``ScreenSpec`` / ``build_screen``: a mutable screen with named fields.
* ``FakePort``: scripted ``(screen, key) -> screen`` transitions (used by the
  mcp-server tests).
* ``FakeApp``: value-aware rules, a key log and a ``dirty`` flag set when a
  rule marked ``mutating`` runs. ``fake_insurance()`` is the 5-screen demo app
  of contracts section 10. ``FakeApp.from_capture`` replays a recorded real app.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from seance_bridge import (
    BUFFER_SIZE,
    COLS,
    Buffer,
    FieldAttrs,
    FieldStart,
    FieldValidationError,
    Key,
    KeyboardTimeoutError,
    ScreenModel,
    ScreenParser,
)

PARSER = ScreenParser()
P = FieldAttrs(protected=True)
U = FieldAttrs(protected=False)
UN = FieldAttrs(protected=False, numeric=True)
H = FieldAttrs(protected=False, hidden=True)
HN = FieldAttrs(protected=False, hidden=True, numeric=True)

Region = tuple[int, int, int]  # (row, col, length), 0-origin, as VOLATILE_REGIONS


def rc(row: int, col: int) -> int:
    return row * COLS + col


def region_positions(regions: Iterable[Region]) -> frozenset[int]:
    return frozenset(
        rc(r, c) + i for r, c, n in regions for i in range(n) if 0 <= rc(r, c) + i < BUFFER_SIZE
    )


class CaptureError(ValueError):
    """A capture file is malformed or does not reproduce its recorded screen_id."""


# ---------------------------------------------------------------- screens


class ScreenSpec:
    """A mutable screen: text + field starts; typed values persist.

    ``names`` maps a field name to the (row, col) of its first data position so
    rules can read and write fields by name. ``volatile`` positions are excluded
    from ``screen_id`` (the same mechanism as the bridge's volatile regions).
    """

    def __init__(
        self,
        texts: dict[int, str],
        starts: list[tuple[int, FieldAttrs]],
        cursor: tuple[int, int] = (0, 0),
        *,
        names: dict[str, tuple[int, int]] | None = None,
        kinds: dict[str, str] | None = None,
        volatile: frozenset[int] = frozenset(),
    ):
        grid = [" "] * BUFFER_SIZE
        for pos, txt in texts.items():
            for i, ch in enumerate(txt):
                if 0 <= pos + i < BUFFER_SIZE:
                    grid[pos + i] = ch
        for pos, _ in starts:
            grid[pos] = " "
        self.text = grid
        self.starts = tuple(FieldStart(pos=p, attrs=a) for p, a in sorted(starts))
        self.cursor = cursor
        self.names = names or {}
        self.kinds = kinds or {}
        self.volatile = volatile

    def model(self) -> ScreenModel:
        return PARSER.parse(
            Buffer(text="".join(self.text), field_starts=self.starts,
                   cursor_row=self.cursor[0], cursor_col=self.cursor[1]),
            self.volatile,
        )

    # -- named field access (used by FakeApp rules) -----------------------

    def _field(self, name: str):
        m = self.model()
        f = ScreenParser.field_at(m, *self.names[name])
        if f is None:
            raise KeyError(f"no field named {name!r}")
        return f

    def get(self, name: str) -> str:
        v = self._field(name).value
        return (v or "").rstrip()

    def put(self, name: str, value: str) -> None:
        f = self._field(name)
        start = f.row * COLS + f.col
        self.text[start:start + f.length] = list(value[: f.length].ljust(f.length))

    def clear(self) -> None:
        for name in self.names:
            self.put(name, "")


@dataclass(frozen=True)
class F:
    """A named field for ``build_screen``. ``col`` is the first DATA column."""

    name: str
    row: int
    col: int
    length: int
    kind: Literal["in", "num", "out", "hidden", "hidden_num"] = "out"


_KIND_ATTRS = {"in": U, "num": UN, "out": P, "hidden": H, "hidden_num": HN}


def build_screen(
    texts: dict[tuple[int, int], str],
    fields: Sequence[F] = (),
    *,
    cursor_field: str | None = None,
    volatile: frozenset[int] = frozenset(),
) -> ScreenSpec:
    """Place text, then fields. Each field gets an attribute byte at ``col - 1``
    and a protected terminator right after its data (unless another field starts
    there). Everything outside fields is protected text."""
    starts: dict[int, FieldAttrs] = {0: P}
    for f in fields:
        end = rc(f.row, f.col) + f.length
        if end < BUFFER_SIZE:
            starts.setdefault(end, P)
    for f in fields:
        starts[rc(f.row, f.col) - 1] = _KIND_ATTRS[f.kind]
    cursor = (0, 0)
    if cursor_field is not None:
        tgt = next(f for f in fields if f.name == cursor_field)
        cursor = (tgt.row, tgt.col)
    return ScreenSpec(
        {rc(r, c): t for (r, c), t in texts.items()},
        list(starts.items()),
        cursor,
        names={f.name: (f.row, f.col) for f in fields},
        kinds={f.name: f.kind for f in fields},
        volatile=volatile,
    )


# ---------------------------------------------------------------- legacy helpers (mcp-server tests)


def logon_screen(extra: dict[int, str] | None = None) -> ScreenSpec:
    texts = {rc(0, 1): "SEANCE TEST SYSTEM", rc(5, 1): "USERID   ===>", rc(6, 1): "PASSWORD ===>",
             rc(7, 1): "ACCOUNT  ===>", rc(8, 1): "PIN      ===>", rc(9, 1): "PF3=EXIT  ENTER=LOGON"}
    texts.update(extra or {})
    starts = [
        (rc(0, 0), P),
        (rc(5, 15), U), (rc(5, 24), P),
        (rc(6, 15), H), (rc(6, 24), P),
        (rc(7, 15), UN), (rc(7, 22), P),
        (rc(8, 15), HN), (rc(8, 20), P),
    ]
    return ScreenSpec(texts, starts, cursor=(5, 16))


def menu_screen() -> ScreenSpec:
    return ScreenSpec({rc(0, 1): "MAIN MENU", rc(3, 1): "1  POLICY ENQUIRY"}, [(rc(0, 0), P)])


# ---------------------------------------------------------------- ports


class FakePort:
    """A scripted 3270 app: ``(screen, key) -> screen``. Implements ``BridgePort``."""

    def __init__(self, screens: dict[str, ScreenSpec] | None = None, start: str = "logon",
                 transitions: dict[tuple[str, str], str] | None = None,
                 timeout_keys: frozenset[str] = frozenset()):
        self.screens = screens or {"logon": logon_screen(), "menu": menu_screen()}
        self.current = start
        self.transitions = transitions if transitions is not None else {
            ("logon", "Enter"): "menu", ("logon", "Clear"): "menu", ("menu", "PF3"): "logon",
        }
        self.timeout_keys = timeout_keys
        self.calls: list[tuple] = []
        self._connected = False
        self.fail_next: Exception | None = None  # raised once by the next read/fill/press

    def _maybe_fail(self) -> None:
        if self.fail_next is not None:
            exc, self.fail_next = self.fail_next, None
            raise exc

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self, host: str, port: int) -> ScreenModel:
        self.calls.append(("connect", host, port))
        self._connected = True
        return self.screens[self.current].model()

    async def disconnect(self) -> None:
        self._connected = False

    async def read_screen(self) -> ScreenModel:
        self._maybe_fail()
        self.calls.append(("read",))
        return self.screens[self.current].model()

    async def fill_field(self, field_ref: int | tuple[int, int], value: str) -> ScreenModel:
        self._maybe_fail()
        spec = self.screens[self.current]
        m = spec.model()
        if isinstance(field_ref, int):
            f = next((x for x in m.fields if x.index == field_ref), None)
        else:
            f = ScreenParser.field_at(m, field_ref[0], field_ref[1])
        if f is None:
            raise FieldValidationError("no such field")
        if f.protected:
            raise FieldValidationError(f"field {f.index} is protected")
        if len(value) > f.length:
            raise FieldValidationError(f"value too long: {len(value)} > field length {f.length}")
        if f.numeric and not value.isdigit():
            raise FieldValidationError(f"field {f.index} is numeric; value is not a number")
        self.calls.append(("fill", f.index, value))
        start = f.row * COLS + f.col
        for i, ch in enumerate(value.ljust(f.length)):
            spec.text[start + i] = ch
        return spec.model()

    async def press(self, key: Key) -> ScreenModel:
        self._maybe_fail()
        self.calls.append(("press", key.value))  # the key IS sent before any timeout
        if key.value in self.timeout_keys:
            raise KeyboardTimeoutError("keyboard still locked")
        self.current = self.transitions.get((self.current, key.value), self.current)
        return self.screens[self.current].model()

    @property
    def pressed(self) -> list[str]:
        return [c[1] for c in self.calls if c[0] == "press"]


Values = dict[str, str]
Effect = Callable[["FakeApp", Values], None]


@dataclass
class Rule:
    """When ``key`` is pressed on screen ``frm`` (``"*"`` = any) and ``when`` holds,
    run ``effect`` (which calls ``app.goto``/``app.set``/``app.say``) or, with no
    effect, go to ``to``. ``mutating`` marks a rule that changes application data:
    it sets ``app.dirty`` and is listed in ``app.mutations``."""

    frm: str
    key: str
    to: str | None = None
    when: Callable[[Values], bool] | None = None
    effect: Effect | None = None
    mutating: bool = False


def _key_name(key: str) -> str:
    return Key[key.upper()].value


class FakeApp(FakePort):
    """Value-aware fake application. Records every key received (``pressed``),
    every mutating rule that ran (``mutations``) and a ``dirty`` flag."""

    def __init__(self, screens: dict[str, ScreenSpec], start: str, rules: Iterable[Rule],
                 timeout_keys: frozenset[str] = frozenset(), *,
                 on_reset: Callable[["FakeApp"], None] | None = None):
        super().__init__(screens=screens, start=start, transitions={}, timeout_keys=timeout_keys)
        self.start = start
        self.rules = [Rule(r.frm, _key_name(r.key), r.to, r.when, r.effect, r.mutating) for r in rules]
        self.dirty = False
        self.mutations: list[tuple[str, str]] = []
        self._on_reset = on_reset
        self.state: dict[str, Any] = {}

    # -- rule helpers -------------------------------------------------------

    def values(self) -> Values:
        spec = self.screens[self.current]
        return {n: spec.get(n) for n in spec.names}

    def goto(self, name: str, **fields: str) -> None:
        spec = self.screens[name]
        spec.clear()
        for k, v in fields.items():
            spec.put(k, v)
        self.current = name

    def set(self, **fields: str) -> None:
        spec = self.screens[self.current]
        for k, v in fields.items():
            spec.put(k, v)

    def say(self, message: str) -> None:
        self.set(msg=message)

    def reset(self) -> None:
        self.current = self.start
        self.dirty = False
        self.mutations.clear()
        self.calls.clear()
        self.state.clear()
        for spec in self.screens.values():
            spec.clear()
        if self._on_reset:
            self._on_reset(self)

    # -- BridgePort ---------------------------------------------------------

    async def press(self, key: Key) -> ScreenModel:
        self._maybe_fail()
        self.calls.append(("press", key.value))
        if key.value in self.timeout_keys:
            raise KeyboardTimeoutError("keyboard still locked")
        values = self.values()
        for rule in self.rules:
            if rule.frm not in (self.current, "*") or rule.key != key.value:
                continue
            if rule.when is not None and not rule.when(values):
                continue
            if rule.mutating:
                self.dirty = True
                self.mutations.append((self.current, key.value))
            if rule.effect is not None:
                rule.effect(self, values)
            elif rule.to is not None:
                self.goto(rule.to)
            break
        return self.screens[self.current].model()

    # -- captures -----------------------------------------------------------

    @classmethod
    def from_capture(cls, path: str | Path) -> "FakeApp":
        """Replay a ``gss.capture/1`` file (docs/contracts.md 2.3).

        Each recorded screen is rebuilt as a buffer and re-parsed; the recomputed
        ``screen_id`` must equal the recorded one (give the capture's optional
        per-screen ``volatile`` spans if the real app has a clock) or this raises
        ``CaptureError``. Transitions with ``fills`` match only when those field
        values (by label) are currently typed; more specific transitions win.
        """
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("schema") != "gss.capture/1":
            raise CaptureError("not a gss.capture/1 file")
        screens: dict[str, ScreenSpec] = {}
        order: list[str] = []
        for item in raw["screens"]:
            name = item["name"]
            screens[name] = _spec_from_screen_out(name, item["screen"], item.get("volatile", []))
            order.append(name)
        if not order:
            raise CaptureError("capture has no screens")
        rules: list[Rule] = []
        for t in sorted(raw.get("transitions", []), key=lambda t: -len(t.get("fills", []))):
            fills = {f["field"]: f["value"] for f in t.get("fills", [])}
            if t["from"] not in screens or t["to"] not in screens:
                raise CaptureError(f"transition names an unknown screen: {t}")
            rules.append(Rule(t["from"], t["key"], t["to"], when=_labels_match(screens, t["from"], fills)))
        return cls(screens, order[0], rules)


def _labels_match(screens: dict[str, ScreenSpec], frm: str, fills: dict[str, str]):
    def check(_values: Values) -> bool:
        if not fills:
            return True
        m = screens[frm].model()
        typed = {f.label: (f.value or "").rstrip() for f in _labelled(m)}
        return all(typed.get(label) == value for label, value in fills.items())

    return check


def _labelled(m: ScreenModel):
    """(label, value) of unprotected fields using the same label rule as the tools."""
    from .screens import field_label

    class _L:
        def __init__(self, label: str, value: str | None):
            self.label, self.value = label, value

    return [_L(field_label(m, f), f.value) for f in m.fields if not f.protected]


def _spec_from_screen_out(name: str, so: dict[str, Any], volatile: list[list[int]]) -> ScreenSpec:
    rows = so["rows"]
    if len(rows) != 24 or any(len(r) != COLS for r in rows):
        raise CaptureError(f"{name}: rows must be 24 x {COLS}")
    text = "".join(rows)
    starts: list[tuple[int, FieldAttrs]] = [(0, P)] if not so["fields"] or so["fields"][0]["row"] * COLS + so["fields"][0]["col"] > 1 else []
    for f in so["fields"]:
        pos = f["row"] * COLS + f["col"] - 1
        if pos < 0:
            raise CaptureError(f"{name}: field starts at the first cell")
        starts.append((pos, FieldAttrs(protected=f["protected"], numeric=f["numeric"],
                                       hidden=f["hidden"], intensified=f["intensified"])))
    vol = region_positions(tuple(v) for v in volatile)  # type: ignore[misc]
    spec = ScreenSpec({0: text}, starts, tuple(so["cursor"]), volatile=vol)
    spec.text = list(text)
    for pos, _ in starts:
        spec.text[pos] = " "
    got = spec.model().screen_id
    if got != so["screen_id"]:
        raise CaptureError(
            f"{name}: rebuilt screen_id {got[:12]} != recorded {so['screen_id'][:12]} "
            "(missing volatile spans, or the capture was edited)"
        )
    return spec


# ---------------------------------------------------------------- fake_insurance (contracts section 10)

# Output fields and message lines: protected text that changes with the data. They
# are masked out of screen_id with the bridge's volatile-region mechanism, exactly
# as the real app's VOLATILE_REGIONS must be configured (otherwise every policy
# would be a different "screen" and per-screen key policies could never match).
DEMO_VOLATILE_REGIONS: tuple[Region, ...] = (
    (22, 1, 70),                                   # message line, all screens
    (5, 13, 20), (6, 13, 10), (7, 13, 10), (8, 13, 10),   # enquiry: holder, status, premium, upddate
    *[(6 + i, 1, 8) for i in range(8)],            # list rows: polno
    *[(6 + i, 11, 20) for i in range(8)],          # list rows: holder
    *[(6 + i, 33, 10) for i in range(8)],          # list rows: status
    (8, 13, 20),                                   # update: holder
    (3, 13, 8), (4, 13, 20), (6, 13, 1), (6, 25, 1), (7, 13, 7), (7, 25, 7),  # confirm
)

SEED_POLICIES: dict[str, dict[str, str]] = {
    f"P000000{i}": {"holder": h, "status": s, "premium": p, "upddate": d}
    for i, (h, s, p, d) in enumerate(
        [
            ("J. MARLOWE", "ACTIVE", "180.00", "2026-09-14"),
            ("K. OKAFOR", "ACTIVE", "320.50", "2026-10-02"),
            ("A. ROSE", "ACTIVE", "250.00", "2026-10-21"),
            ("T. NAKAMURA", "LAPSED", "410.00", "2026-06-30"),
            ("S. LINDQVIST", "ACTIVE", "95.75", "2026-08-11"),
            ("M. DUBOIS", "CANCELLED", "0.00", "2026-05-05"),
            ("R. PATEL", "ACTIVE", "540.00", "2026-10-29"),
            ("H. KOWALSKI", "LAPSED", "275.25", "2026-07-19"),
        ],
        start=1,
    )
}
_STATUS = {"A": "ACTIVE", "L": "LAPSED", "C": "CANCELLED"}
_LEGEND_ROW = 23


def _screens() -> dict[str, ScreenSpec]:
    vol = region_positions(DEMO_VOLATILE_REGIONS)
    msg = F("msg", 22, 1, 70)
    menu = build_screen(
        {(0, 1): "SEANCE INSURANCE - MAIN MENU", (3, 3): "1  POLICY ENQUIRY", (4, 3): "2  POLICY LIST",
         (5, 3): "3  POLICY UPDATE", (7, 3): "OPTION ===>", (_LEGEND_ROW, 1): "ENTER=SELECT  CLEAR=EXIT"},
        [F("option", 7, 15, 1, "in"), msg], cursor_field="option", volatile=vol)
    enquiry = build_screen(
        {(0, 1): "SEANCE INSURANCE - POLICY ENQUIRY", (3, 1): "POLNO ===>", (5, 1): "HOLDER:",
         (6, 1): "STATUS:", (7, 1): "PREMIUM:", (8, 1): "UPDATED:",
         (_LEGEND_ROW, 1): "ENTER=LOOK UP  PF3=BACK"},
        [F("polno", 3, 13, 8, "in"), F("holder", 5, 13, 20), F("status", 6, 13, 10),
         F("premium", 7, 13, 10), F("upddate", 8, 13, 10), msg], cursor_field="polno", volatile=vol)
    list_fields = [F("select", 3, 13, 2, "in")]
    for i in range(8):
        list_fields += [F(f"row{i}_polno", 6 + i, 1, 8), F(f"row{i}_holder", 6 + i, 11, 20),
                        F(f"row{i}_status", 6 + i, 33, 10)]
    plist = build_screen(
        {(0, 1): "SEANCE INSURANCE - POLICY LIST", (3, 1): "SELECT ===>", (5, 1): "POLNO     HOLDER               STATUS",
         (_LEGEND_ROW, 1): "PF7=UP  PF8=DOWN  PF3=BACK"},
        [*list_fields, msg], cursor_field="select", volatile=vol)
    update = build_screen(
        {(0, 1): "SEANCE INSURANCE - POLICY UPDATE", (3, 1): "POLNO ===>", (5, 1): "STATUS (A/L/C) ===>",
         (6, 1): "PREMIUM ===>", (8, 1): "HOLDER:", (_LEGEND_ROW, 1): "ENTER=REVIEW CHANGE  PF3=BACK"},
        [F("polno", 3, 13, 8, "in"), F("status", 5, 22, 1, "in"), F("premium", 6, 22, 7, "num"),
         F("holder", 8, 13, 20), msg], cursor_field="polno", volatile=vol)
    confirm = build_screen(
        {(0, 1): "SEANCE INSURANCE - CONFIRM UPDATE", (3, 1): "POLNO:", (4, 1): "HOLDER:",
         (5, 13): "OLD", (5, 25): "NEW", (6, 1): "STATUS:", (7, 1): "PREMIUM:",
         (_LEGEND_ROW, 1): "ENTER=CONFIRM AND SAVE  PF3=CANCEL"},
        [F("polno", 3, 13, 8), F("holder", 4, 13, 20), F("old_status", 6, 13, 1), F("new_status", 6, 25, 1),
         F("old_premium", 7, 13, 7), F("new_premium", 7, 25, 7), msg], volatile=vol)
    return {"menu": menu, "enquiry": enquiry, "list": plist, "update": update, "confirm": confirm}


def fake_insurance() -> FakeApp:
    """The 5-screen Seance Insurance demo app (contracts section 10).

    Only ENTER on ``confirm`` changes data; ``app.policies`` holds the records and
    ``app.dirty`` / ``app.mutations`` record that. ``app.reset()`` restores the
    8 seed policies."""
    app: FakeApp

    def seed(a: FakeApp) -> None:
        a.state["policies"] = copy.deepcopy(SEED_POLICIES)
        a.state["pending"] = None

    def policy(a: FakeApp, polno: str) -> dict[str, str] | None:
        return a.state["policies"].get(polno.strip().upper())

    def menu_enter(a: FakeApp, v: Values) -> None:
        opt = v.get("option", "").strip()
        if opt == "1":
            a.goto("enquiry")
        elif opt == "2":
            rows: dict[str, str] = {}
            for i, (no, p) in enumerate(sorted(a.state["policies"].items())[:8]):
                rows.update({f"row{i}_polno": no, f"row{i}_holder": p["holder"], f"row{i}_status": p["status"]})
            a.goto("list", **rows)
        elif opt == "3":
            a.goto("update")
        else:
            a.say("INVALID OPTION")

    def enquiry_enter(a: FakeApp, v: Values) -> None:
        p = policy(a, v.get("polno", ""))
        if p is None:
            a.set(holder="", status="", premium="", upddate="", msg="POLICY NOT FOUND")
        else:
            a.set(**p, msg="")

    def update_enter(a: FakeApp, v: Values) -> None:
        no = v.get("polno", "").strip().upper()
        p = policy(a, no)
        status = v.get("status", "").strip().upper()
        premium = v.get("premium", "").strip()
        if p is None:
            a.say("POLICY NOT FOUND")
        elif status and status not in _STATUS:
            a.say("STATUS MUST BE A, L OR C")
        elif not status and not premium:
            a.say("ENTER A NEW STATUS OR PREMIUM")
        else:
            new_status = _STATUS.get(status, p["status"])
            new_premium = f"{int(premium)}.00" if premium else p["premium"]
            a.state["pending"] = {"polno": no, "status": new_status, "premium": new_premium}
            a.goto("confirm", polno=no, holder=p["holder"], old_status=p["status"][:1], new_status=new_status[:1],
                   old_premium=p["premium"][:7], new_premium=new_premium[:7], msg="ENTER=CONFIRM  PF3=CANCEL")

    def confirm_enter(a: FakeApp, v: Values) -> None:
        pend = a.state["pending"]
        if pend is not None:
            rec = a.state["policies"][pend["polno"]]
            rec["status"], rec["premium"], rec["upddate"] = pend["status"], pend["premium"], "2026-11-24"
            a.state["pending"] = None
        a.goto("menu", msg="POLICY UPDATED")

    def confirm_cancel(a: FakeApp, v: Values) -> None:
        a.state["pending"] = None
        a.goto("menu", msg="UPDATE CANCELLED")

    rules = [
        Rule("*", "CLEAR", "menu"),
        Rule("menu", "ENTER", effect=menu_enter),
        Rule("menu", "PF3", effect=lambda a, v: a.say("USE CLEAR TO END")),
        Rule("enquiry", "ENTER", effect=enquiry_enter),
        Rule("enquiry", "PF3", "menu"),
        Rule("list", "PF3", "menu"),
        Rule("list", "PF7", effect=lambda a, v: a.say("TOP OF LIST")),
        Rule("list", "PF8", effect=lambda a, v: a.say("BOTTOM OF LIST")),
        Rule("update", "ENTER", effect=update_enter),
        Rule("update", "PF3", "menu"),
        Rule("confirm", "ENTER", effect=confirm_enter, mutating=True),
        Rule("confirm", "PF3", effect=confirm_cancel),
    ]
    app = FakeApp(_screens(), "menu", rules, on_reset=seed)
    seed(app)
    return app


def _policies(app: FakeApp) -> dict[str, dict[str, str]]:
    return app.state["policies"]


FakeApp.policies = property(_policies)  # type: ignore[attr-defined]

# Named fake apps a SEANCE_APP server can select (no container, never live-guarded).
FAKE_APPS: dict[str, "Callable[[], FakeApp]"] = {"fake-insurance": fake_insurance}

__all__ = [
    "CaptureError", "DEMO_VOLATILE_REGIONS", "F", "FAKE_APPS", "FakeApp", "FakePort", "H", "HN", "P", "PARSER",
    "Region", "Rule", "SEED_POLICIES", "ScreenSpec", "U", "UN", "build_screen", "fake_insurance", "logon_screen",
    "menu_screen", "rc", "region_positions",
]
