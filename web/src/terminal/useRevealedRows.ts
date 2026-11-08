import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { COLS, fieldRects } from './geometry';
import { MAX_REVEAL_MS, revealedCount } from './typing';

/**
 * Typing reveal (REQ-006) wired to the screen. When a new screen arrives right after a `fill` focus, the new
 * characters of that field appear progressively (at most MAX_REVEAL_MS). The rows stay the ground truth: we only
 * blank the not-yet-revealed tail of that one field in a copy. Skipped entirely under reduced motion or when more
 * focus events are queued, and never run for a field whose text did not change.
 */

export interface FillHint {
  seq: number;
  row: number;
  col: number;
  length: number;
}

export interface RevealOptions {
  reduceMotion: boolean;
  /** More planchette moves are waiting: do not make the user wait for typing. */
  skip: boolean;
  now?: () => number;
  raf?: (cb: () => void) => number;
  cancelRaf?: (id: number) => void;
}

interface Active {
  row: number;
  col: number;
  length: number;
  startedAt: number;
}

const cellText = (rows: string[], row: number, col: number, len: number) => (rows[row] ?? '').padEnd(COLS, ' ').slice(col, col + len);

export function useRevealedRows(rows: string[], fill: FillHint | null, o: RevealOptions): string[] {
  const now = o.now ?? (() => performance.now());
  const raf = o.raf ?? ((cb: () => void) => window.requestAnimationFrame(() => cb()));
  const cancelRaf = o.cancelRaf ?? ((id: number) => window.cancelAnimationFrame(id));

  const prevRows = useRef(rows);
  const handled = useRef(0);
  const [active, setActive] = useState<Active | null>(null);
  const [, setTick] = useState(0);
  const rafId = useRef<number | null>(null);

  useLayoutEffect(() => {
    const before = prevRows.current;
    prevRows.current = rows;
    if (!fill || fill.seq <= handled.current || before === rows) return;
    handled.current = fill.seq;
    if (o.reduceMotion || o.skip) return;
    const first = fieldRects({ row: fill.row, col: fill.col, length: fill.length })[0];
    if (!first) return;
    const next = cellText(rows, first.y, first.x, first.w);
    const prev = cellText(before, first.y, first.x, first.w);
    if (next === prev || next.trim() === '') return; // nothing new to type
    setActive({ row: first.y, col: first.x, length: first.w, startedAt: now() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  useEffect(() => {
    if (!active) return;
    const step = () => {
      if (now() - active.startedAt >= MAX_REVEAL_MS) {
        setActive(null);
        return;
      }
      setTick((t) => t + 1);
      rafId.current = raf(step);
    };
    rafId.current = raf(step);
    return () => {
      if (rafId.current !== null) cancelRaf(rafId.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Turning reduced motion on, or queueing more moves, finishes any reveal at once.
  useEffect(() => {
    if ((o.reduceMotion || o.skip) && active) setActive(null);
  }, [o.reduceMotion, o.skip, active]);

  if (!active) return rows;
  const shown = revealedCount(active.length, now() - active.startedAt, false);
  if (shown >= active.length) return rows;
  const copy = rows.slice();
  const line = (copy[active.row] ?? '').padEnd(COLS, ' ');
  copy[active.row] = line.slice(0, active.col + shown) + ' '.repeat(active.length - shown) + line.slice(active.col + active.length);
  return copy;
}
