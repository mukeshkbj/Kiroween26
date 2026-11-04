"""Step observers: live events for each primitive operation (docs/contracts.md 4.3).

The agent subscribes in-process and turns these into ``screen`` / ``field_focus``
websocket events, which is what lets the planchette follow a multi-step recipe.

Rules that keep this safe:

* Events carry only data that is already safe to return from a tool: ``ScreenOut``
  (sanitised, hidden values null) and a *redacted* typed value. No hidden value,
  no credential-labelled value, ever.
* Callbacks are synchronous and run inside the service lock, so they must be fast
  (put the event on a queue and return).
* A callback that raises is dropped from that call: it can never fail, delay or
  change a tool operation, and its exception text is not propagated.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .screens import ScreenOut
from .subscribers import Subscribers  # noqa: F401  (re-exported)


class FieldTarget(BaseModel):
    """Where an operation acts. Position and label only, never a value."""

    model_config = ConfigDict(frozen=True)

    index: int
    row: int
    col: int
    length: int
    label: str


class OpEvent(BaseModel):
    """One edge of a primitive operation: ``start`` then exactly one ``end``."""

    model_config = ConfigDict(frozen=True)

    tool: str  # connect | read_screen | list_fields | fill_field | press_key | confirm_action
    phase: Literal["start", "end"]
    outcome: str | None = None  # end only: ok | pending | <stable error code>
    screen_before: ScreenOut | None = None
    screen_after: ScreenOut | None = None
    field: str | None = None  # the caller's field reference, as text
    target: FieldTarget | None = None
    value: str | None = None  # typed value, already redacted
    key: str | None = None
    action_id: str | None = None


OpCallback = Callable[[OpEvent], None]
