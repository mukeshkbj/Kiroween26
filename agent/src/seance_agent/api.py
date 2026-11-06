"""FastAPI surface: REST (contracts 5) and the websocket (contracts 4).

A thin transport over ``SeanceHub``. The defences that live here (REQ-002):

* **Origin.** The websocket is accepted only to be closed with code 4403 unless its
  ``Origin`` header is in ``AGENT_ALLOWED_ORIGINS``; a missing Origin is refused
  too (browsers always send one on a websocket). Any web page the user visits can
  try ``ws://localhost:8000``; this and the token below are why it gets nowhere.
* **Token.** ``hello`` must carry a token issued by ``GET /api/session``. CORS
  headers are sent only to allowed origins, so another origin cannot read it.
* **Controller only.** Enforced in the hub, not here.
"""
from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from . import __version__
from .apps import AppRegistry, live_allowed
from .config import Settings
from .events import Hello, client_message_adapter
from .hub import SeanceHub

MAX_FRAME_BYTES = 16 * 1024
HELLO_TIMEOUT_S = 10.0


def create_app(settings: Settings | None = None, registry: AppRegistry | None = None,
               hub: SeanceHub | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    registry = registry or AppRegistry.load()
    hub = hub or SeanceHub(settings, registry)
    allowed = set(settings.allowed_origins)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with anyio.create_task_group() as tg:
            hub.tg = tg
            try:
                yield
            finally:
                await hub.shutdown()
                tg.cancel_scope.cancel()

    app = FastAPI(title="Seance agent", version=__version__, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.hub = hub
    app.add_middleware(CORSMiddleware, allow_origins=sorted(allowed), allow_methods=["GET"], allow_headers=["*"])

    def origin_ok(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed:
            raise HTTPException(status_code=403, detail="origin_not_allowed")

    @app.get("/api/health", dependencies=[Depends(origin_ok)])
    async def health() -> dict:
        return {"ok": True, "version": __version__, "live_allowed": live_allowed()}

    @app.get("/api/session", dependencies=[Depends(origin_ok)])
    async def session() -> dict:
        return {"token": hub.issue_token(), "session_id": hub.session_id, "v": 1}

    @app.get("/api/apps", dependencies=[Depends(origin_ok)])
    async def apps() -> dict:
        return {"apps": [registry.info(a, settings) for a in registry.all()]}

    @app.get("/api/apps/{app_id}/spirit-map", dependencies=[Depends(origin_ok)])
    async def spirit_map(app_id: str):
        # Only registered ids ever reach the filesystem (no path traversal).
        view = registry.spirit_map_view(app_id) if registry.get(app_id) else None
        if view is None:
            return JSONResponse({"error": "no_map"}, status_code=404)
        return view

    @app.get("/api/audit", dependencies=[Depends(origin_ok)])
    async def audit(limit: int = 500) -> dict:
        return hub.audit(max(1, min(limit, 5000)))

    @app.websocket("/ws/seance")
    async def ws_seance(ws: WebSocket) -> None:
        await ws.accept()
        if ws.headers.get("origin") not in allowed:
            await ws.close(code=4403)
            return
        try:
            with anyio.fail_after(HELLO_TIMEOUT_S):
                first = await ws.receive_text()
            hello = client_message_adapter.validate_json(first) if len(first) <= MAX_FRAME_BYTES else None
        except (TimeoutError, WebSocketDisconnect):
            return
        except ValidationError:
            hello = None
        if not isinstance(hello, Hello):
            await ws.close(code=4400)
            return
        if not hub.token_valid(hello.token):
            await ws.close(code=4401)
            return

        conn_id = secrets.token_hex(4)
        conn = hub.attach(conn_id, hello.token, hello.resume_from)
        disconnected = False
        async with anyio.create_task_group() as tg:
            async def pump() -> None:
                try:
                    async for event in conn.events():
                        await ws.send_text(json.dumps(event, ensure_ascii=False))
                except Exception:  # noqa: BLE001 - a dead socket ends the pump
                    pass
                finally:
                    tg.cancel_scope.cancel()

            tg.start_soon(pump)
            try:
                while True:
                    text = await ws.receive_text()
                    if len(text) > MAX_FRAME_BYTES:
                        await ws.close(code=1009)
                        break
                    await hub.handle(conn, text)
            except WebSocketDisconnect:
                disconnected = True
            finally:
                hub.detach(conn_id)
                tg.cancel_scope.cancel()
        if not disconnected:
            try:
                await ws.close(code=4429)  # too slow or too large: dropped by the session
            except Exception:  # noqa: BLE001
                pass

    return app
