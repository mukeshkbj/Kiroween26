"""Mutation checks for policy.py (task 2.4): break one rule at a time and require
the invariants to fail. A mutant that survives means a rule is not really tested."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from seance_spirit import policy

from .policy_invariants import check

SRC = Path(policy.__file__).read_text(encoding="utf-8")

MUTANTS = {
    "drop global key deny": (
        '        if k in d.keys:\n            return Deny("denied_key")\n', ""),
    "drop screen deny": (
        '        if sid in d.nodes or nid in d.nodes:\n            return Deny("denied_screen")\n', ""),
    "drop per-screen key deny": (
        '        if any(k in d.screen_keys.get(ref, ()) for ref in (sid, nid)):\n            return Deny("denied_key")\n', ""),
    "text hint no longer denies": (
        '        if k in self._hints.get(screen_id, frozenset()):\n            return Deny("denied_key")\n', ""),
    "text hint relaxes (allows what it names)": (
        '        if k in self._hints.get(screen_id, frozenset()):\n            return Deny("denied_key")\n',
        '        if k in self._hints.get(screen_id, frozenset()):\n            return Allow("declared")\n'),
    "allow before deny": (
        "        d = self.seed.deny\n",
        "        d = self.seed.deny\n"
        "        if any(k in self.seed.declared_read_only.get(ref, ()) for ref in (sid, nid)):\n"
        '            return Allow("declared")\n'),
    "commit check removed": (
        "        if not is_commit_capable(k):\n", "        if True:\n"),
    "declared keys apply on every screen": (
        'for ref in (sid, nid)):\n            return Allow("declared")',
        'for ref in self.seed.declared_read_only):\n            return Allow("declared")'),
    "approved policy ignores screen": (
        "        if k in self.approved.get(screen_id, frozenset()):\n",
        "        if any(k in v for v in self.approved.values()):\n"),
    "hints cleared on use": (
        "            self._hints[screen_id] = self._hints.get(screen_id, frozenset()) | found\n",
        "            self._hints[screen_id] = frozenset()\n"),
}


def build(src: str) -> types.ModuleType:
    mod = types.ModuleType("seance_spirit._mutant_policy")
    mod.__package__ = "seance_spirit"
    sys.modules[mod.__name__] = mod  # dataclasses looks the module up by name
    exec(compile(src, "<mutant>", "exec"), mod.__dict__)  # noqa: S102 - test-only, our own source
    return mod


def test_unmutated_source_passes() -> None:
    check(build(SRC))


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_mutant_is_killed(name: str) -> None:
    old, new = MUTANTS[name]
    assert old in SRC, f"mutation {name!r} no longer matches policy.py; update the mutant"
    mutant = build(SRC.replace(old, new, 1))
    with pytest.raises(AssertionError):
        check(mutant)
