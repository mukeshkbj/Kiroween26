"""Candidate read-only keys with evidence (REQ-025). Deterministic; no labels, ever.

A candidate is only ever a **proposal** shown to a human with its evidence. Promotion to
`key-policy.json` is a human act (`review --policy`). The rules:

1. **Display-only screen.** A node with no unprotected input field: ENTER cannot submit a
   change, so ENTER is a candidate.
2. **Navigation key.** A key whose every observed landing is a *previously known* node (a node
   nearer `home`, or the same node) across all observations: a candidate.
3. **Declared and behaved.** The seed declared the key read-only for this screen and every
   observation landed on a recorded node: a candidate (evidence cites the declaration).

Every candidate records why. A commit-capable key with no evidence is never proposed.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .graph import SpiritMap
from .ids import is_commit_capable
from .seed import ExploreSeed


@dataclass
class Candidate:
    screen_id: str
    key: str
    rules: list[str] = field(default_factory=list)   # which rules fired
    evidence: list[str] = field(default_factory=list)  # human-readable lines


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


def candidates(m: SpiritMap, seed: ExploreSeed) -> list[Candidate]:
    depth = _depths(m)
    out: dict[tuple[str, str], Candidate] = {}

    def cand(screen_id: str, key: str) -> Candidate:
        return out.setdefault((screen_id, key), Candidate(screen_id, key))

    # A key observed to commit (frontier denied_commit) is never a candidate on that screen,
    # whatever other rule might fire. This is the confirm screen's ENTER.
    commits: set[tuple[str, str]] = set()
    for fr in m.frontier:
        node = next((n for n in m.nodes if n.id == fr.from_), None)
        if node is not None and fr.reason == "denied_commit":
            commits.add((node.screen_id, fr.key))

    # Rule 1: display-only screens -> ENTER (unless ENTER is observed to commit here)
    for node in m.nodes:
        if (node.screen_id, "ENTER") in commits:
            continue
        if not any(not f.protected for f in node.fields):
            c = cand(node.screen_id, "ENTER")
            c.rules.append("display_only")
            c.evidence.append(f"{node.id} has no input field, so ENTER cannot submit a change")

    # Rules 2 and 3: per key observed on a screen
    by_node_key: dict[tuple[str, str], list] = {}
    for e in m.edges:
        by_node_key.setdefault((e.from_, e.key), []).append(e)
    nodes_by_id = {n.id: n for n in m.nodes}
    for (from_id, key), edges in by_node_key.items():
        node = nodes_by_id.get(from_id)
        if node is None or not is_commit_capable(key) or (node.screen_id, key) in commits:
            continue
        landings = {e.to for e in edges}
        observed = sum(e.observed for e in edges)
        # Rule 2: navigation key -> every landing is this node or a node nearer home
        if all(to == from_id or depth.get(to, 10**9) <= depth.get(from_id, -1) for to in landings):
            c = cand(node.screen_id, key)
            c.rules.append("navigation")
            where = ", ".join(sorted(t[:10] for t in landings))
            c.evidence.append(f"{key} on {node.id} always lands on a prior/same node ({where}); {observed} obs")
        # Rule 3: declared and every landing is a recorded node
        declared = key in seed.declared_read_only.get(from_id, ()) or key in seed.declared_read_only.get(node.screen_id, ())
        if declared and all(to in nodes_by_id for to in landings):
            c = cand(node.screen_id, key)
            c.rules.append("declared_behaved")
            c.evidence.append(f"{key} on {node.id} was seed-declared read-only and every landing is recorded")

    return [c for c in out.values() if c.rules]


def proposed_policy(m: SpiritMap, seed: ExploreSeed) -> tuple[dict[str, dict[str, list[str]]], dict]:
    """Return (key-policy.proposed.json, key-policy.evidence.json). Non-commit keys are never
    listed: they do not need an override."""
    cands = candidates(m, seed)
    policy: dict[str, set[str]] = {}
    evidence: dict[str, list[dict]] = {}
    for c in cands:
        policy.setdefault(c.screen_id, set()).add(c.key)
        evidence.setdefault(c.screen_id, []).append(
            {"key": c.key, "rules": sorted(set(c.rules)), "evidence": c.evidence})
    policy_json = {sid: {"read_only_keys": sorted(keys, key=_key_order)} for sid, keys in sorted(policy.items())}
    evidence_json = {"schema": "gss.keypolicy.evidence/1", "app_id": m.app_id,
                     "screens": {sid: evidence[sid] for sid in sorted(evidence)}}
    return policy_json, evidence_json


def _key_order(k: str) -> tuple[int, int]:
    order = ["ENTER", "CLEAR", "PA1", "PA2", "PA3"] + [f"PF{n}" for n in range(1, 25)]
    return (order.index(k) if k in order else 99, 0)
