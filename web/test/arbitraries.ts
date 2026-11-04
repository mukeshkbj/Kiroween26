import fc from 'fast-check';
import type { FieldOut, ScreenOut, ServerEvent, ResolvedOutcome } from '../src/protocol/types';

/**
 * Generative grammar for valid server event streams, built by construction (REQ-026), plus mutations that
 * model what a real network does to them: duplicates, reordering inside the resume window, and reconnects
 * with a new session id.
 */

/** Planted in the `value` of hidden fields. It must never reach reducer state. */
export const SENTINEL = 'SENTINEL-HIDDEN-9f3a';

const ids = ['a1b2', 'c3d4', 'e5f6', '0718'] as const;

const fieldArb = fc.record({
  row: fc.integer({ min: 0, max: 23 }),
  col: fc.integer({ min: 1, max: 70 }),
  length: fc.integer({ min: 1, max: 9 }),
  hidden: fc.boolean(),
  protected: fc.boolean(),
  numeric: fc.boolean(),
  intensified: fc.boolean(),
  value: fc.string({ maxLength: 9 }),
});

export const screenArb: fc.Arbitrary<ScreenOut> = fc
  .record({
    id: fc.constantFrom(...ids),
    rows: fc.array(fc.string({ maxLength: 80 }), { minLength: 24, maxLength: 24 }),
    fields: fc.array(fieldArb, { maxLength: 5 }),
    cursor: fc.tuple(fc.integer({ min: 0, max: 23 }), fc.integer({ min: 0, max: 79 })),
  })
  .map(({ id, rows, fields, cursor }) => ({
    trust: 'untrusted-screen-data' as const,
    screen_id: id.repeat(16),
    cursor,
    rows: rows.map((r) => r.padEnd(80, ' ')),
    // The server sends null for hidden fields. The grammar deliberately does NOT: it plants the sentinel so that
    // a reducer that trusts the wire would leak it.
    fields: fields.map<FieldOut>((f, index) => ({
      index,
      row: f.row,
      col: f.col,
      length: f.length,
      protected: f.protected,
      numeric: f.numeric,
      hidden: f.hidden,
      intensified: f.intensified,
      label: `F${index}`,
      value: f.hidden ? SENTINEL : f.value,
    })),
  }));

const focusPlanArb = fc.record({
  mode: fc.constantFrom('read', 'fill', 'key') as fc.Arbitrary<'read' | 'fill' | 'key'>,
  screen: screenArb,
  withAudit: fc.boolean(),
});

const outcomeArb = fc.constantFrom<ResolvedOutcome>(
  'approved', 'denied', 'expired', 'superseded', 'blocked_read_only', 'stale', 'error',
);

const confirmPlanArb = fc.option(
  fc.record({
    outcome: outcomeArb,
    superseded: fc.boolean(),
    screen: screenArb,
  }),
  { nil: null },
);

const callPlanArb = fc.record({
  kind: fc.constantFrom('business', 'generic') as fc.Arbitrary<'business' | 'generic'>,
  tool: fc.constantFrom('lookup_policy', 'read_screen', 'press_key'),
  steps: fc.array(focusPlanArb, { maxLength: 4 }),
  confirm: confirmPlanArb,
  status: fc.constantFrom('ok', 'error', 'pending') as fc.Arbitrary<'ok' | 'error' | 'pending'>,
});

const turnPlanArb = fc.record({
  thinking: fc.boolean(),
  calls: fc.array(callPlanArb, { maxLength: 3 }),
  deltas: fc.array(fc.string({ minLength: 1, maxLength: 12 }), { maxLength: 4 }),
  finalText: fc.option(fc.string({ maxLength: 30 }), { nil: null }),
  reason: fc.constantFrom('completed', 'cancelled', 'error', 'max_steps') as fc.Arbitrary<
    'completed' | 'cancelled' | 'error' | 'max_steps'
  >,
  finish: fc.boolean(),
});

type ValueOf<A> = A extends fc.Arbitrary<infer T> ? T : never;

type SegmentPlan =
  | { t: 'turn'; turn: ValueOf<typeof turnPlanArb> }
  | { t: 'audit' }
  | { t: 'error'; ref: boolean }
  | { t: 'state'; state: 'connected' | 'session_lost' | 'disconnected'; readOnly: boolean };

const segmentArb: fc.Arbitrary<SegmentPlan> = fc.oneof(
  { weight: 5, arbitrary: turnPlanArb.map((turn) => ({ t: 'turn' as const, turn })) },
  { weight: 1, arbitrary: fc.constant({ t: 'audit' as const }) },
  { weight: 1, arbitrary: fc.boolean().map((ref) => ({ t: 'error' as const, ref })) },
  {
    weight: 1,
    arbitrary: fc
      .record({
        state: fc.constantFrom('connected', 'session_lost', 'disconnected') as fc.Arbitrary<
          'connected' | 'session_lost' | 'disconnected'
        >,
        readOnly: fc.boolean(),
      })
      .map((x) => ({ t: 'state' as const, ...x })),
  },
);

/** Ids that must not collide across sessions' own counters are namespaced by the session id. */
export function buildSession(sessionId: string, segments: SegmentPlan[]): ServerEvent[] {
  const out: ServerEvent[] = [];
  let seq = 0;
  let turnN = 0;
  let callN = 0;
  let msgN = 0;
  let actN = 0;
  let auditN = 0;
  const push = (type: ServerEvent['type'], turn_id: string | null, data: unknown) => {
    seq += 1;
    out.push({
      v: 1,
      type,
      seq,
      ts: `2026-11-24T10:00:${String(seq % 60).padStart(2, '0')}.000Z`,
      session_id: sessionId,
      turn_id,
      data,
    } as ServerEvent);
  };
  const sessionData = (state: string, readOnly: boolean) => ({
    state,
    app_id: state === 'disconnected' ? null : 'fake-insurance',
    read_only: readOnly,
    confirm_mode: 'oob',
    llm: { provider: 'scripted', model: 'm', available: true },
    tools: { business: 3, generic: 4 },
    resync: false,
    controller: true,
  });
  const audit = (turn: string | null) => {
    auditN += 1;
    push('audit_entry', turn, {
      entry: {
        seq: auditN, ts: '2026-11-24T10:00:00.000000+00:00', tool: 'press_key', outcome: 'ok', screen_id: null,
        field: null, value: null, key: 'Enter', action_id: null, confirmed_by: 'n/a', detail: null,
        prev_hash: '0'.repeat(64), hash: String(auditN).padStart(64, '0'),
      },
    });
  };

  push('session_state', null, sessionData('connecting', false));
  push('session_state', null, sessionData('connected', false));

  for (const seg of segments) {
    if (seg.t === 'audit') audit(null);
    else if (seg.t === 'error') push('error', null, { code: 'bad_message', message: 'nope', recoverable: true, ref: seg.ref ? 'u_none' : null });
    else if (seg.t === 'state') push('session_state', null, sessionData(seg.state, seg.readOnly));
    else {
      turnN += 1;
      const turn = `t_${turnN}`;
      push('turn_started', turn, { user_message_id: `m_${++msgN}` });
      if (seg.turn.thinking) push('thinking', turn, { summary: 'thinking' });
      for (const call of seg.turn.calls) {
        const id = `c_${++callN}`;
        push('tool_call', turn, { tool_call_id: id, tool: call.tool, kind: call.kind, arguments: { x: 1 }, may_commit: null });
        call.steps.forEach((st, step) => {
          push('screen', turn, { phase: 'before', tool_call_id: id, screen: st.screen });
          push('field_focus', turn, {
            tool_call_id: id, step, mode: st.mode, screen_id: st.screen.screen_id, field_index: null,
            row: st.mode === 'fill' ? 3 : null, col: st.mode === 'fill' ? 5 : null, length: st.mode === 'fill' ? 4 : null,
            label: null, key: st.mode === 'key' ? 'Enter' : null,
          });
          if (st.withAudit) audit(turn);
          push('screen', turn, { phase: 'after', tool_call_id: id, screen: st.screen });
        });
        if (call.confirm) {
          const c = call.confirm;
          const a1 = `act_${++actN}`;
          const req = (action_id: string) =>
            push('confirmation_required', turn, {
              action_id, tool_call_id: id, screen_id: c.screen.screen_id, key: 'Enter', field_snapshot: [],
              expires_in_s: 300, read_only: false, agent_summary: 'agent words',
            });
          push('screen', turn, { phase: 'after', tool_call_id: id, screen: c.screen });
          req(a1);
          if (c.superseded) {
            const a2 = `act_${++actN}`;
            req(a2);
            push('confirmation_resolved', turn, { action_id: a1, outcome: 'superseded', confirmed_by: null, error_code: null });
            push('confirmation_resolved', turn, { action_id: a2, outcome: c.outcome, confirmed_by: null, error_code: null });
          } else {
            push('confirmation_resolved', turn, { action_id: a1, outcome: c.outcome, confirmed_by: null, error_code: null });
          }
        }
        push('tool_result', turn, {
          tool_call_id: id, status: call.status, error_code: null, summary: 's', result: null, truncated: false,
        });
      }
      const mid = `m_${++msgN}`;
      for (const d of seg.turn.deltas) push('assistant_delta', turn, { message_id: mid, text: d });
      if (seg.turn.finalText !== null) push('assistant_message', turn, { message_id: mid, text: seg.turn.finalText });
      if (seg.turn.finish) push('turn_finished', turn, { reason: seg.turn.reason, usage: null });
    }
  }
  return out;
}

export const sessionIdArb = fc.constantFrom('s_01', 's_02', 's_03');

/** A clean, gap-free stream for one session. */
export const cleanStreamArb = (sessionId = 's_01'): fc.Arbitrary<ServerEvent[]> =>
  fc.array(segmentArb, { maxLength: 6 }).map((segs) => buildSession(sessionId, segs));

// ---- mutations --------------------------------------------------------------

/** Insert copies of earlier events later in the stream. */
export const withDuplicates = (events: ServerEvent[]): fc.Arbitrary<ServerEvent[]> =>
  events.length === 0
    ? fc.constant(events)
    : fc
        .array(fc.tuple(fc.nat(events.length - 1), fc.nat(5)), { maxLength: 12 })
        .map((picks) => {
          const out = events.slice();
          for (const [src, back] of picks) {
            const copy = events[src] as ServerEvent;
            const at = Math.min(out.length, out.findIndex((e) => e === copy) + 1 + back);
            out.splice(at, 0, copy);
          }
          return out;
        });

/** Swap events that are at most 3 apart: reordering inside the resume window. */
export const withReordering = (events: ServerEvent[]): fc.Arbitrary<ServerEvent[]> =>
  events.length < 2
    ? fc.constant(events)
    : fc.array(fc.tuple(fc.nat(events.length - 2), fc.integer({ min: 1, max: 3 })), { maxLength: 12 }).map((swaps) => {
        const out = events.slice();
        for (const [i, d] of swaps) {
          const j = Math.min(out.length - 1, i + d);
          const t = out[i] as ServerEvent;
          out[i] = out[j] as ServerEvent;
          out[j] = t;
        }
        return out;
      });
