"""Amazon Bedrock provider using the Converse API with tool use (REQ-009).

Credentials come from the standard AWS chain; only the region is configured here.
``converse_stream`` is a blocking boto3 call, so each pull from the event stream
runs in a worker thread. Conversion functions are pure for recorded-payload tests.
Errors are mapped from the exception class / AWS error code only.
"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import anyio

from ..config import Settings
from .base import LlmError, LlmEvent, Message, Stop, TextDelta, ToolDef, ToolUse, Usage

log = logging.getLogger("seance_agent.llm.bedrock")
_END = object()


def to_converse_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    def flush() -> None:
        if results:
            out.append({"role": "user", "content": list(results)})
            results.clear()

    for m in messages:
        role = m["role"]
        if role == "tool":
            results.append({"toolResult": {"toolUseId": m["tool_use_id"], "content": [{"text": m["content"]}]}})
            continue
        flush()
        if role == "user":
            out.append({"role": "user", "content": [{"text": m["text"]}]})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.get("text"):  # Bedrock rejects empty text blocks
                blocks.append({"text": m["text"]})
            for u in m.get("tool_uses", []):
                blocks.append({"toolUse": {"toolUseId": u["id"], "name": u["name"], "input": u["input"]}})
            if blocks:
                out.append({"role": "assistant", "content": blocks})
    flush()
    return out


def to_converse_tools(tools: list[ToolDef]) -> dict[str, Any]:
    return {"tools": [{"toolSpec": {"name": t.name, "description": t.description or t.name,
                                    "inputSchema": {"json": t.input_schema}}} for t in tools]}


def map_error(exc: Exception) -> LlmError:
    code = ""
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        code = str(resp.get("Error", {}).get("Code", ""))
    name = type(exc).__name__
    if code in {"AccessDeniedException", "UnrecognizedClientException", "ExpiredTokenException"} or name in {
            "NoCredentialsError", "PartialCredentialsError", "EndpointConnectionError", "ConnectTimeoutError"}:
        return LlmError("llm_unavailable", "The language model is not reachable with the configured AWS access.")
    return LlmError("llm_error", f"The language model request failed{f' ({code})' if code else ''}.")


class BedrockProvider:
    name = "bedrock"

    def __init__(self, settings: Settings, *, client: Any | None = None):
        self.model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens
        if client is not None:
            self._client = client
        else:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-runtime", region_name=settings.aws_region,
                config=Config(read_timeout=settings.llm_timeout_s, connect_timeout=10, retries={"max_attempts": 2}))

    def __repr__(self) -> str:
        return f"BedrockProvider(model={self.model!r})"

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await anyio.to_thread.run_sync(close)

    async def stream(self, messages: list[Message], tools: list[ToolDef], system: str) -> AsyncIterator[LlmEvent]:
        kwargs: dict[str, Any] = {
            "modelId": self.model, "messages": to_converse_messages(messages),
            "system": [{"text": system}], "inferenceConfig": {"maxTokens": self._max_tokens},
        }
        if tools:
            kwargs["toolConfig"] = to_converse_tools(tools)
        starts: dict[int, dict[str, Any]] = {}
        stop = "end_turn"
        usage: Usage | None = None
        try:
            resp = await anyio.to_thread.run_sync(lambda: self._client.converse_stream(**kwargs))
            it = iter(resp["stream"])
            while True:
                nxt = await anyio.to_thread.run_sync(next, it, _END)
                if nxt is _END:
                    break
                event: dict[str, Any] = nxt  # type: ignore[assignment]
                if "contentBlockStart" in event:
                    e = event["contentBlockStart"]
                    tu = e.get("start", {}).get("toolUse")
                    if tu:
                        starts[e["contentBlockIndex"]] = {"id": tu["toolUseId"], "name": tu["name"], "json": ""}
                elif "contentBlockDelta" in event:
                    e = event["contentBlockDelta"]
                    d = e.get("delta", {})
                    if "text" in d:
                        yield TextDelta(d["text"])
                    elif "toolUse" in d and e["contentBlockIndex"] in starts:
                        starts[e["contentBlockIndex"]]["json"] += d["toolUse"].get("input", "")
                elif "messageStop" in event:
                    stop = str(event["messageStop"].get("stopReason", stop))
                elif "metadata" in event:
                    u = event["metadata"].get("usage", {})
                    usage = Usage(int(u.get("inputTokens", 0)), int(u.get("outputTokens", 0)))
        except LlmError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped without echoing its text
            log.warning("bedrock call failed: %s", type(exc).__name__)
            raise map_error(exc) from None
        for idx in sorted(starts):
            s = starts[idx]
            try:
                args = json.loads(s["json"]) if s["json"] else {}
            except ValueError:
                raise LlmError("llm_error", "The language model returned malformed tool input.") from None
            yield ToolUse(s["id"], s["name"], args if isinstance(args, dict) else {})
        if usage:
            yield usage
        yield Stop(stop)
