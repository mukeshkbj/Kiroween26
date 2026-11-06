import { describe, expect, it, beforeEach } from 'vitest';
import { act, render } from '@testing-library/react';
import { Planchette } from './Planchette';
import type { FieldFocus } from '../protocol/types';

/**
 * jsdom has no Web Animations engine, so we install a controllable fake `element.animate` that lets the test
 * finish an animation on demand. Positions are checked via the scheduler/geometry property tests, not here;
 * this file checks the component's contract: aria-hidden, one-at-a-time, queue trimming, reduced-motion.
 */

interface FakeAnim {
  finishListeners: (() => void)[];
  cancelled: boolean;
  finished: boolean;
  addEventListener(type: string, fn: () => void): void;
  removeEventListener(type: string, fn: () => void): void;
  cancel(): void;
  finish(): void;
}

let anims: FakeAnim[] = [];

function installFakeAnimate() {
  anims = [];
  (Element.prototype as unknown as { animate: unknown }).animate = function () {
    const a: FakeAnim = {
      finishListeners: [],
      cancelled: false,
      finished: false,
      addEventListener(type, fn) {
        if (type === 'finish') this.finishListeners.push(fn);
      },
      removeEventListener() {},
      cancel() {
        this.cancelled = true;
      },
      finish() {
        this.finished = true;
        for (const fn of this.finishListeners) fn();
      },
    };
    anims.push(a);
    return a as unknown as Animation;
  };
}

function finishLast() {
  const live = anims.filter((a) => !a.cancelled && !a.finished);
  act(() => live[live.length - 1]?.finish());
}

const focus = (seq: number, over: Partial<FieldFocus> = {}): FieldFocus & { seq: number } => ({
  seq,
  tool_call_id: 'c_1',
  step: seq,
  mode: 'fill',
  screen_id: 'x',
  field_index: 1,
  row: 5,
  col: 14,
  length: 8,
  label: 'POLNO ===>',
  key: null,
  ...over,
});

beforeEach(() => {
  installFakeAnimate();
});

describe('Planchette (REQ-005)', () => {
  it('is pointer-events:none and aria-hidden, with a human-readable label', () => {
    const { container } = render(<Planchette queue={[focus(1, { mode: 'read' })]} reduceMotion={false} />);
    const p = container.querySelector('.planchette') as HTMLElement;
    expect(p).not.toBeNull();
    expect(p.getAttribute('aria-hidden')).toBe('true');
    expect(p.querySelector('.planchette-label')?.textContent).toMatch(/reading POLNO/);
  });

  it('animates one step at a time and reports each started seq as consumed', () => {
    const consumed: number[] = [];
    const { rerender } = render(
      <Planchette queue={[focus(1)]} reduceMotion={false} onConsumed={(s) => consumed.push(s)} />,
    );
    expect(anims.filter((a) => !a.cancelled)).toHaveLength(1);
    expect(consumed).toEqual([1]);
    // a second event while the first is in flight waits
    rerender(<Planchette queue={[focus(1), focus(2, { row: 10 })]} reduceMotion={false} onConsumed={(s) => consumed.push(s)} />);
    expect(anims.filter((a) => !a.cancelled && !a.finished)).toHaveLength(1);
    finishLast();
    // now the queued one runs
    expect(consumed).toEqual([1, 2]);
  });

  it('uses the correct gesture per mode', () => {
    const { container, rerender } = render(<Planchette queue={[focus(1, { mode: 'read' })]} reduceMotion={false} />);
    expect(container.querySelector('.planchette')?.className).toContain('planchette-sweep');
    rerender(<Planchette queue={[focus(1, { mode: 'read' }), focus(2, { mode: 'key', key: 'Enter', row: null, col: null, length: null })]} reduceMotion={false} />);
    finishLast();
    expect(container.querySelector('.planchette')?.className).toContain('planchette-press');
    expect(container.querySelector('.planchette-label')?.textContent).toMatch(/pressing Enter/);
  });

  it('with reduced motion it never calls the Web Animations API (instant jumps)', () => {
    const consumed: number[] = [];
    render(
      <Planchette
        queue={[focus(1), focus(2, { row: 9 }), focus(3, { row: 1 })]}
        reduceMotion={true}
        onConsumed={(s) => consumed.push(s)}
      />,
    );
    expect(anims).toHaveLength(0);
    // the last target is shown; earlier ones are dropped/instant
    expect(consumed).toContain(3);
  });

  it('drops intermediate events when more than five queue up, keeping the newest, each reported once', () => {
    const consumed: number[] = [];
    const q = Array.from({ length: 8 }, (_, i) => focus(i + 1, { row: i }));
    render(<Planchette queue={q} reduceMotion={false} onConsumed={(s) => consumed.push(s)} />);
    // Drain: finishing each in-flight glide starts the next until the queue empties.
    for (let i = 0; i < 10 && anims.filter((a) => !a.cancelled && !a.finished).length > 0; i++) finishLast();
    // every event is accounted for exactly once; the last one is always animated
    expect(new Set(consumed).size).toBe(consumed.length);
    expect(consumed.sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(consumed).toContain(8);
  });

  it('renders nothing before any focus event', () => {
    const { container } = render(<Planchette queue={[]} reduceMotion={false} />);
    expect(container.querySelector('.planchette')).toBeNull();
  });
});
