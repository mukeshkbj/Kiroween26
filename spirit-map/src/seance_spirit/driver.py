"""Policy-gated access to the session, shared by the explorer and replay.

Every key goes through ``EffectivePolicy.may_press`` first; every fill refuses
hidden, protected, credential-labelled and seed-denied fields. The service
underneath is built with ``allow_commit=False`` and never confirms anything, so
this is the second of several independent layers (see design.md "Safety layers").
There are no retries: a failed or ambiguous press ends the run.
"""
from __future__ import annotations

import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from seance_bridge import COMMIT_CAPABLE, Key
from seance_mcp.audit import AuditLog
from seance_mcp.config import ConfirmMode, Settings
from seance_mcp.port import BridgePort
from seance_mcp.safety import GateError, KeyPolicy, SafetyGate
from seance_mcp.screens import ScreenOut
from seance_mcp.service import SeanceService

from .graph import Edge, Node, SpiritMap
from .ids import key_name, looks_credential
from .policy import EffectivePolicy
from .seed import ExploreSeed


class Halt(Exception):
    """The run must stop now. ``reason`` is recorded in the map (``ambiguous_ack``,
    ``session_lost``, ``lost``, ``unexpected_pending``, ``not_connected`` ...)."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason


class BudgetExhausted(Exception):
    """A budget (steps or time) ran out. A normal end of a run."""


class PolicyDenied(Exception):
    """The policy refused this key or field; nothing was sent."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class FieldRejected(Exception):
    """The application refused a typed value (length, numeric). Not fatal."""


class RouteMismatch(Exception):
    """A recorded route did not land where recorded."""

    def __init__(self, edge: Edge, landed: ScreenOut):
        super().__init__(f"edge {edge.id} landed on {landed.screen_id[:10]}")
        self.edge = edge
        self.landed = landed


class ExplorerKeyPolicy(KeyPolicy):
    """The exploration service's gate policy: a commit-capable key is sent only when a human
    declared or approved it for this screen (read straight from the data, not through
    ``may_press``); anything else stays a proposal that nobody will ever confirm. Deny rules
    are enforced by the driver in front of this, so a bug in either is caught by the other."""

    def __init__(self, policy: EffectivePolicy):
        super().__init__()
        self._effective = policy

    def may_commit(self, key: Key, screen_id: str | None) -> bool:
        if key not in COMMIT_CAPABLE:
            return False
        if screen_id is None:
            return True
        return key.name not in self._effective.declared_keys(screen_id)


def build_driver(
    port: BridgePort,
    seed: ExploreSeed,
    *,
    approved: Mapping[str, frozenset[str]] | None = None,
    audit_path: Path | None = None,
    host: str = "localhost",
    tn_port: int = 3270,
    clock: Callable[[], float] = time.monotonic,
    policy_factory: Callable[..., EffectivePolicy] = EffectivePolicy,
) -> "Driver":
    """A driver over a service that can never commit: ``allow_commit=False``, a gate whose
    read-only keys come from the effective policy, and no confirmer anywhere."""
    audit = audit_path or Path(tempfile.mkdtemp(prefix="spirit-explore-")) / "audit.jsonl"
    settings = Settings(allow_commit=False, confirm_mode=ConfirmMode.OOB, audit_log_path=audit,
                        host=host, port=tn_port)
    policy = policy_factory(seed, dict(approved or {}))
    gate = SafetyGate(allow_commit=False, ttl_s=settings.pending_ttl_s, policy=ExplorerKeyPolicy(policy))
    service = SeanceService(settings, port, AuditLog(audit), gate)
    b = seed.budgets
    return Driver(service, policy, seed, max_steps=b.max_steps, max_seconds=b.max_seconds, clock=clock)


@dataclass
class Driver:
    service: SeanceService
    policy: EffectivePolicy
    seed: ExploreSeed
    max_steps: int
    max_seconds: float
    clock: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        self.steps = 0
        self.t0 = self.clock()
        self.screen: ScreenOut | None = None
        # Own bookkeeping, written *before* each send: (screen_id, key name).
        self.keys_sent: list[tuple[str, str]] = []

    # -- budget ---------------------------------------------------------------------

    def _spend(self) -> None:
        if self.steps >= self.max_steps or self.clock() - self.t0 >= self.max_seconds:
            raise BudgetExhausted()
        self.steps += 1

    # -- operations -----------------------------------------------------------------

    def _map_error(self, exc: GateError) -> Halt | FieldRejected:
        if exc.code == "field_invalid":
            return FieldRejected(exc.message)
        if exc.code in ("keyboard_timeout", "needs_resync"):
            return Halt("ambiguous_ack", exc.message)
        return Halt(exc.code, exc.message)

    async def connect(self, host: str, port: int) -> ScreenOut:
        try:
            self.screen = await self.service.connect(host, port)
        except GateError as exc:
            raise Halt(exc.code, exc.message) from None
        return self.screen

    async def read(self) -> ScreenOut:
        try:
            self.screen = await self.service.read_screen()
        except GateError as exc:
            raise Halt(exc.code, exc.message) from None
        return self.screen

    async def press(self, key: str) -> ScreenOut:
        screen = self.screen
        if screen is None:
            raise Halt("not_connected", "no screen has been read")
        k = key_name(key)
        self.policy.learn_hints(screen.screen_id, screen.rows)  # text may only add denies
        decision = self.policy.may_press(k, screen.screen_id)
        if not decision.allowed:
            raise PolicyDenied(decision.reason)
        self._spend()
        self.keys_sent.append((screen.screen_id, k))
        try:
            out = await self.service.press_key(k)
        except GateError as exc:
            err = self._map_error(exc)
            raise err from None
        if out.status != "executed" or out.screen is None:
            # The gate held the key back. Never confirm: stop and report.
            raise Halt("unexpected_pending", f"{k} was held by the gate on {screen.screen_id[:10]}")
        self.screen = out.screen
        return out.screen

    def check_fillable(self, index: int) -> None:
        """Raise ``PolicyDenied('unsafe_field')`` unless this field may be typed into."""
        screen = self.screen
        f = next((x for x in (screen.fields if screen else ()) if x.index == index), None)
        if f is None or f.protected or f.hidden:
            raise PolicyDenied("unsafe_field")
        if looks_credential(f.label) or self.seed.label_denied(f.label):
            raise PolicyDenied("unsafe_field")

    async def fill(self, index: int, value: str) -> ScreenOut:
        self.check_fillable(index)
        self._spend()
        try:
            self.screen = await self.service.fill_field(index, value)
        except GateError as exc:
            err = self._map_error(exc)
            raise err from None
        return self.screen

    # -- routes ---------------------------------------------------------------------

    def probe_value(self, name: str) -> str | None:
        return next((p.value for p in self.seed.probes if p.name == name), None)

    async def follow(self, m: SpiritMap, path: list[Edge]) -> ScreenOut:
        """Execute recorded edges, verifying ``screen_id`` before and after each step.
        Raises ``RouteMismatch`` on a wrong landing and ``Halt('lost')`` if we are not
        even where the route starts."""
        assert self.screen is not None
        for edge in path:
            src, dst = m.node(edge.from_), m.node(edge.to)
            if src is None or dst is None:
                raise Halt("lost", "route names an unknown node")
            if self.screen.screen_id != src.screen_id:
                raise Halt("lost", f"expected {src.id}, found {self.screen.screen_id[:10]}")
            await self.apply_fills(src, edge)
            landed = await self.press(edge.key)
            if landed.screen_id != dst.screen_id:
                raise RouteMismatch(edge, landed)
        return self.screen

    async def apply_fills(self, node: Node, edge: Edge) -> None:
        for fill in edge.fills:
            rec = node.field(fill.field)
            value = self.probe_value(fill.probe)
            if rec is None or value is None:
                raise Halt("lost", f"cannot replay fill of {fill.field!r} with probe {fill.probe!r}")
            await self.fill(rec.index, value)
