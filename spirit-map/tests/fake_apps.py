"""Random fake 3270 apps for the explorer's property tests (task 4.1).

Screens are built with the real parser (via seance_mcp.fake), so screen ids, hidden
fields and field layouts are genuine. Every screen has an ``item`` input, an optional
hidden ``secret`` field, a ``msg`` output line and a legend row. Transitions are random;
some are *mutating* (they set ``app.dirty``). The test model keeps its own record of
what a truthful human could declare and what the seed denies, independent of the
policy code under test.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hypothesis import strategies as st

from seance_bridge import Key
from seance_mcp.fake import F, FakeApp, Rule, build_screen, region_positions
from seance_spirit.ids import COMMIT_CAPABLE_NAMES, node_id
from seance_spirit.seed import ExploreSeed, parse_seed

VOLATILE = [(22, 1, 70)]
UNIVERSE = ["ENTER", "PF1", "PF2", "PF3", "PF5", "PF9", "PF12", "CLEAR", "PA1", "PF13"]
DANGEROUS = ["ENTER", "PF1", "PF3", "PF5", "PF9"]
SECRET_CELLS = range(5 * 80 + 15, 5 * 80 + 23)


@dataclass(frozen=True)
class Trans:
    to: int
    mutating: bool
    guarded: bool


@dataclass(frozen=True)
class ScreenDef:
    has_secret: bool
    danger: frozenset[str]            # keys whose on-screen legend says DELETE
    trans: tuple[tuple[str, Trans], ...]


class RecordingApp(FakeApp):
    """A FakeApp that records (screen name, key) for every key it receives."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.received: list[tuple[str, str]] = []

    async def press(self, key: Key):
        self.received.append((self.current, key.name))
        return await super().press(key)


@dataclass(frozen=True)
class Case:
    screens: tuple[ScreenDef, ...]
    connected: bool
    declared: frozenset[tuple[int, str]]
    deny_keys: frozenset[str]
    deny_screens: frozenset[int]
    deny_screen_keys: frozenset[tuple[int, str]]

    # -- the app -----------------------------------------------------------------

    def build(self) -> RecordingApp:
        vol = region_positions(VOLATILE)
        screens, rules = {}, []
        for k, sd in enumerate(self.screens):
            fields = [F("item", 3, 12, 4, "in"), F("msg", 22, 1, 70)]
            texts = {(0, 1): f"SCREEN {k} TITLE", (3, 1): "ITEM ===>", (23, 1): self._legend(sd)}
            if sd.has_secret:
                fields.append(F("secret", 5, 15, 8, "hidden"))
                texts[(5, 1)] = "PASSWORD ===>"
            screens[f"s{k}"] = build_screen(texts, fields, cursor_field="item", volatile=vol)
            for key, t in sd.trans:
                rules.append(Rule(f"s{k}", key, f"s{t.to}", mutating=t.mutating,
                                  when=(lambda v: v.get("item", "").strip() == "1") if t.guarded else None))
        return RecordingApp(screens, "s0", rules)

    @staticmethod
    def _legend(sd: ScreenDef) -> str:
        parts = [f"{k}=DELETE" for k in sorted(sd.danger)] + ["PF4=BACK"]
        return "  ".join(parts)

    def screen_ids(self) -> list[str]:
        app = self.build()
        return [app.screens[f"s{k}"].model().screen_id for k in range(len(self.screens))]

    # -- the human's seed -----------------------------------------------------------

    def seed(self, **budgets) -> ExploreSeed:
        ids = self.screen_ids()
        declared: dict[str, list[str]] = {}
        for k, key in sorted(self.declared):
            declared.setdefault(node_id(ids[k]), []).append(key)
        screen_keys: dict[str, list[str]] = {}
        for k, key in sorted(self.deny_screen_keys):
            screen_keys.setdefault(node_id(ids[k]), []).append(key)
        return parse_seed({
            "app_id": "fake",
            "probes": [{"field_label": "^ITEM", "name": "one", "value": "1"}],
            "declared_read_only": declared,
            "deny": {"keys": sorted(self.deny_keys), "nodes": [node_id(ids[k]) for k in sorted(self.deny_screens)],
                     "screen_keys": screen_keys, "field_label_patterns": []},
            "budgets": {"max_steps": 2000, "max_screens": 50, "max_depth": 20, "fanout": 50, **budgets},
            "volatile": [list(v) for v in VOLATILE],
        })

    # -- the test's own model of what may be pressed ----------------------------------

    def allowed(self, screen: int, key: str) -> bool:
        if key in self.deny_keys or screen in self.deny_screens or (screen, key) in self.deny_screen_keys:
            return False
        if key in self.screens[screen].danger:
            return False  # a legend that says DELETE can only add a deny
        if (screen, key) in self.declared:
            return True
        return key not in COMMIT_CAPABLE_NAMES

    def reachable(self) -> set[int]:
        """Screens reachable from 0 by pressing only allowed keys (ENTER carries item=1)."""
        seen, todo = {0}, [0]
        while todo:
            k = todo.pop()
            for key, t in self.screens[k].trans:
                if self.allowed(k, key) and t.to not in seen:
                    seen.add(t.to)
                    todo.append(t.to)
        return seen


@st.composite
def cases(draw, *, connected: bool | None = None, denies: bool = True, secrets: bool = True) -> Case:
    n = draw(st.integers(2, 6))
    conn = draw(st.booleans()) if connected is None else connected
    all_enter_mutates = draw(st.booleans())
    defs: list[ScreenDef] = []
    declared: set[tuple[int, str]] = set()
    present: list[tuple[int, str]] = []   # (screen, key) pairs that have a transition
    targets: set[int] = set()
    for k in range(n):
        keys = draw(st.lists(st.sampled_from(UNIVERSE), unique=True, max_size=6))
        trans: dict[str, Trans] = {}
        for key in keys:
            commit = key in COMMIT_CAPABLE_NAMES
            safe = draw(st.booleans())  # would a truthful human declare this one read-only?
            mutating = commit and (not safe or (all_enter_mutates and key == "ENTER"))
            trans[key] = Trans(draw(st.integers(0, n - 1)), mutating, key == "ENTER" and draw(st.booleans()))
        if conn:
            trans["CLEAR"] = Trans(0, False, False)  # CLEAR goes home, as on a real 3270
        for key in sorted(COMMIT_CAPABLE_NAMES):
            t = trans.get(key)
            if (t is None or not t.mutating) and draw(st.booleans()):
                declared.add((k, key))  # only never-mutating keys are ever declared
        # a legend that says DELETE: drawn from keys that matter here (declared or with a transition)
        pool = sorted({key for key in DANGEROUS if key in trans or (k, key) in declared})
        danger = frozenset(draw(st.lists(st.sampled_from(pool), unique=True, max_size=2))) if pool else frozenset()
        defs.append(ScreenDef(secrets and draw(st.booleans()), danger, tuple(sorted(trans.items()))))
        present += [(k, key) for key in trans]
        targets |= {t.to for t in trans.values()}
    deny_keys: frozenset[str] = frozenset()
    deny_screens: frozenset[int] = frozenset()
    deny_screen_keys: frozenset[tuple[int, str]] = frozenset()
    if denies:
        # drawn from things that exist, so a broken deny rule has something to get wrong
        keys_present = sorted({key for _, key in present})
        if keys_present:
            deny_keys = frozenset(draw(st.lists(st.sampled_from(keys_present), unique=True, max_size=2)))
            deny_screen_keys = frozenset(draw(st.lists(st.sampled_from(sorted(present)), unique=True, max_size=2)))
        movable = sorted(targets - {0})
        if movable:
            deny_screens = frozenset(draw(st.lists(st.sampled_from(movable), unique=True, max_size=1)))
    return Case(tuple(defs), conn, frozenset(declared), deny_keys, deny_screens, deny_screen_keys)