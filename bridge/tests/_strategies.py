"""Hypothesis strategies for generating valid, varied Buffers.

Design choices that make the property tests meaningful:
  * Normal grid text uses an alphabet that EXCLUDES the sentinel ``@``.
  * Hidden field DATA is filled with the sentinel ``@``. By construction ``@``
    exists nowhere else, so if any ``@`` shows up in a parsed ScreenModel, a
    hidden value has leaked.
"""
from hypothesis import strategies as st

from seance_bridge.models import BUFFER_SIZE, COLS, ROWS, Buffer, FieldAttrs, FieldStart

_TEXT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789. "
SENTINEL = "@"

_field_attrs = st.builds(
    FieldAttrs,
    protected=st.booleans(),
    numeric=st.booleans(),
    hidden=st.booleans(),
    intensified=st.booleans(),
    mdt=st.booleans(),
)


def _data_region(starts_sorted, i):
    begin = starts_sorted[i].pos + 1
    end = starts_sorted[i + 1].pos if i + 1 < len(starts_sorted) else BUFFER_SIZE
    if end < begin:
        end = begin
    return begin, min(end, BUFFER_SIZE)


@st.composite
def arbitrary_buffer(draw) -> Buffer:
    text = list(
        draw(st.text(alphabet=_TEXT_ALPHABET, min_size=BUFFER_SIZE, max_size=BUFFER_SIZE))
    )
    n_fields = draw(st.integers(0, 16))
    positions = sorted(
        draw(
            st.lists(
                st.integers(0, BUFFER_SIZE - 1),
                min_size=n_fields,
                max_size=n_fields,
                unique=True,
            )
        )
    )
    starts = [FieldStart(pos=p, attrs=draw(_field_attrs)) for p in positions]

    # Attribute byte positions display as blanks.
    for fs in starts:
        text[fs.pos] = " "

    # Hidden field data becomes the sentinel so leakage is detectable.
    for i, fs in enumerate(starts):
        if fs.attrs.hidden:
            begin, end = _data_region(starts, i)
            for p in range(begin, end):
                text[p] = SENTINEL

    return Buffer(
        text="".join(text),
        field_starts=tuple(starts),
        cursor_row=draw(st.integers(0, ROWS - 1)),
        cursor_col=draw(st.integers(0, COLS - 1)),
    )


def change_unprotected_data(buf: Buffer) -> Buffer:
    """Return a copy as if the user had typed into every unprotected field.

    Real typing changes the field's data AND sets its MDT (modified) bit, so we
    do both. Used to prove screen_id is invariant under typed-value changes.
    """
    text = list(buf.text)
    starts = sorted(buf.field_starts, key=lambda f: f.pos)
    flipped: list[FieldStart] = []
    for i, fs in enumerate(starts):
        if not fs.attrs.protected:
            if not fs.attrs.hidden:
                begin, end = _data_region(starts, i)
                for p in range(begin, end):
                    text[p] = "Q" if text[p] != "Q" else "Z"
            fs = FieldStart(pos=fs.pos, attrs=fs.attrs.model_copy(update={"mdt": not fs.attrs.mdt}))
        flipped.append(fs)
    return Buffer(
        text="".join(text),
        field_starts=tuple(flipped),
        cursor_row=buf.cursor_row,
        cursor_col=buf.cursor_col,
    )
