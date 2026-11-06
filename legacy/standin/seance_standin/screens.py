"""The five Seance Insurance screens, built to contracts section 10.

Field positions mirror ``seance_mcp.fake`` exactly (0-origin data columns). Each
``Screen`` returns the outbound ``OutField`` list for an Erase/Write and knows
its named input fields so the app can read what the user typed.

VOLATILE_REGIONS (contract 10.4) are the output/message spans that change with
the data; they are documented in legacy/volatile-regions.txt and must equal
DEMO_VOLATILE_REGIONS in seance_mcp.fake.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .datastream import COLS, SIZE, OutField, OutText, field_attr, rc

LEGEND_ROW = 23
MSG_ROW = 22


@dataclass
class InputSpec:
    """A named unprotected field: data at (row, col), given length."""

    name: str
    row: int
    col: int
    length: int
    numeric: bool = False


@dataclass
class Screen:
    name: str
    labels: list[tuple[int, int, str]]        # (row, col, protected text)
    inputs: list[InputSpec]
    outputs: list[tuple[int, int, int]]       # (row, col, length) protected/volatile
    legend: str
    cursor_field: str | None = None
    # dynamic data the app fills in before sending (name -> text), covering both
    # output spans and message line.
    data: dict[str, str] = field(default_factory=dict)

    def texts(self) -> list[OutText]:
        """Static labels and the legend: plain buffer text, no field starts."""
        out = [OutText(r, c, text) for r, c, text in self.labels]
        out.append(OutText(LEGEND_ROW, 1, self.legend))
        return out

    def out_fields(self, values: dict[str, str]) -> list[OutField]:
        """Field starts exactly as ``seance_mcp.fake.build_screen`` lays them out,
        so the stand-in's screen_ids equal the fake's (B's approved key policy is
        keyed by screen_id and then applies to the real-backed app unchanged):

        * a protected start at buffer offset 0;
        * per named field an attribute byte at (row, col-1) -- unprotected for
          inputs (numeric if so), protected for outputs and the message line;
        * a protected terminator right after each named field's data, unless
          another field starts there.
        Static text is not a field; see ``texts()``.
        """
        named: list[tuple[int, int, int, int, str]] = []   # row, col, len, attr, data
        for spec in self.inputs:
            named.append((spec.row, spec.col, spec.length,
                          field_attr(protected=False, numeric=spec.numeric),
                          values.get(spec.name, "")[:spec.length]))
        for r, c, length in self.outputs:
            named.append((r, c, length, field_attr(protected=True),
                          values.get(f"out_{r}_{c}", "")[:length]))
        named.append((MSG_ROW, 1, 70, field_attr(protected=True), values.get("msg", "")[:70]))

        starts: dict[int, tuple[int, str]] = {0: (field_attr(protected=True), "")}
        for r, c, length, _, _ in named:                 # terminators first ...
            end = rc(r, c) + length
            if end < SIZE:
                starts.setdefault(end, (field_attr(protected=True), ""))
        for r, c, _, attr, data in named:                # ... named starts override
            starts[rc(r, c) - 1] = (attr, data)
        return [OutField(pos // COLS, pos % COLS, attr, data)
                for pos, (attr, data) in sorted(starts.items())]

    def cursor_offset(self) -> int:
        if self.cursor_field:
            for spec in self.inputs:
                if spec.name == self.cursor_field:
                    return rc(spec.row, spec.col)
        return 0


def _menu() -> Screen:
    return Screen(
        name="menu",
        labels=[
            (0, 1, "SEANCE INSURANCE - MAIN MENU"),
            (3, 3, "1  POLICY ENQUIRY"),
            (4, 3, "2  POLICY LIST"),
            (5, 3, "3  POLICY UPDATE"),
            (7, 3, "OPTION ===>"),
        ],
        inputs=[InputSpec("option", 7, 15, 1)],
        outputs=[],
        legend="ENTER=SELECT  CLEAR=EXIT",
        cursor_field="option",
    )


def _enquiry() -> Screen:
    return Screen(
        name="enquiry",
        labels=[
            (0, 1, "SEANCE INSURANCE - POLICY ENQUIRY"),
            (3, 1, "POLNO ===>"),
            (5, 1, "HOLDER:"),
            (6, 1, "STATUS:"),
            (7, 1, "PREMIUM:"),
            (8, 1, "UPDATED:"),
        ],
        inputs=[InputSpec("polno", 3, 13, 8)],
        outputs=[(5, 13, 20), (6, 13, 10), (7, 13, 10), (8, 13, 10)],
        legend="ENTER=LOOK UP  PF3=BACK",
        cursor_field="polno",
    )


def _list() -> Screen:
    outputs: list[tuple[int, int, int]] = []
    for i in range(8):
        outputs += [(6 + i, 1, 8), (6 + i, 11, 20), (6 + i, 33, 10)]
    return Screen(
        name="list",
        labels=[
            (0, 1, "SEANCE INSURANCE - POLICY LIST"),
            (3, 1, "SELECT ===>"),
            (5, 1, "POLNO     HOLDER               STATUS"),
        ],
        inputs=[InputSpec("select", 3, 13, 2)],
        outputs=outputs,
        legend="PF7=UP  PF8=DOWN  PF3=BACK",
        cursor_field="select",
    )


def _update() -> Screen:
    return Screen(
        name="update",
        labels=[
            (0, 1, "SEANCE INSURANCE - POLICY UPDATE"),
            (3, 1, "POLNO ===>"),
            (5, 1, "STATUS (A/L/C) ===>"),
            (6, 1, "PREMIUM ===>"),
            (8, 1, "HOLDER:"),
        ],
        inputs=[
            InputSpec("polno", 3, 13, 8),
            InputSpec("status", 5, 22, 1),
            InputSpec("premium", 6, 22, 7, numeric=True),
        ],
        outputs=[(8, 13, 20)],
        legend="ENTER=REVIEW CHANGE  PF3=BACK",
        cursor_field="polno",
    )


def _confirm() -> Screen:
    return Screen(
        name="confirm",
        labels=[
            (0, 1, "SEANCE INSURANCE - CONFIRM UPDATE"),
            (3, 1, "POLNO:"),
            (4, 1, "HOLDER:"),
            (5, 13, "OLD"),
            (5, 25, "NEW"),
            (6, 1, "STATUS:"),
            (7, 1, "PREMIUM:"),
        ],
        inputs=[],
        outputs=[(3, 13, 8), (4, 13, 20), (6, 13, 1), (6, 25, 1), (7, 13, 7), (7, 25, 7)],
        legend="ENTER=CONFIRM AND SAVE  PF3=CANCEL",
    )


def all_screens() -> dict[str, Screen]:
    return {s.name: s for s in (_menu(), _enquiry(), _list(), _update(), _confirm())}


# VOLATILE_REGIONS as (row, col, length), 0-origin. MUST equal
# DEMO_VOLATILE_REGIONS in seance_mcp.fake (contract 10.4).
VOLATILE_REGIONS: tuple[tuple[int, int, int], ...] = (
    (22, 1, 70),
    (5, 13, 20), (6, 13, 10), (7, 13, 10), (8, 13, 10),
    *[(6 + i, 1, 8) for i in range(8)],
    *[(6 + i, 11, 20) for i in range(8)],
    *[(6 + i, 33, 10) for i in range(8)],
    (8, 13, 20),
    (3, 13, 8), (4, 13, 20), (6, 13, 1), (6, 25, 1), (7, 13, 7), (7, 25, 7),
)
