"""Error types for the screen-bridge."""


class ScreenBridgeError(Exception):
    """Base class for all screen-bridge errors."""


class SessionError(ScreenBridgeError):
    """Connection / dropped-session failure."""


class KeyboardTimeoutError(ScreenBridgeError):
    """Timed out waiting for the keyboard to unlock after a key press.

    Raised instead of re-sending the key: an ambiguous acknowledgement is
    treated as a safe failure (see mainframe-safety steering).
    """


class AmbiguousAckError(ScreenBridgeError):
    """Internal guard: never re-send a key whose acknowledgement is ambiguous."""


class FieldValidationError(ScreenBridgeError):
    """fill_field rejected a value (protected field, too long, non-numeric...)."""
