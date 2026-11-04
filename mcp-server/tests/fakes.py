"""FakePort: a scripted 3270 app built from real bridge Buffers + ScreenParser,
so fake screens have realistic fields, hidden fields and screen_ids."""
from __future__ import annotations

from seance_bridge import (
    BUFFER_SIZE,
    COLS,
    Buffer,
    FieldAttrs,
    FieldStart,
    FieldValidationError,
    Key,
    KeyboardTimeoutError,
    ScreenModel,
    ScreenParser,
)

PARSER = ScreenParser()
P = FieldAttrs(protected=True)
U = FieldAttrs(protected=False)
UN = FieldAttrs(protected=False, numeric=True)
H = FieldAttrs(protected=False, hidden=True)
HN = FieldAttrs(protected=False, hidden=True, numeric=True)


class ScreenSpec:
    """A mutable screen: text + field starts; typed values persist."""

    def __init__(self, texts: dict[int, str], starts: list[tuple[int, FieldAttrs]], cursor=(0, 0)):
        grid = [" "] * BUFFER_SIZE
        for pos, txt in texts.items():
            for i, ch in enumerate(txt):
                grid[pos + i] = ch
        for pos, _ in starts:
            grid[pos] = " "
        self.text = grid
        self.starts = tuple(FieldStart(pos=p, attrs=a) for p, a in sorted(starts))
        self.cursor = cursor

    def model(self) -> ScreenModel:
        return PARSER.parse(Buffer(text="".join(self.text), field_starts=self.starts,
                                   cursor_row=self.cursor[0], cursor_col=self.cursor[1]))


def rc(row: int, col: int) -> int:
    return row * COLS + col


def logon_screen(extra: dict[int, str] | None = None) -> ScreenSpec:
    texts = {rc(0, 1): "SEANCE TEST SYSTEM", rc(5, 1): "USERID   ===>", rc(6, 1): "PASSWORD ===>",
             rc(7, 1): "ACCOUNT  ===>", rc(8, 1): "PIN      ===>", rc(9, 1): "PF3=EXIT  ENTER=LOGON"}
    texts.update(extra or {})
    starts = [
        (rc(0, 0), P),
        (rc(5, 15), U), (rc(5, 24), P),
        (rc(6, 15), H), (rc(6, 24), P),
        (rc(7, 15), UN), (rc(7, 22), P),
        (rc(8, 15), HN), (rc(8, 20), P),
    ]
    return ScreenSpec(texts, starts, cursor=(5, 16))


def menu_screen() -> ScreenSpec:
    return ScreenSpec({rc(0, 1): "MAIN MENU", rc(3, 1): "1  POLICY ENQUIRY"}, [(rc(0, 0), P)])


class FakePort:
    def __init__(self, screens: dict[str, ScreenSpec] | None = None, start: str = "logon",
                 transitions: dict[tuple[str, str], str] | None = None,
                 timeout_keys: frozenset[str] = frozenset()):
        self.screens = screens or {"logon": logon_screen(), "menu": menu_screen()}
        self.current = start
        self.transitions = transitions if transitions is not None else {
            ("logon", "Enter"): "menu", ("logon", "Clear"): "menu", ("menu", "PF3"): "logon",
        }
        self.timeout_keys = timeout_keys
        self.calls: list[tuple] = []
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self, host: str, port: int) -> ScreenModel:
        self.calls.append(("connect", host, port))
        self._connected = True
        return self.screens[self.current].model()

    async def disconnect(self) -> None:
        self._connected = False

    async def read_screen(self) -> ScreenModel:
        self.calls.append(("read",))
        return self.screens[self.current].model()

    async def fill_field(self, field_ref, value: str) -> ScreenModel:
        spec = self.screens[self.current]
        m = spec.model()
        if isinstance(field_ref, int):
            f = next((x for x in m.fields if x.index == field_ref), None)
        else:
            f = ScreenParser.field_at(m, field_ref[0], field_ref[1])
        if f is None:
            raise FieldValidationError("no such field")
        if f.protected:
            raise FieldValidationError(f"field {f.index} is protected")
        if len(value) > f.length:
            raise FieldValidationError(f"value too long: {len(value)} > field length {f.length}")
        if f.numeric and not value.isdigit():
            raise FieldValidationError(f"field {f.index} is numeric; value is not a number")
        self.calls.append(("fill", f.index, value))
        start = f.row * COLS + f.col
        for i, ch in enumerate(value.ljust(f.length)):
            spec.text[start + i] = ch
        return spec.model()

    async def press(self, key: Key) -> ScreenModel:
        self.calls.append(("press", key.value))  # the key IS sent before any timeout
        if key.value in self.timeout_keys:
            raise KeyboardTimeoutError("keyboard still locked")
        self.current = self.transitions.get((self.current, key.value), self.current)
        return self.screens[self.current].model()

    @property
    def pressed(self) -> list[str]:
        return [c[1] for c in self.calls if c[0] == "press"]
