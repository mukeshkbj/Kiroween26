"""The real entrypoint over a real stdio subprocess (no TK4- needed):
it starts, lists the tools, and refuses to act before connect."""
import os
import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters


def test_stdio_entrypoint_lists_tools_and_requires_connect(tmp_path):
    env = {**os.environ, "AUDIT_LOG_PATH": str(tmp_path / "audit.jsonl"), "SEANCE_ALLOW_COMMIT": "0"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "seance_mcp"], env=env)

    async def go():
        async with Client(params) as c:
            names = {t.name for t in (await c.list_tools()).tools}
            r = await c.call_tool("read_screen", {})
            return names, r

    names, r = anyio.run(go)
    assert {"connect", "read_screen", "press_key", "confirm_action"} <= names
    assert r.is_error and "[not_connected]" in " ".join(getattr(x, "text", "") for x in r.content)
    assert Path(tmp_path / "audit.jsonl").read_text(encoding="utf-8").count("not_connected") == 1
