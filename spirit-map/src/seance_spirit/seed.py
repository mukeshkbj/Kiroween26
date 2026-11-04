"""The human-authored exploration policy (``explore.seed.json``).

Everything the explorer is allowed to do beyond "press non-commit keys" is written
here by a person. Unknown keys are errors (a typo must not silently drop a deny).
A seed that would fill a credential field, or whose start recipe fills anything or
presses a commit-capable key, is rejected.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .ids import is_commit_capable, key_name, pattern_targets_credentials


def _key(v: str) -> str:
    return key_name(v)


KeyName = Annotated[str, AfterValidator(_key)]


class SeedError(ValueError):
    """The seed file is unusable."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Probe(_Strict):
    """A non-sensitive value the explorer may type into fields whose label matches."""

    field_label: str  # regex, matched case-insensitively against the field label
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: str = Field(max_length=80)

    @field_validator("field_label")
    @classmethod
    def _label_ok(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"bad regex: {exc}") from None
        if pattern_targets_credentials(v):
            raise ValueError("a probe may not target credential-like fields (password, pin, secret, token)")
        return v

    def matches(self, label: str) -> bool:
        return re.search(self.field_label, label or "", re.IGNORECASE) is not None


class Deny(_Strict):
    keys: list[KeyName] = []                       # never pressed anywhere
    nodes: list[str] = []                          # node ids or screen ids: never pressed on
    screen_keys: dict[str, list[KeyName]] = {}     # node/screen id -> keys denied there
    field_label_patterns: list[str] = []           # never filled

    @field_validator("field_label_patterns")
    @classmethod
    def _regexes(cls, v: list[str]) -> list[str]:
        for p in v:
            try:
                re.compile(p)
            except re.error as exc:
                raise ValueError(f"bad regex {p!r}: {exc}") from None
        return v


class Budgets(_Strict):
    max_screens: int = Field(default=50, ge=1, le=1000)
    max_steps: int = Field(default=300, ge=1, le=10000)
    max_depth: int = Field(default=8, ge=1, le=100)
    max_seconds: float = Field(default=600.0, gt=0)
    fanout: int = Field(default=6, ge=1, le=50)


class ExploreSeed(_Strict):
    app_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    probes: list[Probe] = []
    declared_read_only: dict[str, list[KeyName]] = {}   # node/screen id -> keys a human declares read-only
    deny: Deny = Deny()
    budgets: Budgets = Budgets()
    harvest: bool = False
    # Keys to press first from wherever the session is. No fills; never commit-capable.
    start_recipe: list[KeyName] = []
    # Recommended volatile regions (row, col, len), recorded in the map for the generator.
    volatile: list[tuple[int, int, int]] = []

    @model_validator(mode="after")
    def _start_recipe_is_safe(self) -> "ExploreSeed":
        bad = [k for k in self.start_recipe if is_commit_capable(k)]
        if bad:
            raise ValueError(f"start_recipe may not press commit-capable keys: {bad}")
        return self

    def probe_for(self, label: str) -> Probe | None:
        return next((p for p in self.probes if p.matches(label)), None)

    def label_denied(self, label: str) -> bool:
        return any(re.search(p, label or "", re.IGNORECASE) for p in self.deny.field_label_patterns)


def parse_seed(raw: Any) -> ExploreSeed:
    try:
        return ExploreSeed.model_validate(raw)
    except ValueError as exc:  # pydantic.ValidationError is a ValueError
        raise SeedError(str(exc)) from None


def load_seed(path: Path) -> ExploreSeed:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SeedError(f"cannot read seed {path}: {type(exc).__name__}") from None
    return parse_seed(raw)
