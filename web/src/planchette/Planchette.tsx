import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { FieldFocus } from '../protocol/types';
import {
  finish,
  initialScheduler,
  itemFromFocus,
  push,
  type SchedulerState,
  type Step,
} from './scheduler';
import { COLS, ROWS, rectCenter } from '../terminal/geometry';
import { strings } from '../strings';

/**
 * The ouija planchette (REQ-005). A lens/ring with a transparent centre that never covers the field text; it is
 * pointer-events:none and aria-hidden, because its meaning is announced in the chat. It reads the pure scheduler
 * for *what* to do and drives the Web Animations API for *how*. Reduced motion -> instant jumps, static ring.
 *
 * Positioning is in the grid's own coordinate space (1 unit = 1 cell), so it stays exact at any zoom: the parent
 * sets --cell-w and --line, and we translate by (col * cell-w, row * line).
 */

export interface PlanchetteProps {
  /** The reducer's focus queue (field_focus events with their seq). */
  queue: (FieldFocus & { seq: number })[];
  reduceMotion: boolean;
  /** Called with the highest seq that has been consumed (started), so the store can trim the queue. */
  onConsumed?: (seq: number) => void;
}

interface Placed {
  step: Step;
  label: string;
}

export function Planchette({ queue, reduceMotion, onConsumed }: PlanchetteProps) {
  const schedRef = useRef<SchedulerState>(initialScheduler());
  const lastSeqRef = useRef<number>(0);
  const elRef = useRef<HTMLDivElement | null>(null);
  const animRef = useRef<Animation | null>(null);
  const [placed, setPlaced] = useState<Placed | null>(null);

  // Feed new focus events into the scheduler, newest first by seq. This runs for every queue change.
  useEffect(() => {
    const fresh = queue.filter((f) => f.seq > lastSeqRef.current);
    if (fresh.length === 0) return;
    for (const f of fresh) {
      lastSeqRef.current = Math.max(lastSeqRef.current, f.seq);
      const item = itemFromFocus(f);
      if (!item) continue;
      const tr = push(schedRef.current, item, reduceMotion);
      schedRef.current = tr.state;
      if (tr.start) {
        setPlaced({ step: tr.start, label: labelFor(tr.start) });
        onConsumed?.(tr.start.item.seq);
      }
      for (const d of tr.dropped) onConsumed?.(d.seq);
    }
  }, [queue, reduceMotion, onConsumed]);

  // Drive the animation whenever a new step is placed.
  useLayoutEffect(() => {
    const el = elRef.current;
    if (!el || !placed) return;
    const to = rectCenter(placed.step.item.target.rect);
    const toTransform = translate(to.x, to.y);

    animRef.current?.cancel();

    if (placed.step.instant || placed.step.durationMs === 0) {
      el.style.transform = toTransform;
      onAnimationDone();
      return;
    }
    const from = placed.step.from ? rectCenter(placed.step.from) : to;
    const anim = el.animate(
      [{ transform: translate(from.x, from.y) }, { transform: toTransform }],
      { duration: placed.step.durationMs, easing: 'ease-out', fill: 'forwards' },
    );
    animRef.current = anim;
    const done = () => onAnimationDone();
    anim.addEventListener('finish', done, { once: true });
    anim.addEventListener('cancel', () => {}, { once: true });
    return () => anim.removeEventListener('finish', done);
    // onAnimationDone is stable via ref usage below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placed]);

  function onAnimationDone() {
    const tr = finish(schedRef.current, reduceMotion);
    schedRef.current = tr.state;
    if (tr.start) {
      setPlaced({ step: tr.start, label: labelFor(tr.start) });
      onConsumed?.(tr.start.item.seq);
      for (const d of tr.dropped) onConsumed?.(d.seq);
    }
  }

  useEffect(() => () => animRef.current?.cancel(), []);

  if (!placed) return null;
  const shape = placed.step.item.target.shape;
  const rect = placed.step.item.target.rect;

  return (
    <div
      ref={elRef}
      className={`planchette planchette-${placed.step.gesture}`}
      data-shape={shape}
      data-reduce={reduceMotion ? 'true' : 'false'}
      aria-hidden="true"
      style={{
        // size in cell units; the lens widens for a field sweep, is a ring for a settle, a pill on the key bar
        // a lens a little wider and taller than the field so it rings the text instead of sitting on it
        ['--p-w' as string]: shape === 'screen' ? COLS : Math.max(4, rect.w + 2),
        ['--p-h' as string]: shape === 'screen' ? ROWS : 1.9,
      }}
    >
      {shape === 'screen' ? (
        // the label travels inside the scan band so it never sits on the screen's title or fields
        <span className="planchette-scan">
          <span className="planchette-label">{placed.label}</span>
        </span>
      ) : (
        <span className="planchette-label">{placed.label}</span>
      )}
    </div>
  );
}

function translate(cx: number, cy: number): string {
  // Centre the element on the cell centre. Width/height are applied in CSS from --p-w/--p-h.
  return `translate(calc(${cx}ch - var(--p-w) * var(--cell-w) / 2), calc(${cy} * var(--line) - var(--p-h) * var(--line) / 2))`;
}

function labelFor(step: Step): string {
  const name = step.item.target.label?.trim().replace(/[=>\s]+$/, '') || null;
  switch (step.item.mode) {
    case 'read':
      return name ? strings.planchette.readingField(name) : strings.planchette.reading;
    case 'fill':
      return name ? strings.planchette.fillingField(name) : strings.planchette.filling;
    case 'key':
      return strings.planchette.pressing(step.item.target.key ?? '');
  }
}
