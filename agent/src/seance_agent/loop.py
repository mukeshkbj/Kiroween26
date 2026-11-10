"""AgentLoop: one user turn = model <-> tools, streamed to the UI (REQ-008, 012, 013, 019).

The loop is the only caller of the model and of the ToolBroker. What it does *not*
do is the point: it never confirms. When a call yields a pending action it hands
over to the ConfirmBroker and suspends; only the controller websocket resumes it.
The model is not shown the pending text (which names ``confirm_action``); after the
human decides it receives a short, agent-written notice (denied / expired /
read-only are final) or the confirmed screen.

Budgets: ``max_steps`` model calls, ``max_tool_errors`` failed tool calls, a turn
deadline (time spent waiting for a human does not count) and cancel, which takes
effect between steps and never interrupts a key already sent.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import anyio
from seance_mcp.audit import redact
from seance_mcp.safety import GateError

from . import prompts
from .confirm import ConfirmBroker, Resolution
from .events import (
    AssistantDeltaData,
    AssistantMessageData,
    ErrorData,
    ThinkingData,
    ToolCallData,
    ToolResultData,
    TurnFinishedData,
    TurnStartedData,
    Usage as UsageData,
)
from .llm.base import LlmError, LlmProvider, Message, Stop, TextDelta, ToolDef, ToolUse, Usage
from .mapper import CallScope, EventMapper
from .session import Session
from .tools import ToolBroker, ToolOutcome

RESULT_CAP = 8 * 1024
PUMP_INTERVAL_S = 0.02
GENERIC_NO_COMMIT = {"read_screen", "list_fields", "fill_field"}

# resolution outcome -> (error_code, what the PERSON sees, what the MODEL is told on top of it).
# The person's sentence is all the UI ever gets (finding D-5); instructions aimed at the model
# ("do not retry") stay in the tool result sent to the model.
_FINAL: dict[str, tuple[str, str, str]] = {
    "denied": ("denied_by_user", "You declined this change. Nothing was changed.",
               "This is final: do not retry or propose it again, and do not argue."),
    "expired": ("action_expired", "The confirmation timed out. Nothing was changed.",
                "Do not retry unless the person asks again."),
    "blocked_read_only": ("read_only", "The system is read-only, so nothing was changed.",
                          "This is final for this session."),
    "stale": ("stale_screen", "The screen changed before you confirmed, so nothing was sent.",
              "Read the screen before proposing anything else."),
    "superseded": ("unknown_action", "A newer request replaced this one. Nothing was changed.", ""),
    "error": ("bridge_error", "The change could not be completed. Nothing was confirmed.", ""),
}


def _model_notice(outcome: str) -> str:
    _, user, model = _FINAL.get(outcome, _FINAL["error"])
    return f"{user} {model}".strip()


class AgentLoop:
    def __init__(
        self,
        *,
        session: Session,
        broker: ToolBroker,
        confirm: ConfirmBroker,
        mapper: EventMapper,
        service: Any,
        llm: LlmProvider | None,
        llm_available: bool = True,
        max_steps: int = 12,
        max_tool_errors: int = 3,
        turn_timeout_s: float = 120.0,
        commit_hints: dict[str, bool] | None = None,
        on_error_code: Callable[[str], None] | None = None,
    ):
        self.session, self.broker, self.confirm, self.mapper = session, broker, confirm, mapper
        self.service, self.llm, self.llm_available = service, llm, llm_available
        self.max_steps, self.max_tool_errors, self.turn_timeout_s = max_steps, max_tool_errors, turn_timeout_s
        self.commit_hints = commit_hints or {}
        self.on_error_code = on_error_code
        self.history: list[Message] = []
        self.turn_id: str | None = None
        self._cancel = False
        self._waited = 0.0
        self._open_call: str | None = None

    # -- public -----------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self.turn_id is not None

    def current_turn_id(self) -> str | None:
        return self.turn_id

    def cancel(self) -> None:
        """Takes effect between steps; a key already sent is never interrupted."""
        self._cancel = True

    async def run_turn(self, text: str, *, ref: str | None = None) -> str:
        """Run one turn; returns the ``turn_finished`` reason (or ``"unavailable"``)."""
        if self.busy:
            self._error("turn_in_progress", "a turn is already running", True, ref)
            return "busy"
        if self.llm is None or not self.llm_available:
            self._error("llm_unavailable", "No language model is configured, so I cannot answer. "
                        "Check LLM_PROVIDER and its credentials.", True, ref)
            return "unavailable"
        self.turn_id = self.session.next_id("t")
        self._cancel = False
        self._open_call = None
        try:
            return await self._turn(text)
        except Exception:  # noqa: BLE001 - never leave a call or a turn dangling (stream rules)
            if self._open_call is not None:
                self.session.emit(ToolResultData(tool_call_id=self._open_call, status="error", error_code="bridge_error",
                                                 summary="internal error", result=None, truncated=False), turn_id=self.turn_id)
            pend = self.confirm.pending_action_id
            if pend is not None:
                await self.confirm.abandon(pend)
            self._error("bridge_error", "Internal error; this request was stopped.", True, None)
            self.session.emit(TurnFinishedData(reason="error", usage=None), turn_id=self.turn_id)
            return "error"
        finally:
            self.turn_id = None

    # -- the turn ---------------------------------------------------------

    async def _turn(self, text: str) -> str:
        emit = lambda d: self.session.emit(d, turn_id=self.turn_id)  # noqa: E731
        umid = self._mid()
        emit(TurnStartedData(user_message_id=umid))
        self.history.append({"role": "user", "text": text})
        usage_in = usage_out = 0
        seen_usage = False
        errors = 0
        proposed: set[str] = set()
        denied: set[str] = set()
        deadline = time.monotonic() + self.turn_timeout_s
        self._waited = 0.0
        defs = [ToolDef(s.name, s.description, s.input_schema) for s in self.broker.specs()]
        reason = "completed"
        assert self.llm is not None

        for _step in range(self.max_steps):
            if self._cancel:
                reason = "cancelled"
                break
            if time.monotonic() > deadline + self._waited:
                self._error("bridge_error", "The turn took too long and was stopped.", True, None)
                reason = "error"
                break
            mid = self._mid()
            parts: list[str] = []
            uses: list[ToolUse] = []
            try:
                async for ev in self.llm.stream(self.history, defs, prompts.SYSTEM_PROMPT):
                    if isinstance(ev, TextDelta):
                        parts.append(ev.text)
                        emit(AssistantDeltaData(message_id=mid, text=ev.text))
                    elif isinstance(ev, ToolUse):
                        uses.append(ev)
                    elif isinstance(ev, Usage):
                        seen_usage = True
                        usage_in += ev.input_tokens
                        usage_out += ev.output_tokens
                    elif isinstance(ev, Stop):
                        pass
            except LlmError as exc:
                self._error(exc.code, exc.message, True, None)
                reason = "error"
                break
            msg_text = "".join(parts)
            if msg_text:
                emit(AssistantMessageData(message_id=mid, text=msg_text))
            self.history.append({"role": "assistant", "text": msg_text,
                                 "tool_uses": [{"id": u.id, "name": u.name, "input": u.input} for u in uses]})
            if not uses:
                break
            emit(ThinkingData(summary=f"Using {uses[0].name.replace('_', ' ')}."[:300]))

            stop = False
            for i, use in enumerate(uses):
                if self._cancel or stop:
                    self.history.append({"role": "tool", "tool_use_id": use.id,
                                         "content": prompts.agent_notice(use.name, "Not run: the turn was stopped.")})
                    continue
                content, outcome_status, code = await self._run_tool(use, msg_text, proposed, denied)
                self.history.append({"role": "tool", "tool_use_id": use.id, "content": content})
                if outcome_status == "error" and code != "denied_by_user":
                    errors += 1
                    if errors >= self.max_tool_errors:
                        self._error("bridge_error", "Too many tool errors; stopping this turn.", True, None)
                        reason, stop = "error", True
            if reason == "error":
                break
        else:
            reason = "max_steps"
            self._error("max_steps", "I reached the step limit for one request.", True, None)

        if self._cancel and reason == "completed":
            reason = "cancelled"
        emit(TurnFinishedData(reason=reason,  # type: ignore[arg-type]
                              usage=UsageData(input_tokens=usage_in, output_tokens=usage_out) if seen_usage else None))
        return reason

    # -- one tool call ----------------------------------------------------

    async def _run_tool(self, use: ToolUse, agent_text: str, proposed: set[str],
                        denied: set[str]) -> tuple[str, str, str | None]:
        """Returns (content for the model, status, error_code)."""
        tcid = self._cid()
        kind = self.broker.kind_of(use.name) or "generic"
        key = use.name + json.dumps(use.input, sort_keys=True, default=str)
        self.session.emit(
            ToolCallData(tool_call_id=tcid, tool=use.name, kind=kind,  # type: ignore[arg-type]
                         arguments=self._redact_args(use.name, use.input), may_commit=self._may_commit(use.name, kind)),
            turn_id=self.turn_id)

        self._open_call = tcid

        def finish(status: str, code: str | None, summary: str, result: dict[str, Any] | None) -> None:
            self._open_call = None
            res, truncated = _cap(result)
            self.session.emit(ToolResultData(tool_call_id=tcid, status=status, error_code=code,  # type: ignore[arg-type]
                                             summary=summary[:500], result=res, truncated=truncated),
                              turn_id=self.turn_id)
            if code and self.on_error_code:
                self.on_error_code(code)

        # An open confirmation is resolved before anything else runs. The loop already blocks on
        # the human, so this only fires if some future path interleaves. Any other tool would
        # navigate away (PF3/CLEAR cancels the review screen) and leave the modal showing an action
        # the app had already dropped.
        if self.confirm.pending_action_id is not None:
            finish("error", "session_busy", "A change is waiting for your decision; decide on it first.", None)
            return (prompts.agent_notice(use.name, "A change is waiting for the person's decision. "
                                         "Nothing else runs until it is approved, denied or expires.",
                                         user="A change is waiting for your decision; decide on it first."),
                    "error", "session_busy")

        # A denied action is final within the turn; an action already proposed is not repeated (REQ-019).
        if key in denied:
            finish("error", "denied_by_user", "You already declined this change, so it was not proposed again.", None)
            return (prompts.agent_notice(use.name, _model_notice("denied"), user=_FINAL["denied"][1]),
                    "error", "denied_by_user")
        if key in proposed:
            finish("error", "invalid_arguments", "That action was already proposed this turn; not repeated.", None)
            return (prompts.agent_notice(use.name, "This exact action was already proposed in this turn and is not repeated."),
                    "error", "invalid_arguments")

        scope = CallScope(tool_call_id=tcid)
        before = self.service.gate.pending.action_id if self.service.gate.pending else None
        outcome = await self._call_with_pump(use, scope)

        gp = self.service.gate.pending
        is_pending = outcome.status == "pending" or (gp is not None and gp.action_id != before)
        if is_pending:
            proposed.add(key)
            if gp is None:
                finish("error", "unknown_action", "A pending action was reported but none exists.", None)
                return prompts.agent_notice(use.name, "Nothing was proposed."), "error", "unknown_action"
            return await self._await_human(use, tcid, key, agent_text, denied, finish, scope)

        if outcome.status == "error":
            extra = ""
            if outcome.error_code == "keyboard_timeout":
                extra = await self._fresh_read_after_timeout(scope)
            finish("error", outcome.error_code, outcome.summary, {"status": "error", "error": {
                "code": outcome.error_code, "message": outcome.summary}})
            return (prompts.wrap_tool_result(use.name, {"status": "error", "error": {
                "code": outcome.error_code, "message": outcome.summary}, "fresh_screen": extra or None}),
                    "error", outcome.error_code)

        finish("ok", None, outcome.summary, outcome.structured)
        return prompts.wrap_tool_result(use.name, outcome.structured), "ok", None

    async def _call_with_pump(self, use: ToolUse, scope: CallScope) -> ToolOutcome:
        """Call the tool while flushing service events live (REQ-013)."""
        box: dict[str, Any] = {}

        async def pump() -> None:
            while True:
                await anyio.sleep(PUMP_INTERVAL_S)
                self.mapper.flush(scope)

        async with anyio.create_task_group() as tg:
            tg.start_soon(pump)
            try:
                box["o"] = await self.broker.call(use.name, use.input)
            except Exception as exc:  # noqa: BLE001 - an MCP transport failure becomes an error outcome
                box["o"] = ToolOutcome(use.name, self.broker.kind_of(use.name) or "generic", "error",
                                       "bridge_error", None, f"tool call failed: {type(exc).__name__}")
            finally:
                tg.cancel_scope.cancel()
        self.mapper.flush(scope)
        return box["o"]

    async def _await_human(self, use: ToolUse, tcid: str, key: str, agent_text: str, denied: set[str],
                           finish: Callable[..., None], scope: CallScope) -> tuple[str, str, str | None]:
        gp = self.service.gate.pending
        assert gp is not None
        read_only = not self.service.gate.allow_commit
        summary = agent_text.strip()[:300] or None
        aid = self.confirm.register_pending(tool_call_id=tcid, turn_id=self.turn_id,
                                            read_only=read_only, agent_summary=summary, scope=scope)
        t0 = time.monotonic()
        remaining = max(0.0, gp.expires_at - self.service.gate.clock())
        res: Resolution | None = None
        async with anyio.create_task_group() as tg:
            async def waiter() -> None:
                nonlocal res
                res = await self.confirm.wait(aid)
                tg.cancel_scope.cancel()

            async def watcher() -> None:
                await anyio.sleep(remaining + 0.05)
                await self.confirm.expire(aid)

            async def canceller() -> None:
                while not self._cancel:
                    await anyio.sleep(0.05)
                await self.confirm.abandon(aid)

            tg.start_soon(waiter)
            tg.start_soon(watcher)
            tg.start_soon(canceller)
        self._waited += time.monotonic() - t0  # waiting for a human is not charged to the turn deadline
        assert res is not None
        if res.outcome == "approved":
            screen = self.mapper.last_screen
            result = {"status": "ok", "confirmed": True}
            finish("ok", None, "The change was confirmed by the person and sent.", result)
            body = dict(result, screen=screen.model_dump(mode="json") if screen is not None else None)
            return prompts.wrap_tool_result(use.name, body), "ok", None
        code, user_text, _ = _FINAL.get(res.outcome, _FINAL["error"])
        notice = _model_notice(res.outcome)
        code = res.error_code if res.outcome == "error" and res.error_code else code
        if res.outcome == "denied":
            denied.add(key)
        # The UI gets the person's sentence only; the model gets the full notice (D-5).
        finish("error", code, user_text, {"status": "error", "error": {"code": code, "message": user_text}})
        return prompts.agent_notice(use.name, notice, user=user_text), "error", code

    async def _fresh_read_after_timeout(self, scope: CallScope) -> str:
        """REQ-019: after keyboard_timeout never resend; force a read for fresh data."""
        try:
            s = await self.service.read_screen()
        except GateError:
            return ""
        self.mapper.flush(scope)
        return "The key may or may not have been processed. Current screen rows: " + " | ".join(
            r.strip() for r in s.rows if r.strip())[:1500]

    # -- helpers ----------------------------------------------------------

    def _mid(self) -> str:
        return self.session.next_id("m")

    def _cid(self) -> str:
        return self.session.next_id("c")

    def _may_commit(self, name: str, kind: str) -> bool | None:
        if name in GENERIC_NO_COMMIT:
            return False
        if name in self.commit_hints:
            return self.commit_hints[name]
        return None

    def _error(self, code: str, message: str, recoverable: bool, ref: str | None) -> None:
        self.session.emit(ErrorData(code=code, message=message, recoverable=recoverable, ref=ref),
                          turn_id=self.turn_id)

    def _redact_args(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Arguments as the audit log would show them (REQ-014)."""
        out = dict(args)
        if tool == "fill_field" and "value" in out:
            f = self._find_field(args.get("field_ref"))
            if f is None:
                out["value"] = "<redacted>"  # unknown field: fail closed
            else:
                out["value"] = redact(str(out["value"]), hidden=f.hidden, label=f.label)
        return out

    def _find_field(self, ref: Any):
        s = self.mapper.last_screen
        if s is None:
            return None
        for f in s.fields:
            if isinstance(ref, int) and not isinstance(ref, bool) and f.index == ref:
                return f
            if isinstance(ref, list) and len(ref) == 2 and f.row == ref[0] and f.col <= ref[1] < f.col + max(f.length, 1):
                return f
        return None


def _cap(result: dict[str, Any] | None) -> tuple[dict[str, Any] | None, bool]:
    """Cap an event result at 8 KB (contracts 4.3)."""
    if result is None:
        return None, False
    if len(json.dumps(result, ensure_ascii=False)) <= RESULT_CAP:
        return result, False
    slim = {k: v for k, v in result.items() if k != "trace"}
    if len(json.dumps(slim, ensure_ascii=False)) <= RESULT_CAP:
        return slim, True
    return {"status": result.get("status"), "note": "result too large to show"}, True
