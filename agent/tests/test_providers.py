"""Section 7: provider adapters against recorded-shape payloads (no network, no keys).

* message/tool conversion is exact (tool results grouped, empty text dropped);
* streamed events map to LlmEvents;
* a credential never appears in a repr, an LlmError message, or a log line, even
  when the SDK exception text contains it;
* an unreachable model is an ``llm_unavailable`` error event, not a crash (7.4).
"""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace as NS

import anthropic
import pytest

from seance_agent.config import Settings
from seance_agent.llm import anthropic_provider as ap
from seance_agent.llm import bedrock_provider as bp
from seance_agent.llm.base import LlmError, Stop, TextDelta, ToolDef, ToolUse, Usage

from ._harness import agent_harness, assert_stream_ok, events, make_loop

pytestmark = pytest.mark.anyio
SECRET = "sk-ant-SECRET-0123456789"
HISTORY = [
    {"role": "user", "text": "Look up P0000003 and P0000004"},
    {"role": "assistant", "text": "", "tool_uses": [
        {"id": "tu1", "name": "lookup_policy", "input": {"policy_number": "P0000003"}},
        {"id": "tu2", "name": "lookup_policy", "input": {"policy_number": "P0000004"}}]},
    {"role": "tool", "tool_use_id": "tu1", "content": '{"trust":"untrusted-screen-data","result":1}'},
    {"role": "tool", "tool_use_id": "tu2", "content": '{"trust":"untrusted-screen-data","result":2}'},
]
TOOLS = [ToolDef("lookup_policy", "Find a policy", {"type": "object", "properties": {}})]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------- anthropic


def test_anthropic_conversion() -> None:
    msgs = ap.to_anthropic_messages(HISTORY)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert [b["type"] for b in msgs[1]["content"]] == ["tool_use", "tool_use"]  # empty text dropped
    assert [b["tool_use_id"] for b in msgs[2]["content"]] == ["tu1", "tu2"]       # one user turn, in order
    assert ap.to_anthropic_tools(TOOLS) == [{"name": "lookup_policy", "description": "Find a policy",
                                             "input_schema": {"type": "object", "properties": {}}}]


class _Stream:
    def __init__(self, events, final):
        self._events, self._final = events, final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            for e in self._events:
                yield e
        return gen()

    async def get_final_message(self):
        return self._final


class _FakeAnthropic:
    def __init__(self, stream=None, boom=None):
        self.calls, self._stream, self._boom = [], stream, boom
        self.messages = NS(stream=self._open)

    def _open(self, **kw):
        self.calls.append(kw)
        if self._boom:
            raise self._boom
        return self._stream


def _settings(**kw) -> Settings:
    return Settings.from_env({"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": SECRET, "LLM_MODEL": "m", **kw})


async def _collect(provider, messages=HISTORY):
    return [e async for e in provider.stream(messages, TOOLS, "SYS")]


async def test_anthropic_stream_maps_events() -> None:
    final = NS(content=[NS(type="text", text="hi"), NS(type="tool_use", id="tu9", name="lookup_policy",
                                                       input={"policy_number": "P0000001"})],
               usage=NS(input_tokens=12, output_tokens=5), stop_reason="tool_use")
    fake = _FakeAnthropic(_Stream([NS(type="message_start"), NS(type="text", text="Hel"), NS(type="text", text="lo")], final))
    out = await _collect(ap.AnthropicProvider(_settings(), client=fake))
    assert out == [TextDelta("Hel"), TextDelta("lo"), ToolUse("tu9", "lookup_policy", {"policy_number": "P0000001"}),
                   Usage(12, 5), Stop("tool_use")]
    sent = fake.calls[0]
    assert sent["system"] == "SYS" and sent["model"] == "m" and sent["max_tokens"] == 1024


class _AuthBoom(anthropic.AuthenticationError):
    def __init__(self) -> None:  # the SDK text can echo request details, including a key
        Exception.__init__(self, f"401 invalid x-api-key {SECRET}")


class _ConnBoom(anthropic.APIConnectionError):
    def __init__(self) -> None:
        Exception.__init__(self, f"connect failed for {SECRET}")


@pytest.mark.parametrize("boom,code", [(_AuthBoom(), "llm_unavailable"), (_ConnBoom(), "llm_unavailable"),
                                       (RuntimeError(f"weird {SECRET}"), "llm_error")])
async def test_anthropic_errors_are_mapped_without_leaking_the_key(boom, code, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    provider = ap.AnthropicProvider(_settings(), client=_FakeAnthropic(boom=boom))
    with pytest.raises(LlmError) as exc:
        await _collect(provider)
    assert exc.value.code == code
    assert SECRET not in exc.value.message and SECRET not in str(exc.value)
    assert SECRET not in caplog.text and SECRET not in repr(provider)


def test_real_constructor_does_not_expose_the_key() -> None:
    p = ap.AnthropicProvider(_settings())
    assert SECRET not in repr(p) and SECRET not in repr(_settings())


# ---------------------------------------------------------------- bedrock


def test_bedrock_conversion() -> None:
    msgs = bp.to_converse_messages(HISTORY)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert all("toolUse" in b for b in msgs[1]["content"])
    assert [b["toolResult"]["toolUseId"] for b in msgs[2]["content"]] == ["tu1", "tu2"]
    spec = bp.to_converse_tools(TOOLS)["tools"][0]["toolSpec"]
    assert spec["name"] == "lookup_policy" and spec["inputSchema"] == {"json": {"type": "object", "properties": {}}}


class _FakeBedrock:
    def __init__(self, events=(), boom=None):
        self.calls, self._events, self._boom = [], list(events), boom

    def converse_stream(self, **kw):
        self.calls.append(kw)
        if self._boom:
            raise self._boom
        return {"stream": iter(self._events)}


BEDROCK_EVENTS = [
    {"messageStart": {"role": "assistant"}},
    {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Looking"}}},
    {"contentBlockStart": {"contentBlockIndex": 1, "start": {"toolUse": {"toolUseId": "tu7", "name": "lookup_policy"}}}},
    {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": '{"policy_numb'}}}},
    {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": 'er": "P0000002"}'}}}},
    {"messageStop": {"stopReason": "tool_use"}},
    {"metadata": {"usage": {"inputTokens": 20, "outputTokens": 9}}},
]


def _bsettings() -> Settings:
    return Settings.from_env({"LLM_PROVIDER": "bedrock", "AWS_REGION": "us-east-1", "LLM_MODEL": "model-id"})


async def test_bedrock_stream_maps_events() -> None:
    fake = _FakeBedrock(BEDROCK_EVENTS)
    out = await _collect(bp.BedrockProvider(_bsettings(), client=fake))
    assert out == [TextDelta("Looking"), ToolUse("tu7", "lookup_policy", {"policy_number": "P0000002"}),
                   Usage(20, 9), Stop("tool_use")]
    k = fake.calls[0]
    assert k["modelId"] == "model-id" and k["system"] == [{"text": "SYS"}]


async def test_bedrock_malformed_tool_input_is_an_error() -> None:
    bad = BEDROCK_EVENTS[:3] + [{"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": "{oops"}}}}]
    with pytest.raises(LlmError) as exc:
        await _collect(bp.BedrockProvider(_bsettings(), client=_FakeBedrock(bad)))
    assert exc.value.code == "llm_error"


class _Denied(Exception):
    response = {"Error": {"Code": "AccessDeniedException"}}


async def test_bedrock_access_denied_is_unavailable() -> None:
    with pytest.raises(LlmError) as exc:
        await _collect(bp.BedrockProvider(_bsettings(), client=_FakeBedrock(boom=_Denied(f"nope {SECRET}"))))
    assert exc.value.code == "llm_unavailable" and SECRET not in exc.value.message


# ---------------------------------------------------------------- llm_unavailable path (7.4)


class _Broken:
    name, model = "anthropic", "m"

    def __init__(self, code: str):
        self.code = code

    async def stream(self, messages, tools, system):
        raise LlmError(self.code, "The language model could not be reached.")
        yield  # pragma: no cover


@pytest.mark.parametrize("code", ["llm_unavailable", "llm_error"])
async def test_provider_failure_is_an_event_and_a_clean_turn_end(code) -> None:
    async with agent_harness(real_pack=True) as h:
        await h.service.connect()
        loop = make_loop(h, _Broken(code))
        assert await loop.run_turn("Look up P0000003") == "error"
        assert_stream_ok(h)
        err = events(h, "error")[0]["data"]
        assert err["code"] == code and err["recoverable"] is True
        assert events(h, "turn_finished")[-1]["data"]["reason"] == "error"
        assert not h.app.pressed  # nothing was sent to the system
