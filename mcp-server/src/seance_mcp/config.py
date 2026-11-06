"""Settings from the environment, with safe defaults.

Invalid values are errors, never a silent fallback: an unknown confirm mode must
not quietly become a weaker one.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator


class ConfirmMode(StrEnum):
    ELICIT = "elicit"
    OOB = "oob"
    CLIENT_APPROVAL = "client-approval"


Region = tuple[int, int, int]  # (row, col, length), 0-origin

# Also masked: the terminal id in row 0 ("CUU0C0" / "CUU0C1", cols 11-16), which differs per
# connection (found by Agent A, 2026-11-06), so the same screen has one screen_id.
# TK4- VTAM welcome screen: the Date and Time stamps (top right) are fixed at
# paint time, so two reads agree but every repaint differs. Masked by default so
# screen_id (and the safety gate's stale-screen check) stays stable.
TK4_CLOCK_REGIONS: tuple[Region, ...] = ((0, 11, 6), (0, 64, 16), (1, 64, 16))


def parse_regions(raw: str) -> tuple[Region, ...]:
    """Parse ``row,col,len;row,col,len``. ``none`` disables masking. Bad input is an error."""
    if raw.strip().lower() == "none":
        return ()
    out: list[Region] = []
    for part in raw.split(";"):
        if not part.strip():
            continue
        try:
            r, c, n = (int(x) for x in part.split(","))
        except ValueError:
            raise ValueError(f"VOLATILE_REGIONS: bad region {part!r}; want row,col,len") from None
        if r < 0 or c < 0 or n <= 0:
            raise ValueError(f"VOLATILE_REGIONS: out-of-range region {part!r}")
        out.append((r, c, n))
    return tuple(out)


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str = "localhost"
    port: int = 3270
    wait_timeout_ms: int = 5000
    app: str | None = None  # SEANCE_APP: a fake app name (e.g. "fake-insurance") for a no-container server; None = live bridge
    allow_commit: bool = False
    confirm_mode: ConfirmMode = ConfirmMode.ELICIT
    pending_ttl_s: float = 300.0
    audit_log_path: Path = Path("docs/audit/audit.jsonl")
    key_policy_path: Path | None = None
    volatile_regions: tuple[Region, ...] = TK4_CLOCK_REGIONS
    generated_tools_path: Path | None = None
    tool_approvals_path: Path | None = None  # default: tool-approvals.json next to the pack
    allow_unreviewed_tools: bool = False

    @field_validator("pending_ttl_s")
    @classmethod
    def _ttl_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("PENDING_TTL_S must be > 0")
        return v

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        e = os.environ if env is None else env

        def get(key: str) -> str | None:
            v = e.get(key)
            return v if v not in (None, "") else None

        allow = get("SEANCE_ALLOW_COMMIT") or "0"
        if allow not in ("0", "1"):
            raise ValueError("SEANCE_ALLOW_COMMIT must be 0 or 1")
        unreviewed = get("SEANCE_ALLOW_UNREVIEWED_TOOLS") or "0"
        if unreviewed not in ("0", "1"):
            raise ValueError("SEANCE_ALLOW_UNREVIEWED_TOOLS must be 0 or 1")
        data: dict[str, object] = {"allow_commit": allow == "1", "allow_unreviewed_tools": unreviewed == "1"}
        for key, field in (
            ("SEANCE_APP", "app"),
            ("GENERATED_TOOLS_PATH", "generated_tools_path"),
            ("TOOL_APPROVALS_PATH", "tool_approvals_path"),
            ("TN3270_HOST", "host"),
            ("TN3270_PORT", "port"),
            ("WAIT_TIMEOUT_MS", "wait_timeout_ms"),
            ("SEANCE_CONFIRM_MODE", "confirm_mode"),
            ("PENDING_TTL_S", "pending_ttl_s"),
            ("AUDIT_LOG_PATH", "audit_log_path"),
            ("KEY_POLICY_PATH", "key_policy_path"),
        ):
            v = get(key)
            if v is not None:
                data[field] = v
        regions = get("VOLATILE_REGIONS")
        if regions is not None:
            data["volatile_regions"] = parse_regions(regions)
        return cls.model_validate(data)
