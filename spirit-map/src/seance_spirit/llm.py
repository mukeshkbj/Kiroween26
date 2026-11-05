"""LLM client: a tiny protocol plus a scripted client, a prompt-hash cache, and optional
anthropic / bedrock adapters chosen by the shared env contract (docs/contracts.md section 9).

The client only ever *names* things. Its output is validated and sanitised by the labeller
and has no authority over safety (REQ-017). Nothing here ever logs a prompt or a key.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmClient(Protocol):
    name: str
    available: bool

    def complete(self, system: str, user: str) -> str:
        """Return the model's text for one (system, user) turn. Raises ``LlmError`` on failure."""
        ...


class LlmError(Exception):
    """A provider call failed. The labeller falls back to heuristic labels and records it."""


def prompt_hash(system: str, user: str, model: str) -> str:
    h = hashlib.sha256()
    for part in (model, system, user):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


class ScriptedLlm:
    """Deterministic client for tests and no-key demos. Answers by exact prompt hash, else
    a registered fallback, else raises. Records every prompt hash it was asked for."""

    name = "scripted"

    def __init__(self, answers: Mapping[str, str] | None = None, *, model: str = "scripted",
                 default: str | None = None, available: bool = True):
        self._answers = dict(answers or {})
        self._model = model
        self._default = default
        self.available = available
        self.asked: list[str] = []

    def set(self, system: str, user: str, answer: str) -> None:
        self._answers[prompt_hash(system, user, self._model)] = answer

    def complete(self, system: str, user: str) -> str:
        key = prompt_hash(system, user, self._model)
        self.asked.append(key)
        if key in self._answers:
            return self._answers[key]
        if self._default is not None:
            return self._default
        raise LlmError("ScriptedLlm has no answer for this prompt")


class Cache:
    """Prompt-hash cache so a labelled map is reproducible offline (REQ-015). Stores only the
    model's text keyed by hash; never the prompt."""

    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self._data: dict[str, str] = {}
        if self.path and self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._data = {k: str(v) for k, v in raw.get("responses", {}).items()}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, value: str) -> None:
        self._data[key] = value

    def save(self) -> None:
        if self.path is None:
            return
        from .store import write_json

        write_json(self.path, {"schema": "gss.labelcache/1", "responses": self._data})


class CachingLlm:
    """Wrap a client with a prompt-hash cache. A cache hit never calls the provider."""

    def __init__(self, inner: LlmClient, cache: Cache, model: str):
        self._inner = inner
        self._cache = cache
        self._model = model
        self.name = f"{inner.name}(cached)"

    @property
    def available(self) -> bool:
        return self._inner.available

    def complete(self, system: str, user: str) -> str:
        key = prompt_hash(system, user, self._model)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        out = self._inner.complete(system, user)
        self._cache.put(key, out)
        return out


# ---------------------------------------------------------------- provider adapters


class _Unavailable:
    """A known provider with no credentials: degrades to unavailable, never crashes (section 9)."""

    def __init__(self, name: str, reason: str):
        self.name = name
        self.available = False
        self._reason = reason

    def complete(self, system: str, user: str) -> str:
        raise LlmError(f"{self.name} unavailable: {self._reason}")


def _anthropic(model: str, env: Mapping[str, str]) -> LlmClient:
    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        return _Unavailable("anthropic", "ANTHROPIC_API_KEY not set")
    try:
        import anthropic  # type: ignore
    except ImportError:
        return _Unavailable("anthropic", "anthropic package not installed")

    max_tokens = int(env.get("LLM_MAX_TOKENS") or 2048)
    timeout = float(env.get("LLM_TIMEOUT_S") or 60)

    class _Anthropic:
        name = "anthropic"
        available = True

        def __init__(self) -> None:
            self._c = anthropic.Anthropic(api_key=key, timeout=timeout)

        def complete(self, system: str, user: str) -> str:
            try:
                msg = self._c.messages.create(
                    model=model, max_tokens=max_tokens, system=system,
                    messages=[{"role": "user", "content": user}])
                return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
            except Exception as exc:  # provider errors never leak the prompt
                raise LlmError(f"anthropic call failed: {type(exc).__name__}") from None

    return _Anthropic()


def _bedrock(model: str, env: Mapping[str, str]) -> LlmClient:
    region = env.get("AWS_REGION")
    if not region:
        return _Unavailable("bedrock", "AWS_REGION not set")
    try:
        import boto3  # type: ignore
    except ImportError:
        return _Unavailable("bedrock", "boto3 package not installed")

    max_tokens = int(env.get("LLM_MAX_TOKENS") or 2048)

    class _Bedrock:
        name = "bedrock"
        available = True

        def __init__(self) -> None:
            self._c = boto3.client("bedrock-runtime", region_name=region)

        def complete(self, system: str, user: str) -> str:
            try:
                resp = self._c.converse(
                    modelId=model, system=[{"text": system}],
                    messages=[{"role": "user", "content": [{"text": user}]}],
                    inferenceConfig={"maxTokens": max_tokens})
                return "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
            except Exception as exc:
                raise LlmError(f"bedrock call failed: {type(exc).__name__}") from None

    return _Bedrock()


def build_llm(env: Mapping[str, str] | None = None, *, cache_path: Path | None = None) -> LlmClient:
    """Pick a client from ``LLM_PROVIDER`` (section 9). ``heuristic`` returns an unavailable
    client (labelling then uses heuristics). An unknown provider is a startup error."""
    e = os.environ if env is None else env
    provider = (e.get("LLM_PROVIDER") or "heuristic").strip().lower()
    model = e.get("LLM_MODEL") or "unset"
    if provider == "heuristic":
        return _Unavailable("heuristic", "heuristic mode: no LLM")
    if provider == "scripted":
        return ScriptedLlm(model=model)
    if provider == "anthropic":
        inner: LlmClient = _anthropic(model, e)
    elif provider == "bedrock":
        inner = _bedrock(model, e)
    else:
        raise ValueError(f"unknown LLM_PROVIDER {provider!r}; want anthropic, bedrock, scripted or heuristic")
    if cache_path is not None:
        return CachingLlm(inner, Cache(cache_path), model)
    return inner
