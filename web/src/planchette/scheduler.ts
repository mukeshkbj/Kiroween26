import type { FieldFocus } from '../protocol/types';
import { focusTarget, rectCenter, type FocusTarget, type Rect } from '../terminal/geometry';

/**
 * Pure planchette scheduler (REQ-005, REQ-027). It decides *what* to animate and *when*; it never touches the DOM.
 * The animation driver calls `push` for every `field_focus` and `finish` when a glide ends.
 *
 *  - order is preserved
 *  - at most one step is in flight
 *  - more than MAX_QUEUE waiting -> everything but the newest is dropped (the planchette simply jumps ahead)
 *  - reduced motion -> every step is instant; nothing is ever animated
 */

export const MAX_QUEUE = 5;
export const MIN_MS = 400;
export const MAX_MS = 700;

export type Gesture = 'sweep' | 'settle' | 'press';

export interface FocusItem {
  seq: number;
  mode: FieldFocus['mode'];
  toolCallId: string;
  target: FocusTarget;
}

export interface Step {
  item: FocusItem;
  /** Rect the planchette starts from, or null for the first move. */
  from: Rect | null;
  instant: boolean;
  /** 0 when instant. Otherwise within [MIN_MS, MAX_MS]. */
  durationMs: number;
  gesture: Gesture;
}

export interface SchedulerState {
  inFlight: Step | null;
  queue: FocusItem[];
  /** Where the planchette last landed. */
  at: Rect | null;
}

export const initialScheduler = (): SchedulerState => ({ inFlight: null, queue: [], at: null });

export const gestureFor = (mode: FieldFocus['mode']): Gesture =>
  mode === 'read' ? 'sweep' : mode === 'fill' ? 'settle' : 'press';

/** Turn a protocol event into a schedulable item; null when it does not name a place (fail closed). */
export function itemFromFocus(f: FieldFocus & { seq: number }): FocusItem | null {
  const target = focusTarget(f);
  return target ? { seq: f.seq, mode: f.mode, toolCallId: f.tool_call_id, target } : null;
}

/** Duration grows with distance (cells are about twice as tall as wide), clamped to [MIN_MS, MAX_MS]. */
export function durationFor(from: Rect | null, to: Rect): number {
  if (!from) return MIN_MS;
  const a = rectCenter(from);
  const b = rectCenter(to);
  const dist = Math.hypot(a.x - b.x, (a.y - b.y) * 2);
  return Math.round(Math.min(MAX_MS, Math.max(MIN_MS, MIN_MS + dist * 4)));
}

function makeStep(item: FocusItem, from: Rect | null, reduceMotion: boolean): Step {
  return {
    item,
    from,
    instant: reduceMotion,
    durationMs: reduceMotion ? 0 : durationFor(from, item.target.rect),
    gesture: gestureFor(item.mode),
  };
}

export interface Transition {
  state: SchedulerState;
  /** A step the driver must start now (at most one). */
  start: Step | null;
  /** Items that will never be animated. */
  dropped: FocusItem[];
}

/** Start the next queued step if nothing is in flight. */
function pump(state: SchedulerState, reduceMotion: boolean, dropped: FocusItem[]): Transition {
  if (state.inFlight || state.queue.length === 0) return { state, start: null, dropped };

  if (reduceMotion) {
    // Jump straight to the newest target; the earlier ones are visited "instantly", i.e. skipped.
    const last = state.queue[state.queue.length - 1] as FocusItem;
    const skipped = state.queue.slice(0, -1);
    const step = makeStep(last, state.at, true);
    return { state: { inFlight: null, queue: [], at: last.target.rect }, start: step, dropped: [...dropped, ...skipped] };
  }

  const [head, ...rest] = state.queue as [FocusItem, ...FocusItem[]];
  const step = makeStep(head, state.at, false);
  return { state: { inFlight: step, queue: rest, at: state.at }, start: step, dropped };
}

export function push(state: SchedulerState, item: FocusItem, reduceMotion: boolean): Transition {
  let queue = [...state.queue, item];
  const dropped: FocusItem[] = [];
  if (queue.length > MAX_QUEUE) {
    dropped.push(...queue.slice(0, -1));
    queue = [item];
  }
  return pump({ ...state, queue }, reduceMotion, dropped);
}

/** The driver reports that the in-flight glide ended (or was cancelled). */
export function finish(state: SchedulerState, reduceMotion: boolean): Transition {
  if (!state.inFlight) return pump(state, reduceMotion, []);
  const landed = state.inFlight.item.target.rect;
  return pump({ inFlight: null, queue: state.queue, at: landed }, reduceMotion, []);
}

/**
 * The shape named in the design: the plan for a whole queue at once.
 * `current` is what to start now, `next` is what waits, `dropped` is skipped.
 */
export function schedule(
  queue: FocusItem[],
  reduceMotion: boolean,
  from: Rect | null = null,
): { current: Step | null; next: FocusItem[]; dropped: FocusItem[] } {
  const r = pump({ inFlight: null, queue: queue.length > MAX_QUEUE ? [queue[queue.length - 1] as FocusItem] : queue, at: from }, reduceMotion, queue.length > MAX_QUEUE ? queue.slice(0, -1) : []);
  return { current: r.start, next: r.state.queue, dropped: r.dropped };
}
