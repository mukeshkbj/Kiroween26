# seance-insurance (live, COBOL-backed stand-in)

Promoted from Agent A's live run of 2026-11-06 (`docs/handoff/a/live-runs/seance-insurance/`):
the stand-in on its own port, every lookup/list executed by `SEANCSVC` on TK4-.

- `spirit-map.json` is A's live map, unmodified: 5 screens, 30 edges, 1 frontier item
  (ENTER on confirm, `denied_commit`), 64 steps. Nodes, edges, frontier and home are identical to
  `docs/spirit-map/fake-insurance/spirit-map.json`; only `app_id` and the run stamp differ.
- `explore.seed.json` and `key-policy.json` are the fake-insurance ones, unchanged except `app_id`
  (checked: seed equal, policy equal). The policy equals the contracts golden.
- `labels.json`, `tools.json`, `tools.lock.json`, `key-policy.proposed.json`, `key-policy.evidence.json`,
  `app-description.md` were regenerated here with `label` and `generate` (heuristic labels, the same
  `overrides.json` as the fake). The tool hashes equal the fake-insurance ones, so
  `tool-approvals.json` is the fake-insurance approval file, copied byte for byte, with its original
  approver and time. **A person has not yet reviewed this app separately**; run
  `python -m seance_spirit review --app seance-insurance --tools --by <you>` to re-sign it.
- Tools are `draft` (heuristic confidence 0.5); an LLM labelling run raises that.
