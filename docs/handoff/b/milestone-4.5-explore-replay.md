# Agent B: task 4.5 done (explore + replay green on fake-insurance)

Date: 2026-11-04. Branch `agent/b-spirit-map`. Tasks 1 to 4 complete.

## What exists
- `spirit-map/` package `seance_spirit`: `seed`, `policy` (pure, deny beats allow, text hints only deny), `graph`, `store` (atomic, canonical, leak-checked), `driver` (policy-gated session access), `explorer`, `replay`, `__main__` (`explore`, `replay`).
- `docs/spirit-map/fake-insurance/`: `explore.seed.json` (human), `spirit-map.json` (generated; 5 screens, 30 edges, 1 frontier item).
- Result on `fake-insurance`: menu, enquiry, list, update, confirm found with 64 steps. The only frontier item is `ENTER` on `confirm`, `denied_commit`. `app.dirty` stays false and no commit-capable key was ever sent that the seed did not declare. Replay of a fresh copy: 30 edges, 0 mismatches.
- Node ids equal the golden ones (`n_ba02cc6364` menu, `n_419888f22d` enquiry, `n_c5d11dedae` list, `n_96fa848aaa` update, `n_483e5fe116` confirm).

## Commands
```
cd spirit-map
.venv\Scripts\python.exe -m seance_spirit explore --app fake-insurance --fake fake-insurance
.venv\Scripts\python.exe -m seance_spirit replay  --app fake-insurance --fake fake-insurance
.venv\Scripts\python.exe -m pytest            # about 55 s
powershell -File scripts/gate.ps1 -Only spirit-map,contracts      # ok
```

## Tests (REQ numbers from the spec)
- REQ-033 safety: Hypothesis `fake_apps` (hostile apps, mutating ENTER/PF keys, hidden fields, legends that say DELETE, deny lists). The model of "allowed" is in `tests/fake_apps.py::Case.allowed`, written from the case data, not from the policy under test. Mutation oracles kill six policy mutants; two over-allowing mutants are held by candidate generation and the gate (and reach the app only when those layers are removed too).
- REQ-034 completeness, REQ-032 replay: property tests on connected random apps; replay detects a changed app.
- REQ-002: AST test that nothing in `src/` mentions the confirm path.
- REQ-004/035 (explorer part): hidden and credential values never typed, never stored; sentinel test on the written file.
- Policy: unit, model-based and 10-mutant mutation checks (`test_policy_mutations.py`).

## Decisions and deviations worth reading
1. **Output fields** are protected fields whose span equals a seed `volatile` region exactly. `ScreenOut` carries no mask, so the seed lists the regions (request file `request-integrator-screenout-volatile.md`).
2. **Field keys** come from screen text. `upddate` and `msg` exist only inside the fake; the map has `updated` and `r22c1`. Names come from labels or `overrides.json` in task 5/6.
3. **Gate layer reads declarations from data**, not through `may_press`, so a policy bug cannot widen what the service sends.
4. `denied_screen` is a trap: if the only way out of a screen needs a key on that screen, the explorer cannot leave. Use `deny.screen_keys` for finer control.
5. Counts in merged maps are high-water marks (so `merge(m, m) == m`).

## Next
Task 5 (labelling), then 6 (spike 6.1 first: dynamic tool registration in `mcp` 2.x, due 12 Nov).
