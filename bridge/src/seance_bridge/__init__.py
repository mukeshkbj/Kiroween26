"""seance_bridge: turn a 3270 screen into a structured, deterministic model.

Core (no emulator needed): models, attrs, orders, parser.
Session layer (needs s3270 + a 3270 host): session, bridge.
"""
from .attrs import attrs_from_byte
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
from .orders import decode_orders
from .parser import ScreenParser
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
    "decode_orders",
    "parse_readbuffer_ascii",
    "attrs_from_byte",
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
