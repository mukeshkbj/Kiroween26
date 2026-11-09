# For Agent B: live exploration of the Seance Insurance app (stand-in + real COBOL)

Run by Agent A on 2026-11-06 against the live, COBOL-backed app: the stand-in on
port 3271, with every lookup/list executed by `SEANCSVC` on TK4-. I used your
CLI unmodified, with your **own** fake-insurance seed and your human-approved
`key-policy.json`. Both files are copied unchanged except `app_id:
seance-insurance`; the seed check printed "identical except app_id: True".

## Result: the live map is identical to your fake-insurance map
```
completed: 5 screens, 30 edges, 1 frontier, 64 steps
nodes  live=5  fake=5  same=True
edges  live=30 fake=30 same=True
frontier [('n_483e5fe116', 'ENTER', 'denied_commit')]  same=True
```
(Produced by `legacy/scripts/compare_maps.py` against
`docs/spirit-map/fake-insurance/spirit-map.json`.)

Files are in `docs/handoff/a/live-runs/seance-insurance/`: `spirit-map.json`,
`explore.audit-summary.txt` (one line per audit entry, no values, hash chain
checked: linked), the seed and policy used, and `VOLATILE_REGIONS.txt` (the
exact env value). The raw `*.audit.jsonl` and `run.log` are gitignored runtime
data (repo policy), so I kept them on A's machine only; ask if you need a field
from them. Correction 2026-11-06: an earlier version of this note said they were
committed. Promote them into
`docs/spirit-map/seance-insurance/` if you want them there (your folder, so I
have not).

## Why the ids match now
On the first comparison today, the stand-in's `screen_id`s did NOT match the
fake's. The rows were identical, but the stand-in used one field start per
label, while `build_screen` uses a single protected start at offset 0 plus starts
only for the named fields. I changed the stand-in (`legacy/standin`, my folder)
to emit exactly `build_screen`'s field structure. All 5 screens now match the
fake, both offline (`legacy/standin/tests/test_parity.py`) and live
(`legacy/scripts/check_parity.py` on a fresh capture, `PARITY OK`). Your approved
policy therefore covers the real app as-is, and `tools.json`'s node ids apply
too.

## Safety
- Keys per screen (from the audit): ENTER was pressed only on menu (11),
  enquiry (1), list (1) and update (3). These are all read-only in your approved
  policy. The confirm screen received only CLEAR, PF3, PA1-3 and PF13: **zero
  ENTERs**.
- The audit has 1 connect, 22 fills (your probes: option 1/2/3, P0000001, L,
  300) and 42 key presses, all `ok`. The only commit-capable key, ENTER on
  confirm, stayed in the frontier as `denied_commit`.
- The mainframe log shows no `SVCUPD` (update) job after the pre-run reset. The
  only jobs during the run were read-only `SVCRUN` lookups. Policy data is
  unchanged.

## A bug in your CLI (request)
`seance_spirit explore` (and `replay`) construct `Explorer`/`replay_map` without
`host`/`tn_port`. A non-attach run therefore always connects to
`localhost:3270`, ignoring `TN3270_HOST`/`TN3270_PORT`, even though the CLI
reads `Settings.from_env()` for everything else. The tk4-builtins run only worked
because TK4- happens to be on 3270. My runner (`legacy/scripts/live_explore.py`)
passes `host=s.host, tn_port=s.port` from `Settings.from_env()`. Please add that
in `cmd_explore`/`cmd_replay`; after that the runner no longer needs to override
the connect target.

## Run it again
```
# A only (live). Stand-in up on 3271, TK4- up:
$env:TN3270_PORT="3271"; $env:WAIT_TIMEOUT_MS="30000"
$env:VOLATILE_REGIONS=(Get-Content docs/handoff/a/live-runs/seance-insurance/VOLATILE_REGIONS.txt)
mcp-server/.venv/Scripts/python legacy/scripts/live_explore.py explore --app seance-insurance --dir docs/handoff/a/live-runs/seance-insurance --stamp
```
