# Request to Agent B: promote Agent A's live-run maps into docs/spirit-map

From the integrator, relaying Agent A (`docs/handoff/a/response-b-live-run-*.md`). `docs/spirit-map/` is your folder, so you promote; A deliberately did not.

Run `git merge main` first (A's files are on `main` since 4b9abd3 / 48d54ce, under `docs/handoff/a/live-runs/`).

## 1. seance-insurance: promote now
Source: `docs/handoff/a/live-runs/seance-insurance/` (`spirit-map.json`, `explore.audit.jsonl`, seed, policy, `VOLATILE_REGIONS.txt`, `run.log`).
- Result per A: completed, 5 nodes, 30 edges, 1 frontier, 64 steps; identical to your fake-insurance map (`legacy/scripts/compare_maps.py` says same=True); only ENTER on `confirm` is in the frontier as `denied_commit`; no `SVCUPD` job on the mainframe, so nothing committed.
- Put it under `docs/spirit-map/seance-insurance/`. Run the rest of the pipeline on it (label, generate, review) so the tool pack exists for that `app_id`. Because the screen_ids equal the fake's, the generated tools should differ from fake-insurance's only in `app_id`/`map_hash`; say so if they do not.
- **Do not copy the audit log if it contains anything but redacted values** (it should not; check). `docs/audit/` is gitignored for runtime logs; a run's audit evidence is fine under `docs/handoff/` but only after you have looked at it.
- Approvals (`tool-approvals.json`, `key-policy.json`) are human acts: use `review`, do not copy a file and call it approved. Re-approval is cheap (hash-equal tools).

## 2. tk4-builtins: wait, do not promote the partial map
Source: `docs/handoff/a/live-runs/tk4-builtins/spirit-map.partial.json` is `status: running`, 7 nodes, produced with a patched runner and a hanging bridge. The integrator fixed the bridge on 2026-11-06 (PF/PA wire form, bounded commands, `ambiguous_ack`). A will re-run with the unpatched bridge. Promote **that** map, not this one. If you want the partial one for the write-up, keep it under `docs/handoff/b/` and label it partial.

## 3. Two things from the partial run worth acting on
- Blank unformatted screens after CLEAR are a trap on TK4- (the host never answers an AID there). Consider denying them in the seed (`deny.nodes`) or a small `max_depth`, as A suggests. With the bridge fix a run now ends `ambiguous_ack` instead of hanging, but it still ends.
- The welcome terminal id (see `request-b-tk4-volatile-terminal-id.md`).

Done when: `docs/spirit-map/seance-insurance/` exists with a reviewed tool pack and `scripts/gate.ps1 -Only spirit-map,contracts` is green. Tell me in `docs/handoff/b/` and I will merge.