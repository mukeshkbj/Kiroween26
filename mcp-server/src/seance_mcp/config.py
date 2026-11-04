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


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str = "localhost"
    port: int = 3270
    wait_timeout_ms: int = 5000
    allow_commit: bool = False
    confirm_mode: ConfirmMode = ConfirmMode.ELICIT
    pending_ttl_s: float = 300.0
    audit_log_path: Path = Path("docs/audit/audit.jsonl")
    key_policy_path: Path | None = None

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
        data: dict[str, object] = {"allow_commit": allow == "1"}
        for key, field in (
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
        return cls.model_validate(data)
