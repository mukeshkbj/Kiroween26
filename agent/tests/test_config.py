"""Task 1.3: configuration is strict where it must be and forgiving where it should be."""
from __future__ import annotations

import pytest

from seance_agent.config import LlmProviderName, Settings, llm_availability
from seance_agent.llm.factory import build_llm
from seance_agent.__main__ import load_dotenv


def test_defaults_are_the_safe_ones() -> None:
    s = Settings.from_env({})
    assert s.host == "127.0.0.1" and s.allow_commit is False and s.live_ok is False
    assert s.llm_provider is LlmProviderName.SCRIPTED and llm_availability(s)
    assert "http://localhost:5173" in s.allowed_origins


def test_unknown_provider_is_an_error_not_a_fallback() -> None:
    with pytest.raises(ValueError, match="unknown"):
        Settings.from_env({"LLM_PROVIDER": "openai"})


@pytest.mark.parametrize("env", [{"SEANCE_ALLOW_COMMIT": "yes"}, {"SEANCE_CONFIRM_MODE": "elicit"},
                                 {"AGENT_GENERIC_TOOLS": "maybe"}, {"AGENT_MAX_STEPS": "0"}])
def test_bad_values_are_errors(env) -> None:
    with pytest.raises(ValueError):
        Settings.from_env(env)


def test_missing_credentials_degrade_instead_of_crashing() -> None:
    s = Settings.from_env({"LLM_PROVIDER": "anthropic"})
    assert llm_availability(s) is False
    assert build_llm(s) == (None, False)
    b = Settings.from_env({"LLM_PROVIDER": "bedrock"})
    assert build_llm(b) == (None, False)


def test_no_secret_in_repr() -> None:
    s = Settings.from_env({"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-SECRET-VALUE"})
    assert llm_availability(s)
    assert "sk-SECRET-VALUE" not in repr(s) and "sk-SECRET-VALUE" not in str(s.model_dump())
    assert "sk-SECRET-VALUE" not in s.model_dump_json()


def test_dotenv_never_grants_live_access(tmp_path, monkeypatch) -> None:
    f = tmp_path / ".env"
    f.write_text("GSS_LIVE_OK=1\nAGENT_PORT=9999\n# comment\n", encoding="utf-8")
    monkeypatch.delenv("GSS_LIVE_OK", raising=False)
    monkeypatch.delenv("AGENT_PORT", raising=False)
    load_dotenv(f)
    import os

    assert "GSS_LIVE_OK" not in os.environ and os.environ["AGENT_PORT"] == "9999"
    monkeypatch.delenv("AGENT_PORT", raising=False)
