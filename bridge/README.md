# seance-bridge

Turns a 3270 green-screen into a structured, deterministic `ScreenModel`. The core
of Green Screen Séance — and its go/no-go: if the parser's property tests pass and
the integration test reads a stable `screen_id` from a real TK4- session, the whole
project idea works.

## Layout

- `models.py` — `Buffer`, `Field`, `ScreenModel`, `FieldAttrs`.
- `parser.py` — `ScreenParser`: `Buffer` → `ScreenModel` (pure, property-tested).
- `orders.py` — `decode_orders`: raw 3270 datastream → `Buffer`.
- `readbuffer.py` — `parse_readbuffer_ascii`: s3270 `ReadBuffer(Ascii)` text → `Buffer` (validated by the integration test).
- `attrs.py` — decode a 3270 attribute byte into `FieldAttrs`.
- `session.py` — subprocess wrapper around `s3270` (needs the binary + a 3270 host).
- `bridge.py` — `Bridge` facade: `connect`, `read_screen`, `fill_field`, `press`, `disconnect`.

## The screen_id contract

`screen_id` is a SHA-256 over the field structure + protected text, with every
unprotected (user-typed) and hidden (secret) position replaced by a fixed
placeholder. So:

- the same screen is recognised again after values are typed;
- typing into an input field never changes the id;
- hidden values never influence the id (let alone appear in the output).

## Safety

Hidden (non-display) field values are never returned in `ScreenModel` and are
blanked in the output grid. See `.kiro/steering/mainframe-safety.md`.

## Run the tests

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m pytest
```

The integration test (`tests/test_integration.py`) needs `TN3270_HOST` set and a
running TK4- container; it is skipped otherwise.
