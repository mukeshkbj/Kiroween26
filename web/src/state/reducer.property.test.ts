import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { initialState, reduce, type Action, type AppState } from './reducer';
import { cleanStreamArb, SENTINEL, withDuplicates, withReordering } from '../../test/arbitraries';
import type { ServerEvent } from '../protocol/types';

/** `at` is a pure function of the event, so replays see the same clock as the first delivery. */
const act = (event: ServerEvent): Action => ({ type: 'server', event, at: event.seq * 10 });

function run(events: ServerEvent[], from: AppState = initialState()): AppState {
  return events.reduce((s, e) => reduce(s, act(e)), from);
}

/** Reference facts about a clean, in-order stream, computed independently of the reducer. */
function facts(events: ServerEvent[]) {
  const calls = new Set<string>();
  const results = new Set<string>();
  const assistantIds = new Set<string>();
  let lastRequired: string | null = null;
  let openId: string | null = null;
  let superseded = false;
  for (const e of events) {
    if (e.type === 'tool_call') calls.add(e.data.tool_call_id);
    if (e.type === 'tool_result' && calls.has(e.data.tool_call_id)) results.add(e.data.tool_call_id);
    if (e.type === 'assistant_delta' || e.type === 'assistant_message') assistantIds.add(e.data.message_id);
    if (e.type === 'confirmation_required') {
      if (openId !== null) superseded = true;
      openId = lastRequired = e.data.action_id;
    }
    if (e.type === 'confirmation_resolved' && e.data.action_id === openId) openId = null;
  }
  return { calls, results, assistantIds, lastRequired, superseded };
}

/** Invariants of REQ-026 that hold after every single event. */
function invariants(s: AppState) {
  const ids = s.messages.map((m) => m.id);
  expect(new Set(ids).size, 'duplicate message ids').toBe(ids.length);

  // Hidden-value sentinel never present anywhere in state.
  expect(JSON.stringify(s)).not.toContain(SENTINEL);

  // Every tool step points at a call that exists, and calls are not shared between steps.
  const stepCalls = Object.values(s.turns).flatMap((t) => t.steps.flatMap((x) => (x.kind === 'tool' ? [x.callId] : [])));
  for (const id of stepCalls) expect(s.toolCalls[id], `step without call ${id}`).toBeDefined();
  expect(new Set(stepCalls).size).toBe(stepCalls.length);

  // A call that has a result has a status; a call without one is still running.
  for (const c of Object.values(s.toolCalls)) {
    if (c.status === 'running') expect(c.summary).toBeNull();
    else expect(c.summary).not.toBeNull();
  }

  // Audit entries are unique and ordered by seq.
  const seqs = s.audit.map((e) => e.seq);
  expect(seqs).toEqual([...new Set(seqs)].sort((a, b) => a - b));

  // The screen cache stays bounded and the current screen is the one cached under its id.
  if (s.screen) expect(s.screensById[s.screen.screenId]).toBeDefined();
  expect(s.focusQueue.length).toBeLessThanOrEqual(50);

  // A confirmation that is resolved carries an outcome; one that is not resolved carries none.
  if (s.confirmation) {
    expect(s.confirmation.phase === 'resolved').toBe(s.confirmation.outcome !== null);
  }
}

describe('reducer invariants (property-based)', () => {
  it('hold after every prefix of a clean stream, and the final state matches an independent model', () => {
    fc.assert(
      fc.property(cleanStreamArb('s_01'), (events) => {
        let s = initialState();
        let lastSeq = 0;
        for (const e of events) {
          s = reduce(s, act(e));
          expect(e.seq).toBeGreaterThan(lastSeq);
          lastSeq = e.seq;
          expect(s.session.lastSeq).toBe(lastSeq);
          invariants(s);
        }
        const f = facts(events);
        expect(Object.keys(s.toolCalls).sort()).toEqual([...f.calls].sort());
        const done = Object.values(s.toolCalls).filter((c) => c.status !== 'running').map((c) => c.id);
        expect(done.sort()).toEqual([...f.results].sort());
        expect(s.messages.filter((m) => m.kind === 'assistant').length).toBe(f.assistantIds.size);
        // "No confirmation without a prior confirmation_required", and it is the latest one.
        if (f.lastRequired === null) expect(s.confirmation).toBeNull();
        else expect(s.confirmation?.actionId).toBe(f.lastRequired);
        // Replacing an unresolved confirmation is recorded in the log, and only then.
        const logged = s.messages.some((m) => m.kind === 'system' && m.code === 'superseded');
        expect(logged).toBe(f.superseded);
      }),
      { numRuns: 200 },
    );
  });

  it('duplicates are no-ops: a stream with repeated events reaches the same state', () => {
    fc.assert(
      fc.property(
        cleanStreamArb('s_01').chain((clean) => withDuplicates(clean).map((dup) => ({ clean, dup }))),
        ({ clean, dup }) => {
          expect(run(dup)).toEqual(run(clean));
        },
      ),
      { numRuns: 200 },
    );
  });

  // Model: one websocket is TCP-ordered and its first event is the server's reply to hello (a session_state), which
  // is the client's baseline. Reordering is what replays across connections can do AFTER that baseline. (Until
  // 2026-11-06 this property also shuffled the first event; that encoded "a fresh client always sees seq 1", which a
  // running agent disproved: it answers a fresh hello with the current state at the current seq.)
  it('reordering inside the resume window converges once the server replays: state equals the clean run', () => {
    fc.assert(
      fc.property(
        cleanStreamArb('s_01').chain((clean) =>
          withReordering(clean.slice(1)).map((rest) => ({ clean, shuffled: [clean[0] as ServerEvent, ...rest] })),
        ),
        ({ clean, shuffled }) => {
          let s = initialState();
          for (const e of shuffled) {
            s = reduce(s, act(e));
            invariants(s);
          }
          // The store reacts to `needsResume` with hello{resume_from}; the server replays seq > lastSeq in order.
          const replay = clean.filter((e) => e.seq > s.session.lastSeq);
          s = run(replay, s);
          expect(s).toEqual(run(clean));
        },
      ),
      { numRuns: 200 },
    );
  });

  it('attaching mid-session: a fresh client takes the server\'s session_state at ANY seq as its baseline, never asks to resume, and then follows the stream exactly', () => {
    fc.assert(
      fc.property(
        cleanStreamArb('s_01'),
        fc.integer({ min: 0, max: 100_000 }),
        (clean, offset) => {
          // The server has history: renumber the stream so it starts deep into the session (as the live agent does).
          const late = clean.map((e) => ({ ...e, seq: e.seq + offset }) as ServerEvent);
          const states = late.map((e, i) => (e.type === 'session_state' ? i : -1)).filter((i) => i >= 0);
          for (const start of states) {
            const suffix = late.slice(start);
            let s = initialState();
            for (const e of suffix) {
              s = reduce(s, act(e));
              expect(s.needsResume, `asked to resume at seq ${e.seq} after attaching at ${suffix[0]?.seq}`).toBe(false);
              invariants(s);
            }
            expect(s.session.lastSeq).toBe(late[late.length - 1]?.seq);
          }
        },
      ),
      { numRuns: 150 },
    );
  });

  it('a fresh client whose first event is NOT a session_state (and not seq 1) still asks to resume rather than guess', () => {
    fc.assert(
      fc.property(cleanStreamArb('s_01'), fc.integer({ min: 1, max: 100_000 }), (clean, offset) => {
        const first = clean.find((e) => e.type !== 'session_state');
        fc.pre(first !== undefined);
        const s = reduce(initialState(), act({ ...first, seq: (first as ServerEvent).seq + offset } as ServerEvent));
        expect(s.needsResume).toBe(true);
        expect(s.session.lastSeq).toBe(0);
      }),
      { numRuns: 100 },
    );
  });

  it('an event that skips ahead is not applied and requests a resume', () => {
    fc.assert(
      fc.property(cleanStreamArb('s_01'), (clean) => {
        fc.pre(clean.length >= 4);
        const s = run(clean.slice(0, 2));
        const skipped = reduce(s, act(clean[3] as ServerEvent));
        expect(skipped.needsResume).toBe(true);
        expect({ ...skipped, needsResume: false }).toEqual(s);
      }),
      { numRuns: 100 },
    );
  });

  it('a new session id discards everything session-scoped and keeps UI preferences', () => {
    fc.assert(
      fc.property(cleanStreamArb('s_01'), cleanStreamArb('s_02'), (a, b) => {
        fc.pre(b.length > 0);
        const ui = { effects: 'full' as const, reduceMotion: true };
        const start = reduce(initialState(), { type: 'ui', patch: ui });
        const s = run([...a, ...b], start);
        expect(s).toEqual(run(b, start));
        expect(s.ui.effects).toBe('full');
        expect(s.ui.reduceMotion).toBe(true);
      }),
      { numRuns: 150 },
    );
  });

  it('there is never more than one confirmation, and a stale resolved id never opens one', () => {
    fc.assert(
      fc.property(cleanStreamArb('s_01'), (clean) => {
        const s = run(clean);
        // `confirmation` is a single slot by construction; check that an unknown id cannot create one.
        const probe: ServerEvent = {
          v: 1, type: 'confirmation_resolved', seq: s.session.lastSeq + 1, ts: 't', session_id: 's_01', turn_id: null,
          data: { action_id: 'never-seen', outcome: 'approved', confirmed_by: 'x', error_code: null },
        };
        const after = reduce(s, act(probe));
        expect(after.confirmation).toEqual(s.confirmation);
      }),
      { numRuns: 100 },
    );
  });

  it('decisions: exactly one decision_sent takes effect per confirmation', () => {
    let exercised = 0;
    fc.assert(
      fc.property(cleanStreamArb('s_01'), (clean) => {
        // Cut the stream right after the last confirmation_required so the modal is still open.
        const idx = clean.map((e) => e.type).lastIndexOf('confirmation_required');
        if (idx < 0) return;
        const s = run(clean.slice(0, idx + 1));
        const c = s.confirmation as NonNullable<typeof s.confirmation>;
        expect(c.phase).toBe('open');
        exercised += 1;
        const once = reduce(s, { type: 'decision_sent', actionId: c.actionId });
        const twice = reduce(once, { type: 'decision_sent', actionId: c.actionId });
        expect(once.confirmation?.phase).toBe('sending');
        expect(twice).toBe(once);
        // A decision for some other action changes nothing.
        expect(reduce(s, { type: 'decision_sent', actionId: 'other' })).toBe(s);
      }),
      { numRuns: 300 },
    );
    expect(exercised).toBeGreaterThan(5);
  });
});