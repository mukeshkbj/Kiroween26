"""The spirit map: a graph of screens (nodes), the keys between them (edges) and what
was not explored (frontier). Pure data plus pure functions; no I/O, no LLM.

Format: ``gss.spiritmap/1`` (spirit-map design.md). The map holds no labels: those
live in ``labels.json`` and have no authority over anything here.
"""
from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .ids import edge_id, key_name, node_id

SCHEMA = "gss.spiritmap/1"
Region = tuple[int, int, int]

FrontierReason = Literal[
    "denied_key", "denied_screen", "denied_commit", "unsafe_field", "budget", "unvisited"
]
WhyReadOnly = Literal["not_commit_capable", "declared", "approved_policy"]
RunStatus = Literal["running", "completed", "halted", "budget"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---------------------------------------------------------------- field keys


def field_key_base(label: str) -> str:
    """Stable snake_case key from a label: ``POLNO ===>`` -> ``polno``,
    ``STATUS (A/L/C) ===>`` -> ``status``. Empty labels give ``field``."""
    text = re.sub(r"\([^)]*\)", " ", label or "")
    words = re.findall(r"[A-Za-z0-9]+", text)
    key = "_".join(w.lower() for w in words)[:32].strip("_")
    if not key or not key[0].isalpha():
        key = ("f_" + key).strip("_") if key else "field"
    return key


def assign_field_keys(labels: Iterable[str]) -> list[str]:
    """Keys for fields in reading order. Repeated labels get ``_2``, ``_3`` by position."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for label in labels:
        base = field_key_base(label)
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    return out


def label_from_rows(rows: list[str], row: int, col: int) -> str:
    """The same label rule the MCP tools use (text left of the field), on stored rows."""
    from seance_mcp.screens import field_label

    return field_label(SimpleNamespace(rows=rows), SimpleNamespace(row=row, col=col))  # type: ignore[arg-type]


# ---------------------------------------------------------------- records


class FieldRec(_M):
    key: str
    index: int
    row: int
    col: int
    length: int
    protected: bool
    numeric: bool
    hidden: bool
    intensified: bool
    label: str
    output: bool = False  # protected field whose text is data (inside a volatile region)

    @property
    def span(self) -> tuple[int, int]:
        start = self.row * 80 + self.col
        return start, start + self.length


class Node(_M):
    id: str
    screen_id: str
    visits: int = 1
    rows: list[str]
    fields: list[FieldRec]
    volatile: list[Region] = []

    def field(self, key: str) -> FieldRec | None:
        return next((f for f in self.fields if f.key == key), None)


class Fill(_M):
    field: str
    probe: str  # probe name or "harvest"; never a typed value


class Edge(_M):
    id: str
    from_: str = Field(alias="from")
    to: str
    key: str
    fills: list[Fill] = []
    read_only: bool
    why_read_only: WhyReadOnly
    observed: int = 1

    def fill_tuple(self) -> tuple[tuple[str, str], ...]:
        return tuple((f.field, f.probe) for f in self.fills)


class FrontierItem(_M):
    from_: str = Field(alias="from")
    key: str
    fills: list[Fill] = []
    reason: FrontierReason

    def sort_key(self) -> tuple:
        return (self.from_, self.key, tuple((f.field, f.probe) for f in self.fills), self.reason)


class RunInfo(_M):
    id: str = "r_0"
    started_at: str | None = None
    status: RunStatus = "completed"
    reason: str | None = None
    steps: int = 0
    budgets: dict[str, float] = {}


class SpiritMap(_M):
    schema_: str = Field(default=SCHEMA, alias="schema")
    app_id: str
    run: RunInfo = RunInfo()
    home: str | None = None
    nodes: list[Node] = []
    edges: list[Edge] = []
    frontier: list[FrontierItem] = []

    # -- access ----------------------------------------------------------------

    def node(self, nid: str) -> Node | None:
        return next((n for n in self.nodes if n.id == nid), None)

    def node_by_screen(self, screen_id: str) -> Node | None:
        return self.node(node_id(screen_id))

    def edges_from(self, nid: str) -> list[Edge]:
        return [e for e in self.edges if e.from_ == nid]

    # -- mutation (used by the explorer; keeps ids stable) -----------------------

    def add_node(self, node: Node) -> Node:
        """Add a node, or count a revisit. The first sighting's rows and fields stay."""
        have = self.node(node.id)
        if have is not None:
            have.visits += 1
            return have
        self.nodes.append(node)
        return node

    def add_edge(self, frm: str, key: str, to: str, fills: list[Fill], read_only: bool,
                 why: WhyReadOnly) -> Edge:
        k = key_name(key)
        eid = edge_id(frm, k, tuple((f.field, f.probe) for f in fills), to)
        have = next((e for e in self.edges if e.id == eid), None)
        if have is not None:
            have.observed += 1
            return have
        edge = Edge.model_validate({"id": eid, "from": frm, "to": to, "key": k, "fills": fills,
                                    "read_only": read_only, "why_read_only": why})
        self.edges.append(edge)
        return edge

    def add_frontier(self, frm: str, key: str, reason: FrontierReason, fills: list[Fill] | None = None) -> None:
        item = FrontierItem.model_validate({"from": frm, "key": key_name(key), "fills": fills or [], "reason": reason})
        if item.sort_key() not in {f.sort_key() for f in self.frontier}:
            self.frontier.append(item)

    def prune_frontier(self) -> None:
        """Drop frontier entries that were later executed as edges."""
        done = {(e.from_, e.key, e.fill_tuple()) for e in self.edges}
        self.frontier = [f for f in self.frontier
                         if (f.from_, f.key, tuple((x.field, x.probe) for x in f.fills)) not in done]

    # -- canonical form -----------------------------------------------------------

    def canonical(self) -> "SpiritMap":
        """A copy with stable ordering so that diffs are meaningful."""
        m = self.model_copy(deep=True)
        m.nodes = sorted(m.nodes, key=lambda n: n.id)
        for n in m.nodes:
            n.fields = sorted(n.fields, key=lambda f: f.index)
        m.edges = sorted(m.edges, key=lambda e: e.id)
        m.frontier = sorted(m.frontier, key=FrontierItem.sort_key)
        return m

    # -- paths ----------------------------------------------------------------------

    def shortest_path(self, src: str, dst: str, *, avoid: frozenset[str] = frozenset()) -> list[Edge] | None:
        """Shortest route over recorded **read-only** edges (deterministic tie-break by edge id).
        ``avoid`` lists edge ids to skip (used to try an alternative return route)."""
        if src == dst:
            return []
        out: dict[str, list[Edge]] = {}
        for e in sorted(self.edges, key=lambda e: e.id):
            if e.read_only and e.id not in avoid:
                out.setdefault(e.from_, []).append(e)
        prev: dict[str, Edge] = {}
        seen = {src}
        q = deque([src])
        while q:
            cur = q.popleft()
            for e in out.get(cur, []):
                if e.to in seen:
                    continue
                seen.add(e.to)
                prev[e.to] = e
                if e.to == dst:
                    path: list[Edge] = []
                    at = dst
                    while at != src:
                        path.append(prev[at])
                        at = prev[at].from_
                    return path[::-1]
                q.append(e.to)
        return None


# ---------------------------------------------------------------- merge and drift


@dataclass
class Drift:
    layout_changed: list[str] = field(default_factory=list)   # node ids whose fields differ
    edges_changed: list[str] = field(default_factory=list)    # "from key" pairs now landing elsewhere
    nodes_not_seen: list[str] = field(default_factory=list)   # in the old map, absent from the new run

    def empty(self) -> bool:
        return not (self.layout_changed or self.edges_changed or self.nodes_not_seen)


def _layout(n: Node) -> list:
    return [(f.key, f.row, f.col, f.length, f.protected, f.numeric, f.hidden) for f in n.fields]


def merge(old: SpiritMap, new: SpiritMap) -> tuple[SpiritMap, Drift]:
    """Merge a new run into an existing map. Idempotent: ``merge(m, m)`` is ``m``.

    Counts take the high-water mark (so merging a map with itself changes nothing).
    The new run's status wins; the old home is kept unless the new run has one.
    Nothing is deleted: drift is reported, the human decides."""
    if old.app_id != new.app_id:
        raise ValueError(f"cannot merge maps of different apps: {old.app_id} vs {new.app_id}")
    out = old.model_copy(deep=True)
    drift = Drift()
    for n in new.nodes:
        have = out.node(n.id)
        if have is None:
            out.nodes.append(n.model_copy(deep=True))
        else:
            if _layout(have) != _layout(n):
                drift.layout_changed.append(n.id)
            have.visits = max(have.visits, n.visits)
    new_ids = {n.id for n in new.nodes}
    drift.nodes_not_seen = sorted(n.id for n in old.nodes if n.id not in new_ids)
    old_landing = {(e.from_, e.key, e.fill_tuple()): e.to for e in old.edges}
    for e in new.edges:
        have_e = next((x for x in out.edges if x.id == e.id), None)
        if have_e is not None:
            have_e.observed = max(have_e.observed, e.observed)
            continue
        prior = old_landing.get((e.from_, e.key, e.fill_tuple()))
        if prior is not None and prior != e.to:
            drift.edges_changed.append(f"{e.from_} {e.key}")
        out.edges.append(e.model_copy(deep=True))
    for f in new.frontier:
        out.add_frontier(f.from_, f.key, f.reason, list(f.fills))
    out.prune_frontier()
    out.home = new.home or old.home
    out.run = new.run.model_copy(deep=True)
    drift.layout_changed = sorted(set(drift.layout_changed))
    drift.edges_changed = sorted(set(drift.edges_changed))
    return out.canonical(), drift
