"""A tiny callback list with unsubscribe and exception isolation.

Dependency-free on purpose: both ``audit`` and ``observe`` use it, and ``observe``
imports ``screens`` which imports ``audit``.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger("seance_mcp.observe")


class Subscribers:
    def __init__(self) -> None:
        self._cbs: list[Callable] = []

    def add(self, cb: Callable) -> Callable[[], None]:
        self._cbs.append(cb)

        def unsubscribe() -> None:
            if cb in self._cbs:
                self._cbs.remove(cb)

        return unsubscribe

    def emit(self, payload: object) -> None:
        for cb in list(self._cbs):
            try:
                cb(payload)
            except Exception as exc:  # noqa: BLE001  (observers must never break the caller)
                # Log the exception type only: its text could carry screen data.
                log.warning("subscriber %r failed: %s", getattr(cb, "__name__", cb), type(exc).__name__)
