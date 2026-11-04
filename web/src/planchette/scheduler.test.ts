import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import {
  MAX_MS,
  MAX_QUEUE,
  MIN_MS,
  durationFor,
  finish,
  initialScheduler,
  itemFromFocus,
  push,
  schedule,
  type FocusItem,
  type SchedulerState,
  type Step,
} from './scheduler';
import { STAGE, rectContains } from '../terminal/geometry';
import type { FieldFocus } from '../protocol/types';

const focusArb = fc
  .record({
    mode: fc.constantFrom('read', 'fill', 'key') as fc.Arbitrary<FieldFocus['mode']>,
    row: fc.integer({ min: 0, max: 23 }),
    col: fc.integer({ min: 1, max: 79 }),
    length: fc.integer({ min: 1, max: 20 }),
    key: fc.constantFrom('Enter', 'Clear', 'PF3', 'PF8'),
  })
  .map<Omit<FieldFocus, 'tool_call_id'>>((r) => ({
    step: 0,
    mode: r.mode,
    screen_id: 'x',
    field_index: null,
    row: r.mode === 'key' ? null : r.row,
    col: r.mode === 'key' ? null : r.col,
    length: r.mode === 'key' ? null : r.length,
    label: null,
    key: r.mode === 'key' ? r.key : null,
  }));

type Op = { k: 'push'; focus: Omit<FieldFocus, 'tool_call_id'>; reduce: boolean } | { k: 'finish'; reduce: boolean };

const opsArb = (reduceFixed: boolean | null): fc.Arbitrary<Op[]> =>
  fc.array(
    fc.oneof(
      { weight: 3, arbitrary: fc.record({ focus: focusArb, reduce: fc.boolean() }).map((x): Op => ({ k: 'push', focus: x.focus, reduce: reduceFixed ?? x.reduce })) },
      { weight: 2, arbitrary: fc.boolean().map((reduce): Op => ({ k: 'finish', reduce: reduceFixed ?? reduce })) },
    ),
    { maxLength: 60 },
  );

interface Trace {
  pushed: FocusItem[];
  started: Step[];
  dropped: FocusItem[];
  final: SchedulerState;
  maxQueue: number;
  violations: string[];
}

function simulate(ops: Op[], drainReduce: boolean): Trace {
  let state = initialScheduler();
  const t: Trace = { pushed: [], started: [], dropped: [], final: state, maxQueue: 0, violations: [] };
  let seq = 0;
  const apply = (tr: ReturnType<typeof push>, before: SchedulerState, finishing: boolean) => {
    if (tr.start) {
      // A push may only start a step when nothing was in flight (at most one animation at a time).
      if (before.inFlight && !finishing) t.violations.push('started while another was in flight');
      // After a start, the only thing in flight is that step (or nothing, when it was instant).
      if (tr.state.inFlight && tr.state.inFlight !== tr.start) t.violations.push('in flight is not the started step');
      t.started.push(tr.start);
    }
    t.dropped.push(...tr.dropped);
    state = tr.state;
    t.maxQueue = Math.max(t.maxQueue, state.queue.length);
  };
  for (const op of ops) {
    if (op.k === 'push') {
      seq += 1;
      const item = itemFromFocus({ ...op.focus, tool_call_id: 'c', seq });
      if (!item) continue;
      t.pushed.push(item);
      apply(push(state, item, op.reduce), state, false);
    } else {
      apply(finish(state, op.reduce), state, true);
    }
  }
  // Drain: the driver keeps reporting finished glides until nothing is left.
  for (let guard = 0; guard < 1000 && (state.inFlight || state.queue.length > 0); guard++) {
    apply(finish(state, drainReduce), state, true);
  }
  t.final = state;
  return t;
}

describe('planchette scheduler properties (REQ-027)', () => {
  it('every pushed event is either animated/started or dropped, exactly once, in order, ending with the last', () => {
    fc.assert(
      fc.property(opsArb(null), fc.boolean(), (ops, drainReduce) => {
        const t = simulate(ops, drainReduce);
        expect(t.violations).toEqual([]);
        const startedSeq = t.started.map((s) => s.item.seq);
        const droppedSeq = t.dropped.map((i) => i.seq);
        // partition: started ∪ dropped = pushed, disjoint
        expect([...startedSeq, ...droppedSeq].sort((a, b) => a - b)).toEqual(t.pushed.map((i) => i.seq));
        // order preserved: started targets are a subsequence of the pushes
        expect(startedSeq).toEqual([...startedSeq].sort((a, b) => a - b));
        // ends with the last event
        if (t.pushed.length > 0) expect(startedSeq[startedSeq.length - 1]).toBe(t.pushed[t.pushed.length - 1]?.seq);
        // fully drained
        expect(t.final.queue).toEqual([]);
        expect(t.final.inFlight).toBeNull();
      }),
      { numRuns: 400 },
    );
  });

  it('the waiting queue never exceeds MAX_QUEUE', () => {
    fc.assert(
      fc.property(opsArb(false), (ops) => {
        expect(simulate(ops, false).maxQueue).toBeLessThanOrEqual(MAX_QUEUE);
      }),
      { numRuns: 300 },
    );
  });

  it('with reduced motion nothing is ever animated: zero animated steps, zero duration, nothing in flight', () => {
    fc.assert(
      fc.property(opsArb(true), (ops) => {
        const t = simulate(ops, true);
        expect(t.started.filter((s) => !s.instant)).toHaveLength(0);
        for (const s of t.started) expect(s.durationMs).toBe(0);
        expect(t.final.inFlight).toBeNull();
        if (t.pushed.length > 0) {
          expect(t.started[t.started.length - 1]?.item.seq).toBe(t.pushed[t.pushed.length - 1]?.seq);
        }
      }),
      { numRuns: 300 },
    );
  });

  it('animated steps last between MIN_MS and MAX_MS and start from where the previous one landed', () => {
    fc.assert(
      fc.property(opsArb(false), (ops) => {
        const t = simulate(ops, false);
        let prevLanded: FocusItem | null = null;
        for (const s of t.started) {
          expect(s.instant).toBe(false);
          expect(s.durationMs).toBeGreaterThanOrEqual(MIN_MS);
          expect(s.durationMs).toBeLessThanOrEqual(MAX_MS);
          expect(rectContains(STAGE, s.item.target.rect)).toBe(true);
          if (prevLanded) expect(s.from).toEqual(prevLanded.target.rect);
          else expect(s.from).toBeNull();
          prevLanded = s.item;
        }
      }),
      { numRuns: 300 },
    );
  });

  it('more than MAX_QUEUE queued behind a glide drops all but the newest', () => {
    const items = Array.from({ length: 9 }, (_, i) =>
      itemFromFocus({
        step: i, mode: 'fill', screen_id: 'x', field_index: null, row: i, col: 3, length: 4, label: null, key: null,
        tool_call_id: 'c', seq: i + 1,
      }) as FocusItem,
    );
    let state = initialScheduler();
    const started: number[] = [];
    const dropped: number[] = [];
    for (const it of items) {
      const tr = push(state, it, false);
      state = tr.state;
      if (tr.start) started.push(tr.start.item.seq);
      dropped.push(...tr.dropped.map((d) => d.seq));
    }
    expect(started).toEqual([1]); // the first glide is in flight
    expect(dropped.length).toBeGreaterThan(0);
    expect(state.queue.at(-1)?.seq).toBe(9);
    expect(state.queue.length).toBeLessThanOrEqual(MAX_QUEUE);
  });
});

describe('schedule() plan', () => {
  const mk = (n: number): FocusItem[] =>
    Array.from({ length: n }, (_, i) =>
      itemFromFocus({
        step: i, mode: 'read', screen_id: 'x', field_index: null, row: i, col: 2, length: 5, label: null, key: null,
        tool_call_id: 'c', seq: i + 1,
      }) as FocusItem,
    );

  it('plays in order when the queue is short', () => {
    const r = schedule(mk(3), false);
    expect(r.current?.item.seq).toBe(1);
    expect(r.next.map((i) => i.seq)).toEqual([2, 3]);
    expect(r.dropped).toEqual([]);
  });

  it('keeps only the newest when the queue is long', () => {
    const r = schedule(mk(8), false);
    expect(r.current?.item.seq).toBe(8);
    expect(r.dropped.map((i) => i.seq)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it('is instant under reduced motion', () => {
    const r = schedule(mk(3), true);
    expect(r.current?.instant).toBe(true);
    expect(r.current?.item.seq).toBe(3);
    expect(r.next).toEqual([]);
  });

  it('empty queue plans nothing', () => {
    expect(schedule([], false)).toEqual({ current: null, next: [], dropped: [] });
  });
});

describe('durationFor', () => {
  it('is clamped and monotone in distance', () => {
    const a = { x: 0, y: 0, w: 1, h: 1 };
    expect(durationFor(null, a)).toBe(MIN_MS);
    expect(durationFor(a, a)).toBe(MIN_MS);
    expect(durationFor(a, { x: 79, y: 23, w: 1, h: 1 })).toBe(MAX_MS);
    expect(durationFor(a, { x: 20, y: 0, w: 1, h: 1 })).toBeLessThanOrEqual(durationFor(a, { x: 40, y: 0, w: 1, h: 1 }));
  });
});
