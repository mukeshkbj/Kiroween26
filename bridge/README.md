# seance-bridge

Turns a 3270 green-screen into a structured, deterministic `ScreenModel`. The core
of Green Screen Séance — and its go/no-go: if the parser's property tests pass and
the integration test reads a stable `screen_id` from a real TK4- session, the whole
project idea works.

## Layout

- `models.py` — `Buffer`, `Field`, `ScreenModel`, `FieldAttrs`.
- `parser.py` — `ScreenParser`: `Buffer` → `ScreenModel` (pure, property-tested).
- `readbuffer.py` — `parse_readbuffer_ascii`: s3270 `ReadBuffer(Ascii)` output → `Buffer` (line-aware: output line N is row N; validated row by row against `Ascii()` by the integration test).
- `session.py` — subprocess wrapper around `s3270` (needs the binary + a 3270 host).
- `bridge.py` — `Bridge` facade: `connect`, `read_screen`, `fill_field`, `press`, `disconnect`.

## The screen_id contract

`screen_id` is a SHA-256 over the field structure + protected text, with every
unprotected (user-typed) and hidden (secret) position replaced by a fixed
placeholder. So:

- the same screen is recognised again after values are typed;
- typing into an input field never changes the id;
- hidden values never influence the id (let alone appear in the output);
- the MDT (modified) bit is ignored, because typing sets it.

**Volatile regions.** `read_screen()` reads the screen twice; any position that
differs between the two reads is reported in `ScreenModel.volatile` and excluded
from `screen_id` (it stays visible in `rows`). Some stamps are fixed at paint
time, so two quick reads agree but a repaint differs (the TK4- welcome screen's
Date/Time). Pass those as `Bridge(volatile_regions=[(row, col, length)])`.

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
