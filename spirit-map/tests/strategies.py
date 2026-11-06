"""Hypothesis strategies shared by the spirit-map tests."""
from __future__ import annotations

from hypothesis import strategies as st

from seance_spirit.graph import Edge, FieldRec, Fill, Node, SpiritMap, assign_field_keys
from seance_spirit.ids import ALL_KEY_NAMES, COMMIT_CAPABLE_NAMES, edge_id, node_id

KEYS = sorted(ALL_KEY_NAMES)
LABELS = ["POLNO", "HOLDER", "STATUS", "PREMIUM", "OPTION", "PASSWORD", "SELECT", "MSG", ""]

screen_ids = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)
_row_text = st.text(alphabet=" ABCXYZ0123=>:", min_size=80, max_size=80)


def blank(rows: list[str], spans: list[tuple[int, int]]) -> list[str]:
    cells = [list(r) for r in rows]
    for start, end in spans:
        for pos in range(start, min(end, 1920)):
            cells[pos // 80][pos % 80] = " "
    return ["".join(r) for r in cells]


@st.composite
def nodes(draw, screen_id: str | None = None) -> Node:
    sid = screen_id or draw(screen_ids)
    base = draw(st.lists(_row_text, min_size=3, max_size=3))
    rows = [base[i % 3] for i in range(24)]
    n_fields = draw(st.integers(0, 4))
    labels = [draw(st.sampled_from(LABELS)) for _ in range(n_fields)]
    keys = assign_field_keys(labels)
    fields = []
    for i, (label, key) in enumerate(zip(labels, keys)):
        row = draw(st.integers(0, 23))
        col = draw(st.integers(1, 60))
        fields.append(FieldRec(
            key=key, index=i, row=row, col=col, length=draw(st.integers(1, 15)),
            protected=draw(st.booleans()), numeric=draw(st.booleans()), hidden=draw(st.booleans()),
            intensified=draw(st.booleans()), label=label, output=False))
    spans = [f.span for f in fields if f.hidden or "PASS" in f.label]
    return Node(id=node_id(sid), screen_id=sid, visits=draw(st.integers(1, 5)), rows=blank(rows, spans),
                fields=fields, volatile=[])


@st.composite
def spirit_maps(draw, max_nodes: int = 5) -> SpiritMap:
    sids = draw(st.lists(screen_ids, min_size=1, max_size=max_nodes, unique=True))
    ns = [draw(nodes(s)) for s in sids]
    m = SpiritMap(app_id="t", home=ns[0].id, nodes=ns)
    for _ in range(draw(st.integers(0, 8))):
        a, b = draw(st.sampled_from(ns)), draw(st.sampled_from(ns))
        key = draw(st.sampled_from(KEYS))
        fills = [Fill(field="polno", probe="known")] if draw(st.booleans()) else []
        ro = draw(st.booleans())
        m.add_edge(a.id, key, b.id, fills, ro, "declared" if key in COMMIT_CAPABLE_NAMES else "not_commit_capable")
        if not ro:
            m.edges[-1].read_only = False
    for _ in range(draw(st.integers(0, 3))):
        m.add_frontier(draw(st.sampled_from(ns)).id, draw(st.sampled_from(KEYS)),
                       draw(st.sampled_from(["denied_key", "denied_commit", "budget", "unvisited"])))
    m.prune_frontier()
    return m.canonical()


def shuffled(draw, m: SpiritMap) -> SpiritMap:
    c = m.model_copy(deep=True)
    c.nodes = draw(st.permutations(c.nodes))
    c.edges = draw(st.permutations(c.edges))
    c.frontier = draw(st.permutations(c.frontier))
    for n in c.nodes:
        n.fields = draw(st.permutations(n.fields))
    return c


__all__ = ["Edge", "edge_id", "nodes", "spirit_maps", "shuffled", "blank"]
