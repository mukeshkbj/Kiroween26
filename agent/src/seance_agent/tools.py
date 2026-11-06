"""ToolBroker: the agent's only path to the MCP tools (REQ-005 to REQ-007).

The agent hosts ``seance_mcp``'s ``MCPServer`` in-process and talks to it through
a real in-memory MCP ``ClientSession`` (``create_client_server_memory_streams``),
so tool discovery, JSON Schemas and error codes are the genuine MCP ones. Nothing
here reaches the 3270 session except through that client.

Three safety jobs live here, independent of the model (design.md "Enforcement
layers"):

* **Allowlist.** ``confirm_action``, ``connect`` and ``get_audit_log`` are removed
  from the catalogue the model ever sees and are refused if the model names them
  anyway. There is no model-visible way to confirm a commit. ``AGENT_GENERIC_TOOLS=off``
  additionally drops the four generic tools.
* **Schema validation.** Every call is validated against the tool's own
  ``input_schema`` *before* it is sent; an invalid call becomes an error result
  handed back to the model, never a bridge operation.
* **Error mapping.** ``seance_mcp`` raises ``GateError`` which the server turns into
  a ``ToolError`` with text ``[code] message``; the broker parses that back into a
  stable ``error_code`` (contracts section 3.5) so the loop and UI see codes, not
  prose.

Lifecycle: ``async with ToolBroker.start(server) as broker:`` runs the server over
the memory streams and yields a ready, initialised broker.
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import anyio
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaValidationError
from mcp import types
from mcp.client.session import ClientSession
from mcp.server.mcpserver import MCPServer
from mcp.shared.memory import create_client_server_memory_streams

# Never offered to the LLM, never callable by it (REQ-006, safety invariant 2).
WITHHELD_TOOLS = frozenset({"confirm_action", "connect", "get_audit_log"})
# The generic screen tools (kept unless AGENT_GENERIC_TOOLS=off).
GENERIC_TOOLS = frozenset({"read_screen", "list_fields", "fill_field", "press_key"})

_ERROR_RE = re.compile(r"\[(?P<code>[a-z_]+)\]\s*(?P<msg>.*)$", re.DOTALL)
_DEFAULT_ERROR_CODE = "bridge_error"


def _strict_object(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` that forbids unknown top-level properties.

    The MCP SDK generates tool input schemas *without* ``additionalProperties:
    false`` (verified against mcp==2.3.0: ``read_screen`` is ``{"properties": {},
    "type": "object"}``). REQ-007 wants extra or malformed arguments rejected
    before anything is sent, so the broker tightens the schema here rather than
    trusting the server to ignore stray kwargs. Nested objects are left as the
    tool declared them."""
    if schema.get("type") != "object" or "additionalProperties" in schema:
        return schema
    return {**schema, "additionalProperties": False}


@dataclass(frozen=True)
class ToolSpec:
    """A tool as offered to the model: name, kind, schemas, description."""

    name: str
    kind: str  # "business" | "generic"
    title: str | None
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None


@dataclass(frozen=True)
class ToolOutcome:
    """The result of a call, already classified for the loop and the UI.

    ``status`` is the business-envelope status (contracts 6.3) or the generic
    tool's status: ``ok`` | ``pending`` | ``error``. ``structured`` is the raw
    structured content the model is shown (wrapped untrusted by prompts.py). For
    a pending result the gate now holds the authoritative action; the broker does
    not carry its snapshot (that comes from the gate, never from here)."""

    tool: str
    kind: str
    status: str
    error_code: str | None
    structured: dict[str, Any] | None
    summary: str


class ToolError(Exception):
    """A call the broker refused to send (not an MCP error). Carries a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ToolBroker:
    """Owns the in-memory MCP client and the filtered tool catalogue."""

    def __init__(self, session: ClientSession, *, generic_tools: bool = True):
        self._session = session
        self._generic_tools = generic_tools
        self._catalog: dict[str, ToolSpec] = {}

    # -- lifecycle --------------------------------------------------------

    @classmethod
    @asynccontextmanager
    async def start(
        cls, server: MCPServer, *, generic_tools: bool = True
    ) -> AsyncIterator["ToolBroker"]:
        """Run ``server`` over in-memory streams and yield a ready broker."""
        low = server._lowlevel_server
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            c_read, c_write = client_streams
            s_read, s_write = server_streams
            async with anyio.create_task_group() as tg:

                async def _serve() -> None:
                    await low.run(s_read, s_write, low.create_initialization_options())

                tg.start_soon(_serve)
                async with ClientSession(c_read, c_write) as session:
                    await session.initialize()
                    broker = cls(session, generic_tools=generic_tools)
                    await broker.refresh_catalog()
                    try:
                        yield broker
                    finally:
                        tg.cancel_scope.cancel()

    # -- catalogue --------------------------------------------------------

    async def refresh_catalog(self) -> None:
        """Rebuild the tool catalogue from the server, applying the allowlist.

        A tool is classified ``generic`` if it is one of the four generic screen
        tools, else ``business`` (it came from the approved spirit-map pack). The
        withheld tools are dropped entirely."""
        listing = await self._session.list_tools()
        catalog: dict[str, ToolSpec] = {}
        for tool in listing.tools:
            name = tool.name
            if name in WITHHELD_TOOLS:
                continue
            is_generic = name in GENERIC_TOOLS
            if is_generic and not self._generic_tools:
                continue
            catalog[name] = ToolSpec(
                name=name,
                kind="generic" if is_generic else "business",
                title=tool.title,
                description=tool.description or "",
                input_schema=dict(tool.input_schema or {"type": "object"}),
                output_schema=dict(tool.output_schema) if tool.output_schema else None,
            )
        self._catalog = catalog

    def specs(self) -> list[ToolSpec]:
        """Business tools first (REQ-006), then the generic ones, each group sorted."""
        business = sorted((s for s in self._catalog.values() if s.kind == "business"), key=lambda s: s.name)
        generic = sorted((s for s in self._catalog.values() if s.kind == "generic"), key=lambda s: s.name)
        return business + generic

    def counts(self) -> tuple[int, int]:
        """(business, generic) counts for session_state.tools."""
        business = sum(1 for s in self._catalog.values() if s.kind == "business")
        generic = sum(1 for s in self._catalog.values() if s.kind == "generic")
        return business, generic

    def spec(self, name: str) -> ToolSpec | None:
        return self._catalog.get(name)

    def kind_of(self, name: str) -> str | None:
        s = self._catalog.get(name)
        return s.kind if s else None

    # -- validation -------------------------------------------------------

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> None:
        """Raise ``ToolError('invalid_arguments', ...)`` if the call is not allowed
        or does not match the tool's input schema. Checked before anything is sent."""
        if name in WITHHELD_TOOLS:
            # The model named a withheld tool: refuse, do not reach the server.
            raise ToolError("invalid_arguments", f"tool {name!r} is not available to the model")
        spec = self._catalog.get(name)
        if spec is None:
            raise ToolError("invalid_arguments", f"unknown tool {name!r}")
        schema = _strict_object(spec.input_schema)
        try:
            Draft202012Validator(schema).validate(arguments)
        except SchemaValidationError as exc:
            raise ToolError("invalid_arguments", f"arguments do not match schema: {exc.message}") from None

    # -- call -------------------------------------------------------------

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        """Validate, then call the tool over the MCP client, then classify the
        result. A refusal to send (bad args / withheld tool) returns an ``error``
        outcome; it is never sent to the bridge."""
        kind = self.kind_of(name) or "generic"
        try:
            self.validate_arguments(name, arguments)
        except ToolError as exc:
            return ToolOutcome(tool=name, kind=kind, status="error", error_code=exc.code,
                               structured=None, summary=exc.message)

        result = await self._session.call_tool(name, arguments)
        return self._classify(name, kind, result)

    def _classify(self, name: str, kind: str, result: types.CallToolResult) -> ToolOutcome:
        if result.is_error:
            code, msg = self._parse_error(result)
            return ToolOutcome(tool=name, kind=kind, status="error", error_code=code,
                               structured=None, summary=msg)
        structured = result.structured_content
        if structured is None:
            # Generated (business) tools return their envelope as JSON text, not
            # structured content. Parse it, or a pending commit would read as ok.
            structured = self._parse_text_json(result)
        status = self._status_of(name, kind, structured)
        code = None
        if status == "error" and structured:
            err = structured.get("error")
            code = str(err.get("code")) if isinstance(err, dict) and err.get("code") else _DEFAULT_ERROR_CODE
        return ToolOutcome(tool=name, kind=kind, status=status, error_code=code,
                           structured=structured, summary=self._summary(name, status, structured))

    @staticmethod
    def _parse_text_json(result: types.CallToolResult) -> dict[str, Any] | None:
        for block in result.content:
            if isinstance(block, types.TextContent):
                try:
                    obj = json.loads(block.text)
                except ValueError:
                    return None
                return obj if isinstance(obj, dict) else None
        return None

    @staticmethod
    def _status_of(name: str, kind: str, structured: dict[str, Any] | None) -> str:
        """``pending`` for a press/propose that returned a pending action, else ``ok``.

        Business tools carry an explicit ``status`` (contracts 6.3). The generic
        ``press_key`` returns ``PressOut`` whose ``status`` is ``pending`` or
        ``executed``; everything else generic is ``ok``."""
        if structured is None:
            return "ok"
        if kind == "business" and "status" in structured:
            return str(structured["status"])
        press_status = structured.get("status")  # PressOut
        if press_status == "pending":
            return "pending"
        return "ok"

    @staticmethod
    def _summary(name: str, status: str, structured: dict[str, Any] | None) -> str:
        if status == "pending":
            return f"{name} needs a human to confirm a commit-capable key"
        return f"{name} ok"

    @staticmethod
    def _parse_error(result: types.CallToolResult) -> tuple[str, str]:
        text = ""
        for block in result.content:
            if isinstance(block, types.TextContent):
                text = block.text
                break
        m = _ERROR_RE.search(text.strip())
        if m:
            return m.group("code"), m.group("msg").strip()
        return _DEFAULT_ERROR_CODE, text or "the tool reported an error"


__all__ = [
    "ToolBroker",
    "ToolSpec",
    "ToolOutcome",
    "ToolError",
    "WITHHELD_TOOLS",
    "GENERIC_TOOLS",
]
