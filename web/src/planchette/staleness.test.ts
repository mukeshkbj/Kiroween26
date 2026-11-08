import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { finish, initialScheduler, isIdle, isStale, itemFromFocus, push, type FocusItem, type SchedulerState, type Step } from './scheduler';
import type { FieldFocus } from '../protocol/types';

/**
 * C-1 (integrator e2e 2026-11-06): the planchette must follow every target to the last one, and must never show a
 * step about a screen that is not on display. Properties over random interleavings of focus events, screen changes
 * and glide completions.
 */

const SCREENS = ['menu', 'enquiry', 'confirm'] as const;

type Op =
  | { k: 'focus'; mode: FieldFocus['mode']; screen: string; row: number }
  | { k: 'screen'; screen: string }
  | { k: 'finish' };

const opArb: fc.Arbitrary<Op> = fc.oneof(
  {
    weight: 4,
    arbitrary: fc.record({
      mode: fc.constantFrom('read', 'fill', 'key') as fc.Arbitrary<FieldFocus['mode']>,
      // '' models the empty screen_id a non-conforming server sends on step 0 (finding D-3)
      screen: fc.constantFrom(...SCREENS, ''),
      row: fc.integer({ min: 0, max: 23 }),
    }).map((x): Op => ({ k: 'focus', ...x })),
  },
  { weight: 2, arbitrary: fc.constantFrom(...SCREENS).map((screen): Op => ({ k: 'screen', screen })) },
  { weight: 3, arbitrary: fc.constant<Op>({ k: 'finish' }) },
);

const focus = (seq: number, mode: FieldFocus['mode'], screen: string, row: number): FieldFocus & { seq: number } => ({
  seq, tool_call_id: 'c', step: seq, mode, screen_id: screen, field_index: mode === 'fill' ? 1 : null,
  row: mode === 'fill' ? row : null, col: mode === 'fill' ? 10 : null, length: mode === 'fill' ? 8 : null,
  label: mode === 'fill' ? `F${row}` : null, key: mode === 'key' ? 'Enter' : null,
});

interface Run {
  pushed: FocusItem[];
  started: { step: Step; screenAtStart: string | null }[];
  dropped: FocusItem[];
  final: SchedulerState;
  screen: string | null;
  violations: string[];
}

function simulate(ops: Op[], reduceMotion: boolean): Run {
  let state = initialScheduler();
  let screen: string | null = null;
  let seq = 0;
  const r: Run = { pushed: [], started: [], dropped: [], final: state, screen, violations: [] };
  const take = (tr: ReturnType<typeof push>) => {
    if (tr.start) {
      if (isStale(tr.start.item, screen)) r.violations.push(`started stale seq ${tr.start.item.seq} on ${screen}`);
      r.started.push({ step: tr.start, screenAtStart: screen });
    }
    r.dropped.push(...tr.dropped);
    state = tr.state;
    if (state.inFlight && state.inFlight !== tr.start && tr.start) r.violations.push('in flight is not the started step');
  };
  for (const op of ops) {
    if (op.k === 'focus') {
      const item = itemFromFocus(focus(++seq, op.mode, op.screen, op.row));
      if (!item) continue;
      r.pushed.push(item);
      take(push(state, item, reduceMotion, screen));
    } else if (op.k === 'screen') {
      screen = op.screen;
      // the component reacts to a screen change by finishing a step that became stale
      if (state.inFlight && isStale(state.inFlight.item, screen)) take(finish(state, reduceMotion, screen));
    } else {
      take(finish(state, reduceMotion, screen));
    }
  }
  for (let g = 0; g < 200 && !isIdle(state); g++) take(finish(state, reduceMotion, screen));
  r.final = state;
  r.screen = screen;
  return r;
}

describe('staleness (C-1)', () => {
  it('a step is never started while it is about a screen other than the one on display', () => {
    fc.assert(
      fc.property(fc.array(opArb, { maxLength: 60 }), fc.boolean(), (ops, rm) => {
        expect(simulate(ops, rm).violations).toEqual([]);
      }),
      { numRuns: 500 },
    );
  });

  it('every pushed event is started or dropped exactly once, starts keep seq order, and the queue drains', () => {
    fc.assert(
      fc.property(fc.array(opArb, { maxLength: 60 }), fc.boolean(), (ops, rm) => {
        const r = simulate(ops, rm);
        const s = r.started.map((x) => x.step.item.seq);
        const d = r.dropped.map((x) => x.seq);
        expect([...s, ...d].sort((a, b) => a - b)).toEqual(r.pushed.map((i) => i.seq));
        expect(s).toEqual([...s].sort((a, b) => a - b));
        expect(isIdle(r.final)).toBe(true);
      }),
      { numRuns: 500 },
    );
  });

  it('it follows to the last event: if the newest event is fresh when the queue drains, it is the last one shown', () => {
    fc.assert(
      fc.property(fc.array(opArb, { maxLength: 60 }), (ops) => {
        // no screen changes after the last focus, so "fresh at the end" is well defined
        const lastFocus = ops.map((o) => o.k).lastIndexOf('focus');
        fc.pre(lastFocus >= 0);
        const trimmed = ops.slice(0, lastFocus + 1);
        const r = simulate(trimmed, false);
        const newest = r.pushed[r.pushed.length - 1] as FocusItem;
        if (!isStale(newest, r.screen)) {
          expect(r.started[r.started.length - 1]?.step.item.seq).toBe(newest.seq);
        }
      }),
      { numRuns: 500 },
    );
  });

  it('a field focus with an empty screen id is never shown (it cannot be verified on screen); reads and keys still are', () => {
    const f = itemFromFocus(focus(1, 'fill', '', 5)) as FocusItem;
    const k = itemFromFocus(focus(2, 'key', '', 0)) as FocusItem;
    const rd = itemFromFocus(focus(3, 'read', '', 0)) as FocusItem;
    expect(isStale(f, 'menu')).toBe(true);
    expect(isStale(k, 'menu')).toBe(false);
    expect(isStale(rd, 'menu')).toBe(false);
    expect(isStale(f, undefined)).toBe(false); // rule disabled
  });

  it("the integrator's exact sequence: read, fill OPTION (menu), Enter, fill POLNO (enquiry), Enter, all arriving together after the enquiry screen", () => {
    const evs = [
      focus(11, 'read', '', 0),
      { ...focus(15, 'fill', 'menu', 7), col: 15, length: 1, label: 'OPTION ===>' },
      focus(18, 'key', 'menu', 0),
      { ...focus(21, 'fill', 'enquiry', 3), col: 13, length: 8, label: 'POLNO ===>' },
      focus(24, 'key', 'enquiry', 0),
    ];
    let state = initialScheduler();
    const shown: string[] = [];
    const take = (tr: ReturnType<typeof push>) => {
      state = tr.state;
      if (tr.start) shown.push(`${tr.start.item.mode}:${tr.start.item.target.label ?? tr.start.item.target.key ?? ''}`);
    };
    // the read starts on the menu, then everything else arrives while the enquiry screen is already on display
    take(push(state, itemFromFocus(evs[0]!)!, false, 'menu'));
    for (const e of evs.slice(1)) take(push(state, itemFromFocus(e)!, false, 'enquiry'));
    for (let g = 0; g < 10 && !isIdle(state); g++) take(finish(state, false, 'enquiry'));
    expect(shown).toEqual(['read:', 'fill:POLNO ===>', 'key:Enter']);
    expect(shown).not.toContain('fill:OPTION ===>');
  });
});
