"""The explorer: deterministic, read-only discovery of an app's screens.

No LLM, no randomness. Safety layers (outermost first), see design.md:

1. the exploration ``SeanceService`` has ``allow_commit=False`` and nobody ever confirms;
2. ``EffectivePolicy.may_press`` is checked before every key (``Driver``);
3. the service's own gate treats a commit-capable key as read-only only where the
   policy says so (``ExplorerKeyPolicy``);
4. tests record every key the app actually received and check it against a model.

Halting: an ambiguous acknowledgement, a lost session, a pending action from the
gate or a route that lands wrongly twice ends the run. Nothing is retried or resent.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from seance_mcp.port import BridgePort
from seance_mcp.screens import FieldOut, ScreenOut

from .driver import (
    BudgetExhausted, FieldRejected, Halt, PolicyDenied, RouteMismatch, build_driver,
)
from .graph import (
    FieldRec, Fill, FrontierReason, Node, RunInfo, SpiritMap, assign_field_keys, label_from_rows,
)
from .ids import ALL_KEY_NAMES, COMMIT_CAPABLE_NAMES, key_name, looks_credential, node_id
from .policy import EffectivePolicy, Allow
from .seed import ExploreSeed
from .store import write_map

# After the human-declared keys: CLEAR first (the usual way home), then the cheap rest.
_OTHER_KEYS = ["CLEAR", "PA1", "PA2", "PA3"] + [f"PF{n}" for n in range(13, 25)]
_COMMIT_ORDER = ["ENTER"] + [f"PF{n}" for n in range(1, 13)]


@dataclass(frozen=True)
class FillSpec:
    field: str   # field key
    index: int
    probe: str   # probe name, or "harvest"
    value: str   # typed value; never stored in the map


@dataclass(frozen=True)
class Action:
    key: str
    fills: tuple[FillSpec, ...] = ()
    harvest: tuple[str, ...] = ()  # field keys to fill from harvested values at run time

    def ident(self) -> tuple:
        return (self.key, tuple((f.field, f.probe) for f in self.fills), self.harvest)


@dataclass
class QItem:
    node_id: str
    action: Action
    depth: int
    order: int


@dataclass
class ExploreReport:
    status: str
    reason: str | None
    steps: int
    nodes: int
    edges: int
    frontier: int


# ---------------------------------------------------------------- recording


def _blank(rows: list[str], positions: Iterable[int]) -> list[str]:
    cells = [list(r.ljust(80)[:80]) for r in rows]
    for pos in positions:
        if 0 <= pos < 1920:
            cells[pos // 80][pos % 80] = " "
    return ["".join(r) for r in cells]


def record_node(screen: ScreenOut, seed: ExploreSeed) -> Node:
    """A node from a screen. Cells of unprotected fields (typed input), hidden fields,
    credential-labelled fields and volatile regions are blanked, so the stored rows
    hold only the app's own static text and are stable across visits."""
    regions = {tuple(r) for r in seed.volatile}
    blank: set[int] = set()
    keep: list[FieldOut] = []
    outputs: set[int] = set()
    for f in screen.fields:
        span = range(f.row * 80 + f.col, f.row * 80 + f.col + f.length)
        if not f.protected:
            keep.append(f)
            blank.update(span)
        elif (f.row, f.col, f.length) in regions:
            # A protected field whose span is exactly a volatile region is an output field:
            # its text is data, not part of the screen's identity.
            keep.append(f)
            outputs.add(f.index)
            blank.update(span)
        elif f.hidden or looks_credential(f.label):
            blank.update(span)
    rows = _blank(list(screen.rows), blank)
    labels = [label_from_rows(rows, f.row, f.col) for f in keep]
    keys = assign_field_keys(labels, [(f.row, f.col) for f in keep])
    fields = [
        FieldRec(key=k, index=f.index, row=f.row, col=f.col, length=f.length, protected=f.protected,
                 numeric=f.numeric, hidden=f.hidden, intensified=f.intensified, label=lab,
                 output=f.index in outputs)
        for f, lab, k in zip(keep, labels, keys)
    ]
    return Node(id=node_id(screen.screen_id), screen_id=screen.screen_id, visits=1, rows=rows,
                fields=fields, volatile=[tuple(v) for v in seed.volatile])  # type: ignore[misc]


def advertised_keys(rows: Iterable[str]) -> set[str]:
    import re

    rx = re.compile(r"\b(ENTER|CLEAR|PA[123]|PF(?:[1-9]|1\d|2[0-4]))\s*[=:]", re.IGNORECASE)
    return {key_name(m.group(1)) for row in rows for m in rx.finditer(row)}


# ---------------------------------------------------------------- the explorer


class Explorer:
    def __init__(
        self,
        port: BridgePort,
        seed: ExploreSeed,
        *,
        approved: dict[str, frozenset[str]] | None = None,
        attach: bool = False,
        out_path: Path | None = None,
        sentinels: Iterable[str] = (),
        audit_path: Path | None = None,
        host: str = "localhost",
        tn_port: int = 3270,
        clock: Callable[[], float] = time.monotonic,
        started_at: str | None = None,
        policy_factory: Callable[..., EffectivePolicy] = EffectivePolicy,
    ):
        self.seed = seed
        self.attach, self.out_path = attach, out_path
        self.sentinels = tuple(sentinels)
        self.host, self.tn_port = host, tn_port
        self.driver = build_driver(port, seed, approved=approved, audit_path=audit_path, host=host,
                                   tn_port=tn_port, clock=clock, policy_factory=policy_factory)
        self.policy, self.service = self.driver.policy, self.driver.service
        b = seed.budgets
        self.map = SpiritMap(app_id=seed.app_id, run=RunInfo(
            id="r_1", started_at=started_at, status="running",
            budgets={"max_screens": b.max_screens, "max_steps": b.max_steps, "max_depth": b.max_depth}))
        self.depth: dict[str, int] = {}
        self.queue: list[QItem] = []
        self.done: set[tuple] = set()
        self.cur: str | None = None
        self._order = 0
        self._failed: set[str] = set()
        self.harvested: dict[str, str] = {}

    # -- public --------------------------------------------------------------------

    async def run(self) -> ExploreReport:
        status, reason = "completed", None
        try:
            await self._start()
            await self._loop()
        except BudgetExhausted:
            status, reason = "budget", "steps_or_time"
        except _ScreenBudget:
            status, reason = "budget", "screens"
        except Halt as h:
            status, reason = "halted", h.reason
        for item in self.queue:
            self.map.add_frontier(item.node_id, item.action.key,
                                  "budget" if status == "budget" else "unvisited",
                                  [Fill(field=f.field, probe=f.probe) for f in item.action.fills])
        self.map.prune_frontier()
        self.map.run.status = status  # type: ignore[assignment]
        self.map.run.reason = reason
        self.map.run.steps = self.driver.steps
        self._save()
        return ExploreReport(status, reason, self.driver.steps, len(self.map.nodes), len(self.map.edges),
                             len(self.map.frontier))

    # -- start -------------------------------------------------------------------------

    async def _start(self) -> None:
        if self.attach:
            screen = await self.driver.read()
        else:
            screen = await self.driver.connect(self.host, self.tn_port)
        for key in self.seed.start_recipe:
            try:
                screen = await self.driver.press(key)
            except PolicyDenied as d:
                raise Halt("start_recipe_denied", d.reason) from None
        node = self._see(screen, frm=None)
        self.map.home = node.id
        self.cur = node.id

    # -- recording ------------------------------------------------------------------------

    def _see(self, screen: ScreenOut, frm: str | None) -> Node:
        """Record a screen as a node (new or revisited) and queue its actions if new."""
        nid = node_id(screen.screen_id)
        known = self.map.node(nid) is not None
        node = self.map.add_node(record_node(screen, self.seed))
        if not known:
            self.depth[nid] = 0 if frm is None else self.depth.get(frm, 0) + 1
            self.policy.learn_hints(screen.screen_id, screen.rows)
            self._queue_node(node, screen)
            self._save()
        self._harvest(node, screen)
        return node

    def _harvest(self, node: Node, screen: ScreenOut) -> None:
        if not self.seed.harvest:
            return
        by_index = {f.index: f for f in screen.fields}
        for rec in node.fields:
            f = by_index[rec.index]
            if f.hidden or f.value is None or looks_credential(f.label) or looks_credential(rec.label):
                continue
            v = f.value.strip()
            if rec.output and v and len(v) <= 40:
                self.harvested.setdefault(rec.key, v)

    # -- candidate actions ---------------------------------------------------------------------

    def _queue_node(self, node: Node, screen: ScreenOut) -> None:
        sid = node.screen_id
        depth = self.depth[node.id]
        if depth > self.seed.budgets.max_depth:
            self.map.add_frontier(node.id, "ENTER", "budget")
            return
        # Frontier: what we will not do here, with the reason.
        wanted = {"ENTER"} | {k for k in advertised_keys(screen.rows) if k in COMMIT_CAPABLE_NAMES}
        for k in sorted(wanted, key=_COMMIT_ORDER.index):
            d = self.policy.may_press(k, sid)
            if not d.allowed:
                self.map.add_frontier(node.id, k, _frontier_reason(d.reason))
        for f in node.fields:
            if not f.protected and (f.hidden or looks_credential(f.label) or self.seed.label_denied(f.label)):
                self.map.add_frontier(node.id, "ENTER", "unsafe_field", [Fill(field=f.key, probe="-")])
        # Candidates: declared/approved keys first (with fills), then the cheap navigation keys.
        declared = [k for k in sorted(ALL_KEY_NAMES, key=lambda k: (_COMMIT_ORDER + _OTHER_KEYS).index(k))
                    if self.policy.may_press(k, sid).allowed and
                    (k in self.policy.read_only_keys(sid))]
        others = [k for k in _OTHER_KEYS if k not in declared and self.policy.may_press(k, sid).allowed]
        alts = self._fill_alternatives(node)
        harvest_fields = self._harvest_fields(node) if self.seed.harvest else ()
        actions: list[Action] = []
        for k in declared:
            if k != "ENTER":  # only the submit key carries typed input; the rest are tried bare
                actions.append(Action(k))
            elif alts:
                actions += [Action(k, a) for a in alts]
            else:
                actions.append(Action(k))
            if k == "ENTER" and harvest_fields:
                actions.append(Action(k, (), harvest_fields))
        actions += [Action(k) for k in others]
        cap = self.seed.budgets.fanout
        # Only declared keys are worth listing when the fanout cuts them off; the cheap
        # navigation keys (PA1-3, PF13-24) are simply not all tried, which is not news.
        for a in actions[cap:]:
            if a.key in declared:
                self.map.add_frontier(node.id, a.key, "budget", [Fill(field=f.field, probe=f.probe) for f in a.fills])
        for a in actions[:cap]:
            self._order += 1
            self.queue.append(QItem(node.id, a, depth, self._order))

    def _fillable(self, node: Node) -> list[FieldRec]:
        return [f for f in node.fields if not f.protected and not f.hidden
                and not looks_credential(f.label) and not self.seed.label_denied(f.label)]

    def _fill_alternatives(self, node: Node) -> list[tuple[FillSpec, ...]]:
        per_field: list[tuple[FieldRec, list]] = []
        for f in self._fillable(node):
            ps = [p for p in self.seed.probes if p.matches(f.label)]
            if ps:
                per_field.append((f, ps))
        if not per_field:
            return []
        n = max(len(ps) for _, ps in per_field)
        out: list[tuple[FillSpec, ...]] = []
        for i in range(n):
            spec = tuple(FillSpec(f.key, f.index, ps[min(i, len(ps) - 1)].name, ps[min(i, len(ps) - 1)].value)
                         for f, ps in per_field)
            if spec not in out:
                out.append(spec)
        return out

    def _harvest_fields(self, node: Node) -> tuple[str, ...]:
        return tuple(f.key for f in self._fillable(node) if self.seed.probe_for(f.label) is None)

    # -- the loop --------------------------------------------------------------------------------

    def _next(self) -> QItem | None:
        live = [q for q in self.queue
                if (q.node_id, *q.action.ident()) not in self.done]
        self.queue = live
        if not live:
            return None
        best = min(live, key=lambda q: (q.depth, 0 if q.node_id == self.cur else 1, q.order))
        self.queue.remove(best)
        return best

    async def _loop(self) -> None:
        while True:
            if len(self.map.nodes) >= self.seed.budgets.max_screens:
                raise _ScreenBudget()
            item = self._next()
            if item is None:
                return
            try:
                await self._execute(item)
            except PolicyDenied as d:
                self.map.add_frontier(item.node_id, item.action.key, _frontier_reason(d.reason))
            except FieldRejected:
                self.map.add_frontier(item.node_id, item.action.key, "unsafe_field")
            except _Unreachable:
                self.map.add_frontier(item.node_id, item.action.key, "unvisited")
    async def _execute(self, item: QItem) -> None:
        node = self.map.node(item.node_id)
        assert node is not None
        await self._goto(item.node_id)
        await self._clear_inputs(node)
        fills = list(item.action.fills)
        for key in item.action.harvest:
            rec = node.field(key)
            value = self._harvest_value(key)
            if rec is not None and value is not None:
                fills.append(FillSpec(key, rec.index, "harvest", value))
        if item.action.harvest and not fills:
            return  # nothing harvested yet: the bare action is queued separately
        if (item.node_id, *Action(item.action.key, tuple(fills)).ident()) in self.done:
            return
        for f in fills:
            await self.driver.fill(f.index, f.value)
        decision = self.policy.may_press(item.action.key, node.screen_id)
        landed = await self.driver.press(item.action.key)
        why = decision.reason if isinstance(decision, Allow) else "not_commit_capable"
        edge_fills = [Fill(field=f.field, probe=f.probe) for f in fills]
        self._land(node, item.action.key, edge_fills, landed, why)
        self.done.add((item.node_id, *Action(item.action.key, tuple(fills)).ident()))
        self.done.add((item.node_id, *item.action.ident()))

    def _harvest_value(self, key: str) -> str | None:
        if key in self.harvested:
            return self.harvested[key]
        return next((v for k, v in sorted(self.harvested.items()) if k.endswith("_" + key)), None)

    def _land(self, frm: Node, key: str, fills: list[Fill], landed: ScreenOut, why: str) -> Node:
        to = self._see(landed, frm.id)
        self.map.add_edge(frm.id, key, to.id, fills, True, why)  # type: ignore[arg-type]
        self.cur = to.id
        self.map.prune_frontier()
        return to

    async def _clear_inputs(self, node: Node) -> None:
        """Blank leftover typed input, so a bare action really is bare."""
        screen = self.driver.screen
        assert screen is not None
        for f in screen.fields:
            if f.protected or f.hidden or looks_credential(f.label) or self.seed.label_denied(f.label):
                continue
            if (f.value or "").strip():
                await self.driver.fill(f.index, "")

    # -- navigation -----------------------------------------------------------------------------------

    async def _goto(self, target: str) -> None:
        """Be on ``target``, using recorded read-only routes, verifying every landing."""
        assert self.cur is not None
        if self.cur == target:
            return
        mismatches = 0
        reset_done = False
        while True:
            path = self.map.shortest_path(self.cur, target, avoid=frozenset(self._failed))
            if path is None:
                if reset_done:
                    raise _Unreachable()
                reset_done = True
                await self._reset()
                if self.cur == target:
                    return
                continue
            try:
                await self.driver.follow(self.map, path)
                self.cur = target
                return
            except RouteMismatch as m:
                self._failed.add(m.edge.id)
                src = self.map.node(m.edge.from_)
                assert src is not None
                self._land(src, m.edge.key, list(m.edge.fills), m.landed, "not_commit_capable")
                mismatches += 1
                if mismatches >= 2:
                    raise Halt("lost", "a recorded route did not land as recorded, twice") from None
                if self.cur == target:
                    return

    async def _reset(self) -> None:
        """Press the seed's start recipe (default CLEAR) from wherever we are, as a normal edge."""
        keys = self.seed.start_recipe or ["CLEAR"]
        for key in keys:
            frm = self.map.node(self.cur) if self.cur else None
            assert frm is not None
            decision = self.policy.may_press(key, frm.screen_id)
            if not decision.allowed:
                return
            landed = await self.driver.press(key)
            why = decision.reason if isinstance(decision, Allow) else "not_commit_capable"
            self._land(frm, key, [], landed, why)
            self.done.add((frm.id, key, (), ()))

    # -- output -------------------------------------------------------------------------------------------

    def _save(self) -> None:
        if self.out_path is not None:
            write_map(self.out_path, self.map, self.sentinels)


class _ScreenBudget(Exception):
    """The map has max_screens nodes: a normal end."""


class _Unreachable(Exception):
    """No read-only route to the node; the action is left on the frontier."""


def _frontier_reason(reason: str) -> FrontierReason:
    return {
        "denied_key": "denied_key",
        "denied_screen": "denied_screen",
        "commit_capable": "denied_commit",
        "denied_hint": "denied_commit",  # a legend said it saves/deletes: treated as a commit key
        "unsafe_field": "unsafe_field",
    }.get(reason, "denied_key")  # type: ignore[return-value]
