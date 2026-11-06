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
    """s3270 stopped answering a command, so it may or may not have been processed.

    Raised by ``Session._exec`` when its deadline expires. The s3270 process is killed
    and the session is dead: the key (or typed text) is **never** resent, and the caller
    must reconnect and re-read the screen before doing anything else."""


class FieldValidationError(ScreenBridgeError):
    """fill_field rejected a value (protected field, too long, non-numeric...)."""
