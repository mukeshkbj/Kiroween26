"""Real-provider labelling test (task 5.5). Marked `llm`: skipped by default and whenever the
provider named by LLM_PROVIDER has no credentials. Run it with:

    $env:LLM_PROVIDER="anthropic"; $env:LLM_MODEL="..."; $env:ANTHROPIC_API_KEY="..."
    python -m pytest -m llm -s

It asserts what must hold for ANY model, not what a model says: labels are schema-valid, the
sentinel never reaches a prompt, and the key policy, tool kinds and recipe keys are the same as with
heuristic labels (the model names things; it never decides what is safe)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from seance_spirit.generator import Generator, Overrides
from seance_spirit.keypolicy import proposed_policy
from seance_spirit.labeller import Labeller
from seance_spirit.llm import build_llm
from seance_spirit.seed import load_seed
from seance_spirit.store import read_map

pytestmark = pytest.mark.llm

D = Path(__file__).resolve().parents[2] / "docs" / "spirit-map" / "fake-insurance"


def test_real_model_labels_change_names_not_safety() -> None:
    client = build_llm(os.environ)
    if not client.available:
        pytest.skip("no LLM provider configured (set LLM_PROVIDER and its credentials)")
    m = read_map(D / "spirit-map.json")
    seed = load_seed(D / "explore.seed.json")
    overrides = Overrides.load(json.loads((D / "overrides.json").read_text(encoding="utf-8")))

    real = Labeller(client, sentinels=["@@HIDDEN@@"]).label(m)
    heur = Labeller().label(m)
    assert real.source != "heuristic"
    for n in m.nodes:
        assert real.node(n.id) is not None and 0.0 <= real.node(n.id).confidence <= 1.0

    def shape(labels):
        pack = Generator(m, labels, seed, overrides).generate()
        policy, _ = proposed_policy(m, seed)
        return policy, {t["name"]: (t["kind"], [(s["op"], s.get("key")) for s in t["recipe"]]) for t in pack["tools"]}

    assert shape(real) == shape(heur)
    print(f"\nreal labels via {real.source}: " + ", ".join(
        f"{n.id}={real.node(n.id).name!r}({real.node(n.id).confidence:.2f})" for n in m.nodes))
