"""seance_bridge: turn a 3270 screen into a structured, deterministic model.

Core (no emulator needed): models, readbuffer, parser.
Session layer (needs s3270 + a 3270 host): session, bridge.
"""
from .bridge import Bridge, PressResult
from .errors import (
    AmbiguousAckError,
    FieldValidationError,
    KeyboardTimeoutError,
    ScreenBridgeError,
    SessionError,
)
from .keys import COMMIT_CAPABLE, Key
from .models import (
    BUFFER_SIZE,
    COLS,
    Buffer,
    Field,
    FieldAttrs,
    FieldStart,
    ROWS,
    ScreenModel,
)
from .parser import ScreenParser, diff_positions
from .readbuffer import parse_readbuffer_ascii
from .session import Session

__all__ = [
    "BUFFER_SIZE",
    "COLS",
    "ROWS",
    "Buffer",
    "Field",
    "FieldAttrs",
    "FieldStart",
    "ScreenModel",
    "ScreenParser",
    "diff_positions",
    "parse_readbuffer_ascii",
    "Key",
    "COMMIT_CAPABLE",
    "Bridge",
    "PressResult",
    "Session",
    "ScreenBridgeError",
    "SessionError",
    "KeyboardTimeoutError",
    "AmbiguousAckError",
    "FieldValidationError",
]
