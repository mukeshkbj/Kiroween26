"""3270 attention keys."""
from enum import StrEnum

_members = {
    "ENTER": "Enter",
    "CLEAR": "Clear",
    "PA1": "PA1",
    "PA2": "PA2",
    "PA3": "PA3",
}
_members.update({f"PF{n}": f"PF{n}" for n in range(1, 25)})


class Key(StrEnum):
    """A 3270 attention key: ENTER, CLEAR, PA1-3, PF1-24."""

    pass


# Rebuild from the dict so PF1..PF24 are real members.
Key = StrEnum("Key", _members)  # type: ignore[assignment,misc]

# Keys that may commit data when pressed on a data-entry screen. Callers use
# this to decide whether to demand confirmation (see mainframe-safety steering).
COMMIT_CAPABLE = frozenset({Key.ENTER, Key.PF1, Key.PF2, Key.PF3, Key.PF4, Key.PF5,
                            Key.PF6, Key.PF7, Key.PF8, Key.PF9, Key.PF10, Key.PF11,
                            Key.PF12})
