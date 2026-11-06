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

from .datastream import COLS, OutField, field_attr, rc

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

    def out_fields(self, values: dict[str, str]) -> list[OutField]:
        fields: list[OutField] = []
        # title + static labels
        for r, c, text in self.labels:
            fields.append(OutField(r, c - 1, field_attr(protected=True), text))
        # legend row (protected)
        fields.append(OutField(LEGEND_ROW, 0, field_attr(protected=True), self.legend))
        # message line (volatile, intensified) always present
        fields.append(OutField(MSG_ROW, 0, field_attr(protected=True, intensified=True),
                                values.get("msg", "")[:70]))
        # output display spans (protected, carry data)
        for r, c, length in self.outputs:
            key = f"out_{r}_{c}"
            fields.append(OutField(r, c - 1, field_attr(protected=True),
                                   values.get(key, "")[:length]))
        # input fields (unprotected); add a protected stop one past the end
        for spec in self.inputs:
            fields.append(OutField(spec.row, spec.col - 1,
                                   field_attr(protected=False, numeric=spec.numeric),
                                   values.get(spec.name, "")[:spec.length]))
            stop_col = spec.col + spec.length
            if stop_col < COLS:
                fields.append(OutField(spec.row, stop_col, field_attr(protected=True), ""))
        return fields

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
