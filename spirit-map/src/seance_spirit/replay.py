"""Replay a stored map: re-execute every recorded edge and check it still lands on the
recorded ``screen_id``. Used for drift detection (REQ-012/013).

It obeys the same policy as the explorer: an edge whose key is commit-capable replays
only if the seed declares it (or the approved policy lists it). It checks ``screen_id``
only, never data, and never resends a key whose acknowledgement is ambiguous.
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from seance_mcp.port import BridgePort

from .driver import (
    BudgetExhausted, FieldRejected, Halt, PolicyDenied, RouteMismatch, build_driver,
)
from .graph import Edge, SpiritMap
from .policy import EffectivePolicy
from .seed import ExploreSeed


@dataclass
class Mismatch:
    edge_id: str
    from_node: str
    key: str
    expected: str
    landed_screen_id: str


@dataclass
class ReplayReport:
    ok: bool = False
    replayed: list[str] = field(default_factory=list)      # edge ids that landed as recorded
    mismatches: list[Mismatch] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)  # edge id -> reason
    halted: str | None = None
    keys_sent: list[tuple[str, str]] = field(default_factory=list)


def _depths(m: SpiritMap) -> dict[str, int]:
    out: dict[str, int] = {}
    if m.home is None:
        return out
    out[m.home] = 0
    q = deque([m.home])
    while q:
        cur = q.popleft()
        for e in sorted(m.edges_from(cur), key=lambda e: e.id):
            if e.to not in out:
                out[e.to] = out[cur] + 1
                q.append(e.to)
    return out


async def replay_map(
    port: BridgePort,
    m: SpiritMap,
    seed: ExploreSeed,
    *,
    approved: Mapping[str, frozenset[str]] | None = None,
    attach: bool = False,
    host: str = "localhost",
    tn_port: int = 3270,
    audit_path: Path | None = None,
    clock: Callable[[], float] = time.monotonic,
    policy_factory: Callable[..., EffectivePolicy] = EffectivePolicy,
) -> ReplayReport:
    rep = ReplayReport()
    driver = build_driver(port, seed, approved=approved, audit_path=audit_path, host=host, tn_port=tn_port,
                          clock=clock, policy_factory=policy_factory)
    try:
        await _run(driver, m, seed, rep, attach, host, tn_port)
    except Halt as h:
        rep.halted = h.reason
    except BudgetExhausted:
        rep.halted = "budget"
    rep.keys_sent = list(driver.keys_sent)
    rep.ok = rep.halted is None and not rep.mismatches
    return rep


async def _run(driver, m: SpiritMap, seed: ExploreSeed, rep: ReplayReport, attach: bool,
               host: str, tn_port: int) -> None:
    screen = await driver.read() if attach else await driver.connect(host, tn_port)
    for key in seed.start_recipe:
        screen = await driver.press(key)
    home = m.node(m.home) if m.home else None
    if home is None:
        raise Halt("no_home", "the map has no home node")
    if screen.screen_id != home.screen_id:
        raise Halt("not_at_home", "the session is not on the map's home screen")
    cur: str | None = home.id
    depth = _depths(m)
    for edge in sorted(m.edges, key=lambda e: (depth.get(e.from_, 10**6), e.id)):
        if cur is None:
            rep.skipped[edge.id] = "position_unknown"
            continue
        reason = _unreplayable(driver, m, edge)
        if reason:
            rep.skipped[edge.id] = reason
            continue
        path = m.shortest_path(cur, edge.from_)
        if path is None:
            rep.skipped[edge.id] = "no_route"
            continue
        try:
            await driver.follow(m, path)
            cur = edge.from_
            await driver.follow(m, [edge])
            cur = edge.to
            rep.replayed.append(edge.id)
        except RouteMismatch as mm:
            rep.mismatches.append(Mismatch(mm.edge.id, mm.edge.from_, mm.edge.key,
                                           m.node(mm.edge.to).screen_id, mm.landed.screen_id))  # type: ignore[union-attr]
            landed = m.node_by_screen(mm.landed.screen_id)
            cur = landed.id if landed else None
        except PolicyDenied as d:
            rep.skipped[edge.id] = f"denied:{d.reason}"
        except FieldRejected:
            rep.skipped[edge.id] = "field_rejected"


def _unreplayable(driver, m: SpiritMap, edge: Edge) -> str | None:
    for f in edge.fills:
        if driver.probe_value(f.probe) is None:
            return "no_probe_value"  # e.g. harvested values are not stored
    return None
