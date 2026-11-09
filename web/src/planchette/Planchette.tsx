import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { FieldFocus } from '../protocol/types';
import {
  finish,
  initialScheduler,
  isIdle,
  isStale,
  itemFromFocus,
  push,
  type SchedulerState,
  type ScreenRef,
  type Step,
  type Transition,
} from './scheduler';
import { COLS, ROWS, rectCenter } from '../terminal/geometry';
import { strings } from '../strings';

/**
 * The ouija planchette (REQ-005). A lens/ring with a transparent centre that never covers the field text; it is
 * pointer-events:none and aria-hidden, because its meaning is announced in the chat. It reads the pure scheduler
 * for *what* to do and drives the Web Animations API for *how*. Reduced motion -> instant jumps, static ring.
 *
 * Live-mode rules (C-1, 2026-11-06):
 *  - it follows every event to the last one; steps about a screen that is no longer shown are skipped (scheduler);
 *  - a glide whose `finish` event never arrives (throttled or hidden tab) cannot stall the chain: a timer finishes it;
 *  - if the screen changes under a field it is naming, the label goes at once (never name a field that is not shown);
 *  - when the turn is over and nothing is pending it comes to rest (is hidden) after a short hold.
 *
 * Positioning is in the grid's own coordinate space (1 unit = 1 cell), so it stays exact at any zoom.
 */

export interface PlanchetteProps {
  /** The reducer's focus queue (field_focus events with their seq). */
  queue: (FieldFocus & { seq: number })[];
  reduceMotion: boolean;
  /** Called with each seq the planchette is done with (started or skipped), so the store can trim the queue. */
  onConsumed?: (seq: number) => void;
  /** The screen on display. `undefined` disables the staleness rule (component tests of ordering only). */
  currentScreenId?: ScreenRef;
  /** A turn is running. `undefined` means "unknown": never rest automatically. */
  turnActive?: boolean;
  /** How long it stays visible after the last step of a finished turn. */
  restMs?: number;
}

/** Extra time past the planned duration before the fallback timer finishes a glide. */
export const FINISH_SLACK_MS = 250;
export const REST_MS = 900;

interface Placed {
  step: Step;
  label: string;
}

export function Planchette({ queue, reduceMotion, onConsumed, currentScreenId, turnActive, restMs = REST_MS }: PlanchetteProps) {
  const schedRef = useRef<SchedulerState>(initialScheduler());
  const lastSeqRef = useRef<number>(0);
  const elRef = useRef<HTMLDivElement | null>(null);
  const animRef = useRef<Animation | null>(null);
  const fallbackRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const restRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [placed, setPlaced] = useState<Placed | null>(null);
  // Bumped whenever the scheduler drains to idle. The turn usually ends BEFORE the last glide does, and a glide
  // finishing changes neither the turn flag nor the placed step, so the rest rule needs its own signal (found live).
  const [idleTick, setIdleTick] = useState(0);

  // Latest values for callbacks that outlive a render (animation listeners, timers).
  const screenRef = useRef<ScreenRef>(currentScreenId);
  screenRef.current = currentScreenId;
  const reduceRef = useRef(reduceMotion);
  reduceRef.current = reduceMotion;
  const consumedRef = useRef(onConsumed);
  consumedRef.current = onConsumed;

  const clearFallback = () => {
    if (fallbackRef.current) clearTimeout(fallbackRef.current);
    fallbackRef.current = null;
  };
  const clearRest = () => {
    if (restRef.current) clearTimeout(restRef.current);
    restRef.current = null;
  };

  /** Apply a scheduler transition: report consumed items, place the started step. */
  const apply = useCallback((tr: Transition) => {
    schedRef.current = tr.state;
    for (const d of tr.dropped) consumedRef.current?.(d.seq);
    if (tr.start) {
      clearRest();
      consumedRef.current?.(tr.start.item.seq);
      setPlaced({ step: tr.start, label: labelFor(tr.start) });
    } else if (isIdle(tr.state)) {
      setIdleTick((n) => n + 1);
    }
  }, []);

  /** The step `step` is done (animation finish, fallback timer, or cancelled as stale). Ignores stale reports. */
  const done = useCallback(
    (step: Step | null) => {
      if (step !== null && schedRef.current.inFlight !== step) return; // already handled (finish + fallback race)
      clearFallback();
      apply(finish(schedRef.current, reduceRef.current, screenRef.current));
    },
    [apply],
  );

  // Feed new focus events into the scheduler, in seq order.
  useEffect(() => {
    const fresh = queue.filter((f) => f.seq > lastSeqRef.current).sort((a, b) => a.seq - b.seq);
    for (const f of fresh) {
      lastSeqRef.current = Math.max(lastSeqRef.current, f.seq);
      const item = itemFromFocus(f);
      if (!item) {
        consumedRef.current?.(f.seq);
        continue;
      }
      apply(push(schedRef.current, item, reduceRef.current, screenRef.current));
    }
  }, [queue, apply]);

  // The screen changed: a step about the old screen is stale. Stop it now and move on (or rest).
  useEffect(() => {
    const p = placed;
    if (!p || currentScreenId === undefined) return;
    if (!isStale(p.step.item, currentScreenId)) return;
    animRef.current?.cancel();
    if (schedRef.current.inFlight === p.step) done(p.step);
    else apply(finish(schedRef.current, reduceRef.current, currentScreenId));
    // Nothing new started: hide rather than keep a label for a field that is not on screen.
    if (schedRef.current.inFlight === null && isIdle(schedRef.current)) setPlaced((cur) => (cur === p ? null : cur));
  }, [currentScreenId, placed, done, apply]);

  // Rest: the turn is over and nothing is in flight or waiting. Hold briefly so the user sees where it landed.
  useEffect(() => {
    if (turnActive !== false || !placed) return;
    if (!isIdle(schedRef.current)) return;
    clearRest();
    restRef.current = setTimeout(() => {
      restRef.current = null;
      if (isIdle(schedRef.current)) setPlaced(null);
    }, restMs);
    return clearRest;
  }, [turnActive, placed, restMs, idleTick]);

  // Drive the animation whenever a new step is placed.
  useLayoutEffect(() => {
    const el = elRef.current;
    if (!el || !placed) return;
    const step = placed.step;
    const to = rectCenter(step.item.target.rect);
    const toTransform = translate(to.x, to.y);

    animRef.current?.cancel();
    clearFallback();

    if (step.instant || step.durationMs === 0) {
      el.style.transform = toTransform;
      done(step);
      return;
    }
    const from = step.from ? rectCenter(step.from) : to;
    el.style.transform = toTransform; // the resting place if the animation is cancelled or unsupported
    const anim = el.animate([{ transform: translate(from.x, from.y) }, { transform: toTransform }], {
      duration: step.durationMs,
      easing: 'ease-out',
      fill: 'forwards',
    });
    animRef.current = anim;
    const onFinish = () => done(step);
    anim.addEventListener('finish', onFinish, { once: true });
    // Fallback: a background tab may never deliver `finish`. Never let that stall the chain.
    fallbackRef.current = setTimeout(() => done(step), step.durationMs + FINISH_SLACK_MS);
    return () => {
      anim.removeEventListener('finish', onFinish);
    };
  }, [placed, done]);

  useEffect(
    () => () => {
      animRef.current?.cancel();
      clearFallback();
      clearRest();
    },
    [],
  );

  if (!placed) return null;
  const shape = placed.step.item.target.shape;
  const rect = placed.step.item.target.rect;

  return (
    <div
      ref={elRef}
      className={`planchette planchette-${placed.step.gesture}`}
      data-shape={shape}
      data-seq={placed.step.item.seq}
      data-reduce={reduceMotion ? 'true' : 'false'}
      aria-hidden="true"
      style={{
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
