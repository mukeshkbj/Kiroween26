"""BridgePort: the async seam between the MCP server and the blocking bridge.

The real adapter runs each blocking ``Bridge`` call in a worker thread. It is
serialised by the service's single lock (one s3270 process is strictly one
conversation), so the port itself holds no lock. Tests inject a fake port.
"""
from __future__ import annotations

from typing import Protocol

import anyio

from seance_bridge import Bridge, Key, ScreenModel


class BridgePort(Protocol):
    @property
    def connected(self) -> bool: ...

    async def connect(self, host: str, port: int) -> ScreenModel: ...

    async def disconnect(self) -> None: ...

    async def read_screen(self) -> ScreenModel: ...

    async def fill_field(self, field_ref: int | tuple[int, int], value: str) -> ScreenModel: ...

    async def press(self, key: Key) -> ScreenModel: ...


class RealBridgePort:
    def __init__(self, wait_timeout_ms: int = 5000):
        self._timeout_ms = wait_timeout_ms
        self._bridge: Bridge | None = None

    @property
    def connected(self) -> bool:
        return self._bridge is not None

    def _b(self) -> Bridge:
        if self._bridge is None:
            raise RuntimeError("not connected")
        return self._bridge

    async def connect(self, host: str, port: int) -> ScreenModel:
        await self.disconnect()
        bridge = Bridge(host, port, wait_timeout_ms=self._timeout_ms)
        await anyio.to_thread.run_sync(bridge.connect)
        self._bridge = bridge
        return await self.read_screen()

    async def disconnect(self) -> None:
        if self._bridge is not None:
            b, self._bridge = self._bridge, None
            await anyio.to_thread.run_sync(b.disconnect)

    async def read_screen(self) -> ScreenModel:
        return await anyio.to_thread.run_sync(self._b().read_screen)

    async def fill_field(self, field_ref: int | tuple[int, int], value: str) -> ScreenModel:
        b = self._b()
        return await anyio.to_thread.run_sync(lambda: b.fill_field(field_ref, value))

    async def press(self, key: Key) -> ScreenModel:
        b = self._b()
        return (await anyio.to_thread.run_sync(lambda: b.press(key))).screen
