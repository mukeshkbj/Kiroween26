import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import { Planchette, FINISH_SLACK_MS, REST_MS } from './Planchette';
import { MAX_MS } from './scheduler';
import type { FieldFocus } from '../protocol/types';

/**
 * C-1 component tests (integrator request-c-e2e-findings.md, 2026-11-06). In the live run the agent sent, within a few
 * milliseconds: read (no position), fill OPTION (7,15) on the menu, key Enter, fill POLNO (3,13) on the enquiry
 * screen, key Enter. The planchette ended "filling OPTION" over the enquiry screen. These tests replay that sequence
 * with fake timers.
 *
 * `animate` here NEVER fires `finish` unless a test says so: the worst case (a throttled or background tab). Only the
 * fallback timer can move the planchette on. A second suite fires `finish` normally.
 */

const MENU = 'ba02cc6364b6cd8728535a7085dc51abac5bd83c32a02163d91634aa6bb97271';
const ENQ = '419888f22df6bc184e84af5f6a22ce8966b85e028e3919b6be7218de22dd5080';

type F = FieldFocus & { seq: number };
const ev = (seq: number, mode: F['mode'], screen_id: string, over: Partial<F> = {}): F => ({
  seq, tool_call_id: 'c_01', step: seq, mode, screen_id, field_index: null, row: null, col: null, length: null,
  label: null, key: null, ...over,
});
// The live sequence, exactly as probed (screen_id is '' on the first event: finding D-3).
const READ = ev(11, 'read', '');
const OPTION = ev(15, 'fill', MENU, { field_index: 1, row: 7, col: 15, length: 1, label: 'OPTION ===>' });
const ENTER1 = ev(18, 'key', MENU, { key: 'Enter' });
const POLNO = ev(21, 'fill', ENQ, { field_index: 1, row: 3, col: 13, length: 8, label: 'POLNO ===>' });
const ENTER2 = ev(24, 'key', ENQ, { key: 'Enter' });

interface FakeAnim { listeners: (() => void)[]; cancelled: boolean; finish(): void }
let anims: FakeAnim[] = [];
let autoFinish = false;

beforeEach(() => {
  vi.useFakeTimers();
  anims = [];
  autoFinish = false;
  (Element.prototype as unknown as { animate: unknown }).animate = function (_k: unknown, opts: { duration: number }) {
    const a: FakeAnim = {
      listeners: [],
      cancelled: false,
      finish() {
        for (const l of this.listeners) l();
      },
    };
    anims.push(a);
    // with autoFinish the browser delivers `finish` on time (well before the fallback)
    if (autoFinish) setTimeout(() => !a.cancelled && a.finish(), opts.duration);
    return {
      addEventListener: (t: string, fn: () => void) => t === 'finish' && a.listeners.push(fn),
      removeEventListener: (_t: string, fn: () => void) => (a.listeners = a.listeners.filter((x) => x !== fn)),
      cancel: () => (a.cancelled = true),
      finish: () => a.finish(),
    } as unknown as Animation;
  };
});
afterEach(() => {
  vi.useRealTimers();
});

const label = (c: HTMLElement) => c.querySelector('.planchette-label')?.textContent ?? null;
const advance = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

function mount(props: { queue: F[]; screen: string | null; turnActive?: boolean }) {
  const consumed: number[] = [];
  const view = render(
    <Planchette queue={props.queue} reduceMotion={false} currentScreenId={props.screen} turnActive={props.turnActive ?? true} onConsumed={(s) => consumed.push(s)} />,
  );
  const rerender = (p: { queue: F[]; screen: string | null; turnActive?: boolean }) =>
    view.rerender(
      <Planchette queue={p.queue} reduceMotion={false} currentScreenId={p.screen} turnActive={p.turnActive ?? true} onConsumed={(s) => consumed.push(s)} />,
    );
  return { ...view, rerender, consumed };
}

describe.each([
  ['finish events never arrive (fallback timer only)', false],
  ['finish events arrive on time', true],
])('C-1 live sequence: %s', (_name, finishes) => {
  beforeEach(() => {
    autoFinish = finishes;
  });

  it('ends on POLNO / Enter, never shows OPTION over the enquiry screen, and consumes every event once', () => {
    // the read begins on the menu...
    const h = mount({ queue: [READ], screen: MENU });
    expect(label(h.container)).toMatch(/reading/);
    // ...then the rest of the tool call arrives together, by which time the enquiry screen is shown
    h.rerender({ queue: [READ, OPTION, ENTER1, POLNO, ENTER2], screen: ENQ });
    const seen: (string | null)[] = [label(h.container)];
    for (let i = 0; i < 10; i++) {
      advance(MAX_MS + FINISH_SLACK_MS + 1);
      seen.push(label(h.container));
    }
    expect(seen).toContain('filling POLNO');
    expect(seen).not.toContain('filling OPTION');
    expect(seen.filter((s) => s !== null).at(-1)).toBe('pressing Enter');
    expect(h.container.querySelector('.planchette')?.getAttribute('data-seq')).toBe('24');
    expect([...h.consumed].sort((a, b) => a - b)).toEqual([11, 15, 18, 21, 24]);
    expect(new Set(h.consumed).size).toBe(5);
  });

  it('with everything arriving before the screen changes, OPTION may show, but the planchette still ends on the last target', () => {
    const h = mount({ queue: [READ, OPTION, ENTER1], screen: MENU });
    h.rerender({ queue: [READ, OPTION, ENTER1, POLNO, ENTER2], screen: ENQ });
    for (let i = 0; i < 10; i++) advance(MAX_MS + FINISH_SLACK_MS + 1);
    expect(h.container.querySelector('.planchette')?.getAttribute('data-seq')).toBe('24');
  });

  it('a later screen with another screen_id clears a field label at once', () => {
    const h = mount({ queue: [POLNO], screen: ENQ });
    expect(label(h.container)).toBe('filling POLNO');
    h.rerender({ queue: [POLNO], screen: MENU }); // e.g. PF3 back to the menu
    expect(label(h.container)).toBeNull();
    expect(h.container.querySelector('.planchette')).toBeNull();
  });

  it('comes to rest (hidden) once the turn has finished and nothing is pending, after a short hold', () => {
    const h = mount({ queue: [POLNO], screen: ENQ });
    advance(MAX_MS + FINISH_SLACK_MS + 1); // the glide is over
    h.rerender({ queue: [POLNO], screen: ENQ, turnActive: false });
    expect(label(h.container)).toBe('filling POLNO'); // held so the user sees where it landed
    advance(REST_MS + 1);
    expect(h.container.querySelector('.planchette')).toBeNull();
  });

  it('the real order: the turn ends while the last glide is still moving, and it rests once that glide is done', () => {
    // live: turn_finished at +299 ms, last glide over at about +1.8 s. Ending the turn first must still lead to rest.
    const h = mount({ queue: [POLNO, ENTER2], screen: ENQ, turnActive: true });
    h.rerender({ queue: [POLNO, ENTER2], screen: ENQ, turnActive: false }); // turn over, glides still pending
    expect(label(h.container)).toBe('filling POLNO');
    for (let i = 0; i < 40 && label(h.container) !== 'pressing Enter'; i++) advance(50); // POLNO's glide runs out
    expect(label(h.container)).toBe('pressing Enter');
    advance(MAX_MS + FINISH_SLACK_MS + 1); // the last glide is over: nothing in flight, nothing queued
    expect(label(h.container)).toBe('pressing Enter'); // landed, and held so the user sees where
    advance(REST_MS + 1);
    expect(h.container.querySelector('.planchette')).toBeNull();
  });

  it('does not rest while the turn is still running, and comes back for the next event after resting', () => {
    const h = mount({ queue: [POLNO], screen: ENQ, turnActive: true });
    advance(MAX_MS + FINISH_SLACK_MS + REST_MS * 3);
    expect(label(h.container)).toBe('filling POLNO');
    h.rerender({ queue: [POLNO], screen: ENQ, turnActive: false });
    advance(REST_MS + 1);
    expect(h.container.querySelector('.planchette')).toBeNull();
    h.rerender({ queue: [POLNO, ENTER2], screen: ENQ, turnActive: true });
    expect(label(h.container)).toBe('pressing Enter');
  });
});

describe('the fallback never double-finishes', () => {
  it('finish event and fallback timer both firing advance by one step only', () => {
    autoFinish = false;
    const A = ev(1, 'fill', ENQ, { row: 3, col: 13, length: 8, label: 'A' });
    const B = ev(2, 'fill', ENQ, { row: 5, col: 13, length: 8, label: 'B' });
    const C = ev(3, 'fill', ENQ, { row: 7, col: 13, length: 8, label: 'C' });
    const consumed: number[] = [];
    const { container } = render(<Planchette queue={[A, B, C]} reduceMotion={false} currentScreenId={ENQ} turnActive onConsumed={(s) => consumed.push(s)} />);
    expect(label(container)).toBe('filling A');
    act(() => anims[0]!.finish()); // the browser's finish...
    expect(label(container)).toBe('filling B');
    advance(MAX_MS + FINISH_SLACK_MS + 1); // ...and A's fallback timer must not skip B (it was cleared)
    // B's own fallback fired in that same window, so C is now showing; what must not happen is skipping straight past C
    expect(label(container)).toBe('filling C');
    expect(consumed).toEqual([1, 2, 3]);
  });
});
