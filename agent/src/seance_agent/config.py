"""Agent settings from the environment, with safe defaults (design.md "Config").

Two rules the tests pin:

* An **unknown** ``LLM_PROVIDER`` is a startup error, never a silent fallback to a
  weaker provider (REQ-009, mirrors ``seance_mcp.config``).
* A **known** provider whose credentials are missing does not crash: it degrades
  to ``llm.available == false`` so a ``user_message`` can report ``llm_unavailable``
  cleanly (REQ-011). That check lives in ``llm_availability`` here; nothing in
  ``Settings`` validation reads a secret.

No secret is logged or placed in an event. ``ANTHROPIC_API_KEY`` is read only to
decide availability and to hand to the provider; it never appears in ``repr`` of
anything the UI or logs see.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator


class LlmProviderName(StrEnum):
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    SCRIPTED = "scripted"


class ConfirmMode(StrEnum):
    OOB = "oob"


def _origins(raw: str) -> tuple[str, ...]:
    return tuple(o.strip() for o in raw.split(",") if o.strip())


DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


class Settings(BaseModel):
    """Everything the agent needs to start. Frozen; built once at startup."""

    model_config = ConfigDict(frozen=True)

    # service / transport
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: tuple[str, ...] = _origins(DEFAULT_ORIGINS)
    max_steps: int = 12
    max_tool_errors: int = 3
    turn_timeout_s: float = 120.0
    generic_tools: bool = True
    event_log: Path | None = None
    ring_size: int = 1000

    # llm
    llm_provider: LlmProviderName = LlmProviderName.SCRIPTED
    llm_model: str = "scripted-demo"
    anthropic_api_key: SecretStr | None = None  # SecretStr: never shown in repr, logs or errors
    aws_region: str | None = None
    llm_max_tokens: int = 1024
    llm_timeout_s: float = 60.0

    # shared with mcp-server (passed straight through to build_service via from_env there)
    tn3270_host: str | None = None
    tn3270_port: int | None = None
    allow_commit: bool = False
    confirm_mode: ConfirmMode = ConfirmMode.OOB
    pending_ttl_s: float = 300.0
    audit_log_path: Path = Path("docs/audit/audit.jsonl")
    generated_tools_path: Path | None = None
    tool_approvals_path: Path | None = None
    key_policy_path: Path | None = None
    live_ok: bool = False

    @field_validator("turn_timeout_s", "pending_ttl_s", "llm_timeout_s")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("timeout/ttl must be > 0")
        return v

    @field_validator("max_steps", "max_tool_errors", "ring_size", "llm_max_tokens")
    @classmethod
    def _positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("count must be > 0")
        return v

    @property
    def is_live_default(self) -> bool:
        """True when the default connect target is a live host (needs GSS_LIVE_OK)."""
        return self.tn3270_host is not None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        e = os.environ if env is None else env

        def get(key: str) -> str | None:
            v = e.get(key)
            return v if v not in (None, "") else None

        def flag(key: str, default: str = "0") -> bool:
            v = (get(key) or default)
            if v not in ("0", "1"):
                raise ValueError(f"{key} must be 0 or 1")
            return v == "1"

        provider_raw = (get("LLM_PROVIDER") or "scripted").lower()
        try:
            provider = LlmProviderName(provider_raw)
        except ValueError:
            allowed = ", ".join(p.value for p in LlmProviderName)
            raise ValueError(f"LLM_PROVIDER={provider_raw!r} is unknown; use one of: {allowed}") from None

        confirm_raw = (get("SEANCE_CONFIRM_MODE") or "oob").lower()
        if confirm_raw != "oob":
            raise ValueError("SEANCE_CONFIRM_MODE must be 'oob' for the agent")

        generic_raw = (get("AGENT_GENERIC_TOOLS") or "on").lower()
        if generic_raw not in ("on", "off"):
            raise ValueError("AGENT_GENERIC_TOOLS must be 'on' or 'off'")

        data: dict[str, object] = {
            "llm_provider": provider,
            "generic_tools": generic_raw == "on",
            "allow_commit": flag("SEANCE_ALLOW_COMMIT"),
            "live_ok": flag("GSS_LIVE_OK"),
            "confirm_mode": ConfirmMode.OOB,
        }
        if (o := get("AGENT_ALLOWED_ORIGINS")) is not None:
            data["allowed_origins"] = _origins(o)
        for key, field, cast in (
            ("AGENT_HOST", "host", str),
            ("AGENT_PORT", "port", int),
            ("AGENT_MAX_STEPS", "max_steps", int),
            ("AGENT_MAX_TOOL_ERRORS", "max_tool_errors", int),
            ("AGENT_TURN_TIMEOUT_S", "turn_timeout_s", float),
            ("AGENT_EVENT_LOG", "event_log", Path),
            ("AGENT_RING_SIZE", "ring_size", int),
            ("LLM_MODEL", "llm_model", str),
            ("ANTHROPIC_API_KEY", "anthropic_api_key", str),
            ("AWS_REGION", "aws_region", str),
            ("LLM_MAX_TOKENS", "llm_max_tokens", int),
            ("LLM_TIMEOUT_S", "llm_timeout_s", float),
            ("TN3270_HOST", "tn3270_host", str),
            ("TN3270_PORT", "tn3270_port", int),
            ("PENDING_TTL_S", "pending_ttl_s", float),
            ("AUDIT_LOG_PATH", "audit_log_path", Path),
            ("GENERATED_TOOLS_PATH", "generated_tools_path", Path),
            ("TOOL_APPROVALS_PATH", "tool_approvals_path", Path),
            ("KEY_POLICY_PATH", "key_policy_path", Path),
        ):
            v = get(key)
            if v is not None:
                data[field] = cast(v)
        return cls.model_validate(data)


def llm_availability(settings: Settings) -> bool:
    """Whether the configured provider can actually be used right now.

    A missing credential is *not* a crash (REQ-011): it means ``available=false``,
    which the UI shows and which turns a ``user_message`` into an ``llm_unavailable``
    error. ``scripted`` is always available (no network, no key).
    """
    if settings.llm_provider is LlmProviderName.SCRIPTED:
        return True
    if settings.llm_provider is LlmProviderName.ANTHROPIC:
        return bool(settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value())
    if settings.llm_provider is LlmProviderName.BEDROCK:
        # boto3 resolves credentials from the standard chain at call time; a region
        # is the minimum we can check cheaply without reaching out to AWS.
        return bool(settings.aws_region)
    return False
