"""Execute a tool pack through the public service, and register tools with an MCP server.

``run_tool`` drives the session only through the ``RecipeService`` facade (read/list/fill/press
only), so every step is gated and audited exactly like a generic call, and a recipe can propose
a commit but can never confirm one (REQ-027, REQ-028). It validates arguments against the strict
input schema itself, because the SDK only checks required/types (task 6.1 spike). No retries; a
step budget applies; the trace is returned so the UI can animate the planchette.

``register`` is the hook mcp-server calls (``seance_spirit.register``). It adds each approved
tool with its JSON Schema as the advertised ``inputSchema`` and returns the registered names.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import jsonschema

from seance_mcp.toolpack import RecipeService

TRUST = "untrusted-screen-data"
DEFAULT_BUDGET = 25


class RunError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _validator(schema: dict) -> jsonschema.protocols.Validator:
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


async def run_tool(service: RecipeService, pack: dict, tool: dict, args: dict) -> dict:
    """Execute one tool. Returns the tool-result envelope (docs/contracts.md 6.3)."""
    trace: list[dict] = []
    try:
        _validate_args(tool, args)
        data, pending = await _execute(service, pack, tool, args, trace)
    except RunError as exc:
        return {"status": "error", "data": {}, "pending": None,
                "error": {"code": exc.code, "message": exc.message}, "trace": trace, "trust": TRUST}
    if pending is not None:
        return {"status": "pending", "data": data, "pending": pending, "error": None,
                "trace": trace, "trust": TRUST}
    return {"status": "ok", "data": data, "pending": None, "error": None, "trace": trace, "trust": TRUST}


def _validate_args(tool: dict, args: dict) -> None:
    try:
        _validator(tool["input_schema"]).validate(args)
    except jsonschema.ValidationError as exc:
        raise RunError("invalid_arguments", f"argument error: {exc.message}") from None


async def _execute(service: RecipeService, pack: dict, tool: dict, args: dict, trace: list[dict]):
    budget = int(tool.get("limits", {}).get("max_steps", DEFAULT_BUDGET))
    volatile = _parse_regions(pack.get("volatile_regions"))
    nav = _Nav.from_pack(pack)
    screen = await _read(service)
    data: dict[str, Any] = {}
    pending = None
    used = 0  # recipe steps plus routing presses count against the budget

    def spend() -> None:
        nonlocal used
        if used >= budget:
            raise RunError("step_budget", f"recipe exceeded {budget} steps")
        used += 1

    for step in tool["recipe"]:
        op = step["op"]
        if op == "goto":
            spend()
            screen = await _goto(service, nav, step["node"], screen, trace, spend)
            continue
        spend()
        if op == "fill":
            screen = await _fill(service, step, args, screen, volatile)
        elif op == "press":
            screen = await _press(service, step, screen)
        elif op == "extract":
            data.update(_extract(step, screen, volatile))
        elif op == "extract_list":
            data.update(await _extract_list(service, step, screen, volatile))
        elif op == "propose":
            pending = await _propose(service, step, screen)
        else:
            raise RunError("invalid_arguments", f"unknown op {op!r}")
        trace.append({"step": len(trace), "op": op, "node": step.get("node") or step.get("on"),
                      "screen_id": screen.screen_id, "key": step.get("key"), "field": step.get("field")})
    return data, pending


async def _read(service: RecipeService):
    try:
        return await service.read_screen()
    except Exception as exc:
        raise RunError(_code(exc), str(exc)) from None


class _Nav:
    """The navigation graph carried in the pack: nodes the map knows and the read-only,
    fill-free key edges between them. Built by the generator from the map; never from labels."""

    def __init__(self, nodes: set[str], edges: list[tuple[str, str, str]]):
        self.nodes = nodes
        self.edges = edges

    @classmethod
    def from_pack(cls, pack: dict) -> "_Nav":
        nav = pack.get("navigation") or {}
        return cls(set(nav.get("nodes", [])),
                   [(e["from"], e["key"], e["to"]) for e in nav.get("edges", [])])

    def route(self, src: str, dst: str) -> list[tuple[str, str]] | None:
        """Shortest list of (key, expected node) from src to dst, deterministic."""
        if src == dst:
            return []
        from collections import deque

        out: dict[str, list[tuple[str, str]]] = {}
        for frm, key, to in sorted(self.edges):
            out.setdefault(frm, []).append((key, to))
        prev: dict[str, tuple[str, str]] = {}
        seen, q = {src}, deque([src])
        while q:
            cur = q.popleft()
            for key, to in out.get(cur, []):
                if to in seen:
                    continue
                seen.add(to)
                prev[to] = (cur, key)
                if to == dst:
                    path, at = [], dst
                    while at != src:
                        p, k = prev[at]
                        path.append((k, at))
                        at = p
                    return path[::-1]
                q.append(to)
        return None


async def _goto(service: RecipeService, nav: _Nav, node_id: str, screen, trace: list[dict], spend):
    """Move to ``node_id`` over the pack's read-only, fill-free edges (contracts 6.2).

    Already there: nothing is pressed. On a screen the map does not know: ``unknown_start``,
    nothing pressed. Each routing press is audited by the service, counted against the step
    budget, verified by landing node, and added to the trace. Nothing is ever typed."""
    here = _nid(screen.screen_id)
    if here == node_id:
        trace.append({"step": len(trace), "op": "goto", "node": node_id, "screen_id": screen.screen_id,
                      "key": None, "field": None})
        return screen
    if here not in nav.nodes:
        raise RunError("unknown_start", f"the current screen ({here}) is not in the map; nothing was pressed")
    route = nav.route(here, node_id)
    if route is None:
        raise RunError("unknown_start", f"no read-only route from {here} to {node_id}; nothing was pressed")
    for key, expect in route:
        spend()
        screen = await _press(service, {"key": key, "expect": expect}, screen)
        trace.append({"step": len(trace), "op": "goto", "node": expect, "screen_id": screen.screen_id,
                      "key": key, "field": None})
    return screen

async def _fill(service: RecipeService, step: dict, args: dict, screen, volatile):
    if _nid(screen.screen_id) != step["node"]:
        raise RunError("screen_mismatch", f"fill expected {step['node']}, on {_nid(screen.screen_id)}")
    value = _resolve_value(step["value"], args)
    if value is None:
        if step.get("skip_if_absent"):
            return screen
        raise RunError("invalid_arguments", f"missing value for field {step['field']!r}")
    field = _field_by_key(screen, step["field"], volatile)
    if field is None:
        raise RunError("screen_mismatch", f"no field {step['field']!r} on {step['node']}")
    try:
        return await service.fill_field(field.index, value)
    except Exception as exc:
        raise RunError(_code(exc), str(exc)) from None


async def _press(service: RecipeService, step: dict, screen):
    try:
        out = await service.press_key(step["key"])
    except Exception as exc:
        raise RunError(_code(exc), str(exc)) from None
    if out.status != "executed" or out.screen is None:
        raise RunError("unexpected_pending", f"{step['key']} was held by the gate (not a propose step)")
    landed = out.screen
    if _nid(landed.screen_id) != step["expect"]:
        raise RunError("screen_mismatch", f"{step['key']} expected {step['expect']}, landed {_nid(landed.screen_id)}")
    return landed


def _extract(step: dict, screen, volatile) -> dict:
    if _nid(screen.screen_id) != step["node"]:
        raise RunError("screen_mismatch", f"extract expected {step['node']}, on {_nid(screen.screen_id)}")
    values = _values_by_field_key(screen, volatile)
    out = {}
    for out_name, field_key in step["into"].items():
        out[out_name] = values.get(field_key, "")
    return out


async def _extract_list(service: RecipeService, step: dict, screen, volatile) -> dict:
    rows: list[dict] = []
    max_rows = int(step["max_rows"])
    paginate = step.get("paginate")
    pages = int(paginate["max_pages"]) if paginate else 1
    for page in range(pages):
        values = _values_by_field_key(screen, volatile)
        for n in _row_indices(step["row_fields"], values, max_rows):
            row = {}
            present = False
            for out_name, pattern in step["row_fields"].items():
                key = pattern.replace("{n}", str(n))
                v = values.get(key, "")
                row[out_name] = v
                present = present or bool(v.strip())
            if present:
                rows.append(row)
        if paginate and page < pages - 1:
            try:
                out = await service.press_key(paginate["key"])
            except Exception as exc:
                raise RunError(_code(exc), str(exc)) from None
            if out.status != "executed" or out.screen is None:
                raise RunError("unexpected_pending", f"{paginate['key']} was held by the gate")
            if out.screen.screen_id == screen.screen_id:
                break  # paging key did not move: end of the list
            screen = out.screen
    return {"rows": rows}


async def _propose(service: RecipeService, step: dict, screen):
    if _nid(screen.screen_id) != step["on"]:
        raise RunError("screen_mismatch", f"propose expected {step['on']}, on {_nid(screen.screen_id)}")
    try:
        out = await service.press_key(step["key"])
    except Exception as exc:
        raise RunError(_code(exc), str(exc)) from None
    if out.status != "pending" or out.action is None:
        raise RunError("unexpected_pending", "a commit step did not produce a pending action")
    return out.action.model_dump(mode="json")


# ---------------------------------------------------------------- helpers


def _row_indices(row_fields: dict[str, str], values: dict[str, str], max_rows: int) -> list[int]:
    """The ``{n}`` values that actually occur on this screen for the row patterns, ascending.

    The generator writes patterns like ``r{n}c1`` where ``{n}`` is the field's row number, so
    the indices are the rows the layout actually has (e.g. 6..13), not 0..max_rows."""
    import re

    per_pattern: list[set[int]] = []
    for pattern in row_fields.values():
        rx = re.compile("^" + re.escape(pattern).replace(r"\{n\}", r"(\d+)") + "$")
        per_pattern.append({int(m.group(1)) for key in values if (m := rx.match(key))})
    if not per_pattern:
        return []
    common = set.intersection(*per_pattern)  # a row exists only where every column has a field
    return sorted(common)[:max_rows]


def _resolve_value(spec, args: dict):
    if isinstance(spec, dict):
        return spec.get("literal")
    if isinstance(spec, str) and spec.startswith("$"):
        return args.get(spec[1:])
    return spec


def _nid(screen_id: str) -> str:
    return "n_" + screen_id[:10]


def _field_by_key(screen, key: str, volatile):
    return _fields_by_key(screen, volatile).get(key)


def _values_by_field_key(screen, volatile) -> dict[str, str]:
    # Extracted values are sanitised screen text; trim trailing fill (3270 fields are fixed width).
    return {k: (f.value or "").rstrip() for k, f in _fields_by_key(screen, volatile).items()}


def _parse_regions(raw) -> frozenset:
    """Positions of the ``volatile_regions`` string (``r,c,len;...``), the mask the generator
    recorded with the pack. Empty/None means no output fields."""
    if not raw:
        return frozenset()
    out: set[int] = set()
    for part in str(raw).split(";"):
        if not part.strip():
            continue
        r, c, n = (int(x) for x in part.split(","))
        out.update(r * 80 + c + i for i in range(n) if 0 <= r * 80 + c + i < 1920)
    return frozenset(out)


def _fields_by_key(screen, volatile=frozenset()):
    """Field keys exactly as explorer.record_node computes them: labels are read from rows with
    unprotected, hidden and output-field cells blanked. An output field is a protected field
    whose span is wholly inside the pack's volatile regions; its cells are blanked so it keys on
    position (``r6c11``), never on the data it holds. Static protected labels (``HOLDER:``) stay,
    so an enquiry display field still keys as ``holder``."""
    from .graph import assign_field_keys, label_from_rows

    cells = [list(r.ljust(80)[:80]) for r in screen.rows]
    for f in screen.fields:
        span = range(f.row * 80 + f.col, min(f.row * 80 + f.col + f.length, 1920))
        if not f.protected or f.hidden or all(p in volatile for p in span):
            for pos in span:
                cells[pos // 80][pos % 80] = " "
    blanked = ["".join(r) for r in cells]
    labels = [label_from_rows(blanked, f.row, f.col) for f in screen.fields]
    keys = assign_field_keys(labels, [(f.row, f.col) for f in screen.fields])
    return {k: f for k, f in zip(keys, screen.fields)}


def _code(exc: Exception) -> str:
    msg = str(exc)
    for code in ("keyboard_timeout", "session_lost", "not_connected", "field_invalid", "read_only",
                 "needs_resync", "stale_screen", "bad_key"):
        if code in msg:
            return code
    return "bridge_error"


# ---------------------------------------------------------------- registration (mcp-server hook)


def register(server: Any, recipe_service: RecipeService, tools: Sequence[dict], pack: dict) -> list[str]:
    """Add each (already approved) tool to the MCP server. Returns registered names.

    Task 6.1 spike: build a handler whose generated signature matches the tool's input schema
    (so the SDK enforces required/types), then advertise the strict JSON Schema by overriding
    the tool's ``parameters``. The runtime validates the strict rules itself.
    """
    from mcp.server.mcpserver.tools.base import Tool

    import inspect

    names: list[str] = []
    for tool in tools:
        handler = _make_handler(server, recipe_service, pack, tool)
        t = Tool.from_function(handler, name=tool["name"], title=tool.get("title"),
                               description=tool.get("description"), structured_output=False)
        t.parameters = tool["input_schema"]
        server._tool_manager._tools[tool["name"]] = t  # noqa: SLF001 - the only SDK-private seam (spike)
        names.append(tool["name"])
    return names


def _make_handler(server, recipe_service, pack, tool):
    import inspect

    schema = tool["input_schema"]
    required = list(schema.get("required", []))
    optional = [p for p in schema.get("properties", {}) if p not in required]
    params = [inspect.Parameter(n, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str) for n in required]
    params += [inspect.Parameter(n, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation="str | None")
               for n in optional]
    sig = inspect.Signature(params)

    async def handler(*a, **kw):
        bound = sig.bind(*a, **kw)
        bound.apply_defaults()
        args = {k: v for k, v in bound.arguments.items() if v is not None}
        return await run_tool(recipe_service, pack, tool, args)

    handler.__signature__ = sig  # type: ignore[attr-defined]
    handler.__annotations__ = {p.name: p.annotation for p in params} | {"return": dict}
    handler.__name__ = tool["name"]
    return handler
