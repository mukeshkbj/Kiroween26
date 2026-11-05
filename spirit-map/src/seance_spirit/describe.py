"""app-description.md, generated deterministically from map + labels + tool pack (REQ-026).

Screens, fields, a Mermaid flow, the tools, and the frontier of unexplored or denied edges and
open review items. Everything here is derived; no hidden values, screen text sanitised by labels.
"""
from __future__ import annotations

from .graph import SpiritMap
from .labels import Labels, clean_text

_FRONTIER = {
    "denied_commit": "needs a human-confirmed commit",
    "denied_key": "key denied by policy",
    "denied_screen": "screen denied by policy",
    "unsafe_field": "would fill a hidden/credential field",
    "budget": "not explored (budget)",
    "unvisited": "not explored",
}


def _name(labels: Labels, node_id: str) -> str:
    nl = labels.node(node_id)
    return nl.name if nl and nl.name else node_id


def describe(m: SpiritMap, labels: Labels, pack: dict) -> str:
    out: list[str] = [f"# {m.app_id}", "", f"Generated from spirit-map `{m.app_id}`. "
                      "Screen text is untrusted data from a legacy system.", ""]
    out += ["## Flow", "", "```mermaid", "flowchart TD"]
    for n in sorted(m.nodes, key=lambda n: n.id):
        out.append(f'    {n.id}["{clean_text(_name(labels, n.id))}"]')
    for e in sorted(m.edges, key=lambda e: e.id):
        el = labels.edge(e.id)
        lab = clean_text(el.meaning) if el and el.meaning else e.key
        out.append(f'    {e.from_} -->|"{e.key}"| {e.to}')
    out += ["```", ""]

    out += ["## Screens", ""]
    for n in sorted(m.nodes, key=lambda n: n.id):
        nl = labels.node(n.id)
        kind = nl.kind if nl else "other"
        review = "  _(needs review)_" if nl and nl.needs_review else ""
        out.append(f"### {_name(labels, n.id)} (`{kind}`, {n.id}){review}")
        if nl and nl.purpose:
            out.append(f"\n{clean_text(nl.purpose)}\n")
        out.append("| field | business name | role | input |")
        out.append("|---|---|---|---|")
        for f in n.fields:
            fl = labels.field(n.id, f.key)
            bn = clean_text(fl.business_name) if fl else f.key
            role = fl.role if fl else "other"
            kind_in = "output" if f.output else ("input" if not f.protected else "text")
            out.append(f"| `{f.key}` | {bn} | {role} | {kind_in} |")
        out.append("")

    out += ["## Tools", ""]
    for t in pack["tools"]:
        draft = " _(draft)_" if t.get("provenance", {}).get("needs_review") else ""
        out.append(f"- **{t['name']}** (`{t['kind']}`){draft}: {clean_text(t['description'])}")
    out.append("")

    out += ["## Frontier (not explored or denied)", ""]
    if not m.frontier:
        out.append("None: every allowed edge was followed.")
    for fr in sorted(m.frontier, key=lambda f: (f.from_, f.key)):
        out.append(f"- `{fr.from_}` {fr.key}: {_FRONTIER.get(fr.reason, fr.reason)}")
    out.append("")

    drafts = [t["name"] for t in pack["tools"] if t.get("provenance", {}).get("needs_review")]
    if drafts:
        out += ["## Open review items", "", "These tools are `draft` until a human approves them:",
                "", *[f"- {n}" for n in drafts], ""]
    return "\n".join(out) + "\n"
