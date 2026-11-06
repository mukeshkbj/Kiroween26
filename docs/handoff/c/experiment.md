# Spec-driven vs vibe coding: the audit drawer (tasks.md 8.2)

Run 2026-11-06 by Agent C. Component: the audit drawer with outcome filter, JSON export and chain status (REQ-015).
The scratch copy has been deleted; the numbers below are copied from that run.

## Method

1. **Spec-built version** (already in `web/src/audit/`): written after reading REQ-015, the design section and the
   contract, with its tests, as part of task 5.3.
2. **Vibe version**: one pass from a one-line request ("add an audit drawer: list audit entries, filter by outcome, export
   json, show if the chain is ok"). No spec, no tests, no reading of the spec-built code. Looked at the result only
   as a vibe coder would: does it compile and render.
3. **Acceptance suite** (13 checks, `A1`..`A13`), written *after* the vibe version, from REQ-015 and contracts 3.4 only,
   and run against **both** implementations through the same four props. I left out decisions that exist only in the
   spec-built code (for example whether "expired" belongs under "rejected").
4. Count the defects the suite finds, then **rework** the vibe version until green.

## Result

| | Spec-built | Vibe, first pass | Vibe, after one rework round |
|---|---|---|---|
| Acceptance checks passed | **13 / 13** | **5 / 13** | **13 / 13** (also under `TZ=Asia/Kolkata`) |
| Component code | 170 lines + 69 lines of pure filter helpers | 74 lines | 134 lines (104 lines added, 44 removed) |
| Own tests | 181 lines, 17 tests (15 at the time) | none | none |
| Time to a compiling, visible component | not reliably measurable (see below) | one write, compiled first time, about 5 s of tool time | |
| Time from the vibe start to all green | | | about 5 minutes, but most of it was building and debugging the acceptance suite (170 lines, two mistakes in my own harness); the rework write itself took one step, about 11 s of tool time |

**Defects in the vibe first pass (9):**

| # | Defect | Needs the spec to know it is wrong? |
|---|---|---|
| A1 | No landmark: a `<div>` rather than a labelled `complementary` region | No (axe/landmark practice) |
| A13 | The filter `<select>` has no accessible name (axe `select-name`, critical) | No |
| A2 | Time shown with `toLocaleTimeString`, so an audit timestamp shifts with the viewer's timezone. **It passed on this UTC machine by luck** and failed under `TZ=Asia/Kolkata` (15:45:30 shown for 10:15:30) | No, but only found because I varied the environment |
| A7 | "Export JSON" exports the **filtered view**, not the log | No: an audit export that silently omits entries is wrong |
| A6 | "Blocked" matches one outcome (`blocked_read_only`); `stale_screen`, `ambiguous_ack` and the other blocking outcomes from the contract vanish from the filter, and "Pending" misses `awaiting_oob` | Yes (needs the contract's outcome list) |
| A9 | Esc did nothing after opening (focus is never moved in) and focus is not returned to the opener | Partly (REQ-015, REQ-018) |
| A10 | No empty states ("no entries", "no entries match") | Yes |
| A11 | 2,000 entries become 2,001 DOM rows | Yes (design says virtualise above 500) |
| A12 | No count, so a filtered list looks like the whole log | Yes |

Five of the nine are wrong whatever the spec says. Four are only wrong against the spec's requirements.

**The spec-built version had 0 defects against the same suite.** My first run showed one failure (A13) that turned out
to be a leaked fixture in my own test (an empty `<button>` appended to `document.body` and never removed); I fixed the
harness, not the drawer. Another, earlier real-browser pass found defects elsewhere in the app but none in the drawer.

## What I take from it

- **The vibe version was faster to something that looked finished, and that is the danger.** It rendered, it filtered,
  it exported, it showed the chain. Four of the nine defects (timezone, export subset, the outcome grouping, the missing
  count) would not show up in a demo, and three of those are about trusting an audit log.
- **The spec's value here was the requirement list, not the documents.** Once REQ-015 and the contract were turned into
  13 checks, vibe code converged to the spec-built architecture in one round (the same outcome table, the same
  windowing, the same count) and ended up 134 lines against 170 + 69. A vibe pass followed by spec-derived checks is a
  legitimate workflow; a vibe pass followed by nothing is not.
- **The spec path's costs are real:** reading three documents, a pure helper module, and 181 lines of tests before the
  first thing rendered. I cannot put a trustworthy time on that (below).
- **The experiment improved the real code a little:** it exposed that the spec-built suite never tested "export while a
  filter is active" or "the time is shown as written in any timezone". Both tests are now in `AuditDrawer.test.tsx`
  (15 -> 17 tests). Both already passed; they were untested, not wrong.

## Limits (read these before quoting any number)

- **Same author, and I remembered the spec-built version.** The vibe pass was not naive; a newcomer would likely do
  worse. This biases towards the vibe path looking *better* than it would for most people.
- **The acceptance suite comes from the same spec the spec-built code was built from.** Of course the spec-built code
  passes it. The five defects that need no spec (A1, A2, A7, A13 and half of A9) are the fairer evidence. The suite was
  validated by the spec-built version passing it, not by anyone else.
- **I am a language model, so "time" is tool latency plus generation, not human effort.** Wall-clock from the start
  to green was about 5 minutes (14:05:10 to about 14:10 on 2026-11-06). I do **not** have a usable time for the
  spec-built version: its commits are 73 seconds apart (`d09bc4c` 04:11:45 to `48a3825` 04:12:58) only because the
  session batched them. I am not inventing one.
- **One component, one run, one author.** This is an anecdote with the defects listed, not a benchmark.
- The acceptance suite needed one test-environment fix (above) and one change of method (scoping by landmark masked
  other failures, so I added a document fallback to count distinct defects rather than cascaded failures).
