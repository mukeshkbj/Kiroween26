import json

import pytest
from hypothesis import given, settings, strategies as st

from seance_spirit.graph import (
    Fill, SpiritMap, assign_field_keys, field_key_base, merge,
)
from seance_spirit.ids import node_id
from seance_spirit.store import LeakError, dumps, map_to_obj, read_map, write_json, write_map

from .strategies import blank, shuffled, spirit_maps, nodes

SENTINEL = "@@HIDDEN-7f3a@@"


# -- field keys ------------------------------------------------------------------------------


def test_field_keys() -> None:
    assert field_key_base("POLNO ===>") == "polno"
    assert field_key_base("STATUS (A/L/C) ===>") == "status"
    assert field_key_base("") == "field"
    assert field_key_base("2ND LINE") == "f_2nd_line"
    assert assign_field_keys(["STATUS:", "STATUS:", "X", "STATUS:"]) == ["status", "status_2", "x", "status_3"]


@given(st.lists(st.text(max_size=20), max_size=10))
def test_field_keys_are_unique_snake_case(labels) -> None:
    keys = assign_field_keys(labels)
    assert len(set(keys)) == len(keys)
    import re
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", k) for k in keys)


# -- ids and canonical form ---------------------------------------------------------------------


@given(st.data())
def test_canonical_form_is_independent_of_order(data) -> None:
    m = data.draw(spirit_maps())
    s = shuffled(data.draw, m)
    assert s.canonical() == m.canonical()
    assert dumps(map_to_obj(s)) == dumps(map_to_obj(m))


@given(spirit_maps())
def test_node_ids_derive_from_screen_id(m: SpiritMap) -> None:
    assert all(n.id == node_id(n.screen_id) for n in m.nodes)
    assert len({n.id for n in m.nodes}) == len(m.nodes)


# -- merge ------------------------------------------------------------------------------------------


@given(spirit_maps())
def test_merge_is_idempotent(m: SpiritMap) -> None:
    merged, drift = merge(m, m)
    assert merged == m.canonical()
    assert drift.layout_changed == [] and drift.edges_changed == []


@given(spirit_maps(), spirit_maps())
def test_merge_keeps_everything_from_both(a: SpiritMap, b: SpiritMap) -> None:
    merged, _ = merge(a, b)
    assert {n.id for n in a.nodes} | {n.id for n in b.nodes} == {n.id for n in merged.nodes}
    assert {e.id for e in a.edges} | {e.id for e in b.edges} == {e.id for e in merged.edges}
    again, _ = merge(merged, b)
    assert again == merged


def test_merge_reports_drift() -> None:
    from seance_spirit.graph import Node

    old = SpiritMap(app_id="t")
    a = Node(id=node_id("a" * 64), screen_id="a" * 64, rows=[" " * 80] * 24, fields=[])
    b = Node(id=node_id("b" * 64), screen_id="b" * 64, rows=[" " * 80] * 24, fields=[])
    c = Node(id=node_id("c" * 64), screen_id="c" * 64, rows=[" " * 80] * 24, fields=[])
    old.nodes = [a, b, c]
    old.add_edge(a.id, "PF3", b.id, [], True, "not_commit_capable")
    new = SpiritMap(app_id="t", nodes=[a.model_copy(deep=True), c.model_copy(deep=True)])
    new.add_edge(a.id, "PF3", c.id, [], True, "not_commit_capable")
    merged, drift = merge(old, new)
    assert drift.edges_changed == [f"{a.id} PF3"]
    assert drift.nodes_not_seen == [b.id]
    assert len(merged.edges) == 2  # nothing is deleted


def test_merge_rejects_other_app() -> None:
    with pytest.raises(ValueError):
        merge(SpiritMap(app_id="a"), SpiritMap(app_id="b"))


# -- shortest path ----------------------------------------------------------------------------------


@given(spirit_maps(), st.data())
def test_shortest_path_is_valid_and_minimal(m: SpiritMap, data) -> None:
    ids = [n.id for n in m.nodes]
    src, dst = data.draw(st.sampled_from(ids)), data.draw(st.sampled_from(ids))
    path = m.shortest_path(src, dst)
    # independent model: BFS distances over read-only edges
    dist = {src: 0}
    frontier = [src]
    while frontier:
        nxt = []
        for cur in frontier:
            for e in m.edges:
                if e.read_only and e.from_ == cur and e.to not in dist:
                    dist[e.to] = dist[cur] + 1
                    nxt.append(e.to)
        frontier = nxt
    if dst not in dist:
        assert path is None
        return
    assert path is not None and len(path) == dist[dst]
    at = src
    for e in path:
        assert e.read_only and e.from_ == at
        at = e.to
    assert at == dst


def test_shortest_path_avoid_gives_alternative() -> None:
    m = SpiritMap(app_id="t")
    m.add_edge("a", "PF3", "b", [], True, "not_commit_capable")
    m.add_edge("a", "CLEAR", "b", [], True, "not_commit_capable")
    first = m.shortest_path("a", "b")
    second = m.shortest_path("a", "b", avoid=frozenset({first[0].id}))
    assert second and second[0].id != first[0].id
    assert m.shortest_path("a", "b", avoid=frozenset(e.id for e in m.edges)) is None


def test_non_read_only_edges_are_never_on_a_path() -> None:
    m = SpiritMap(app_id="t")
    m.add_edge("a", "ENTER", "b", [Fill(field="x", probe="p")], True, "declared")
    m.edges[0].read_only = False
    assert m.shortest_path("a", "b") is None


# -- store ------------------------------------------------------------------------------------------


@settings(max_examples=40)
@given(m=spirit_maps())
def test_write_then_read_is_identity(m: SpiritMap, tmp_path_factory) -> None:
    p = tmp_path_factory.mktemp("s") / "spirit-map.json"
    write_map(p, m)
    assert read_map(p) == m.canonical()
    assert json.loads(p.read_text(encoding="utf-8"))["schema"] == "gss.spiritmap/1"


@settings(max_examples=40)
@given(m=spirit_maps(), where=st.sampled_from(["row", "app", "frontier_key_field"]))
def test_sentinel_never_survives_a_write(m: SpiritMap, where: str, tmp_path_factory) -> None:
    p = tmp_path_factory.mktemp("s") / "spirit-map.json"
    bad = m.model_copy(deep=True)
    if where == "row":
        bad.nodes[0].rows[3] = SENTINEL.ljust(80)
    elif where == "app":
        bad.app_id = "x" + SENTINEL
    else:
        bad.run.reason = SENTINEL
    with pytest.raises(LeakError):
        write_map(p, bad, sentinels=[SENTINEL])
    assert not p.exists()
    assert list(p.parent.glob("*.tmp")) == []

def test_hidden_field_cells_must_be_blank(tmp_path) -> None:
    from seance_spirit.graph import FieldRec, Node

    rows = [" " * 80] * 24
    rows[5] = "   SECRETVALUE" + " " * 66
    f = FieldRec(key="pw", index=0, row=5, col=3, length=11, protected=False, numeric=False, hidden=True,
                 intensified=False, label="X")
    m = SpiritMap(app_id="t", nodes=[Node(id=node_id("a" * 64), screen_id="a" * 64, rows=rows, fields=[f])])
    with pytest.raises(LeakError):
        write_map(tmp_path / "m.json", m)
    # a credential-labelled field that is not hidden is checked too
    f2 = f.model_copy(update={"hidden": False, "label": "PASSWORD"})
    m.nodes[0].fields = [f2]
    with pytest.raises(LeakError):
        write_map(tmp_path / "m.json", m)


def test_write_is_atomic_when_serialising_fails(tmp_path) -> None:
    p = tmp_path / "x.json"
    write_json(p, {"a": 1})
    with pytest.raises(LeakError):
        write_json(p, {"a": SENTINEL}, sentinels=[SENTINEL])
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1}


def test_output_is_canonical_text(tmp_path) -> None:
    p = tmp_path / "x.json"
    write_json(p, {"b": 1, "a": [2, 1]})
    assert p.read_text(encoding="utf-8") == '{\n  "a": [\n    2,\n    1\n  ],\n  "b": 1\n}\n'
