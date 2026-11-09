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
 *  - STALE steps are dropped (C-1, 2026-11-06): the agent sends a whole tool call's focus events within a few ms,
 *    while each glide takes 400-700 ms, so without this the planchette replays history seconds behind the screen and
 *    labels a field ("filling OPTION") that is no longer shown. A step is stale when the screen it was about is not the
 *    screen on display. Pass `screenId` to enable the rule; `undefined` turns it off (pure ordering tests).
 */

export const MAX_QUEUE = 5;
export const MIN_MS = 400;
export const MAX_MS = 700;

export type Gesture = 'sweep' | 'settle' | 'press';

export interface FocusItem {
  seq: number;
  mode: FieldFocus['mode'];
  toolCallId: string;
  /** The screen the operation acted on (contracts 4.3). May be '' from a non-conforming server (finding D-3). */
  screenId: string;
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

/** The screen on display: a screen id, null for "no screen yet", or undefined to disable the staleness rule. */
export type ScreenRef = string | null | undefined;

export const initialScheduler = (): SchedulerState => ({ inFlight: null, queue: [], at: null });

export const gestureFor = (mode: FieldFocus['mode']): Gesture =>
  mode === 'read' ? 'sweep' : mode === 'fill' ? 'settle' : 'press';

/** Turn a protocol event into a schedulable item; null when it does not name a place (fail closed). */
export function itemFromFocus(f: FieldFocus & { seq: number }): FocusItem | null {
  const target = focusTarget(f);
  return target ? { seq: f.seq, mode: f.mode, toolCallId: f.tool_call_id, screenId: f.screen_id ?? '', target } : null;
}

/**
 * Is this item about a screen other than the one on display?
 *  - A FIELD target must be verifiably on screen: an unknown screen on either side means stale (never label a field
 *    we cannot show). This covers the empty `screen_id` some servers send on step 0.
 *  - A whole-screen read or a key press names no field; it is stale only when both screen ids are known and differ.
 */
export function isStale(item: FocusItem, screenId: ScreenRef): boolean {
  if (screenId === undefined) return false;
  const known = item.screenId !== '';
  if (item.target.shape === 'field') return !known || screenId === null || item.screenId !== screenId;
  return known && screenId !== null && item.screenId !== screenId;
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

/** Start the next queued, non-stale step if nothing is in flight. Stale items at the head are dropped. */
function pump(state: SchedulerState, reduceMotion: boolean, dropped: FocusItem[], screenId: ScreenRef): Transition {
  if (state.inFlight || state.queue.length === 0) return { state, start: null, dropped };
  const fresh = state.queue.filter((i) => !isStale(i, screenId));
  const stale = state.queue.filter((i) => isStale(i, screenId));

  if (fresh.length === 0) return { state: { ...state, queue: [] }, start: null, dropped: [...dropped, ...stale] };

  if (reduceMotion) {
    // Jump straight to the newest target; the earlier ones are visited "instantly", i.e. skipped.
    const last = fresh[fresh.length - 1] as FocusItem;
    const skipped = state.queue.filter((i) => i !== last);
    const step = makeStep(last, state.at, true);
    return { state: { inFlight: null, queue: [], at: last.target.rect }, start: step, dropped: [...dropped, ...skipped] };
  }

  // Order is preserved: drop only the stale items AHEAD of the next fresh one. Later stale items stay queued and are
  // judged against the screen on display when their turn comes (the screen may have changed back by then).
  const headIdx = state.queue.indexOf(fresh[0] as FocusItem);
  const head = state.queue[headIdx] as FocusItem;
  const skipped = state.queue.slice(0, headIdx);
  const rest = state.queue.slice(headIdx + 1);
  const step = makeStep(head, state.at, false);
  return { state: { inFlight: step, queue: rest, at: state.at }, start: step, dropped: [...dropped, ...skipped] };
}

export function push(state: SchedulerState, item: FocusItem, reduceMotion: boolean, screenId?: ScreenRef): Transition {
  let queue = [...state.queue, item];
  const dropped: FocusItem[] = [];
  if (queue.length > MAX_QUEUE) {
    dropped.push(...queue.slice(0, -1));
    queue = [item];
  }
  return pump({ ...state, queue }, reduceMotion, dropped, screenId);
}

/** The driver reports that the in-flight glide ended (or was cancelled). */
export function finish(state: SchedulerState, reduceMotion: boolean, screenId?: ScreenRef): Transition {
  if (!state.inFlight) return pump(state, reduceMotion, [], screenId);
  const landed = state.inFlight.item.target.rect;
  return pump({ inFlight: null, queue: state.queue, at: landed }, reduceMotion, [], screenId);
}

/** Nothing in flight and nothing waiting. */
export const isIdle = (s: SchedulerState): boolean => s.inFlight === null && s.queue.length === 0;

/**
 * The shape named in the design: the plan for a whole queue at once.
 * `current` is what to start now, `next` is what waits, `dropped` is skipped.
 */
export function schedule(
  queue: FocusItem[],
  reduceMotion: boolean,
  from: Rect | null = null,
  screenId?: ScreenRef,
): { current: Step | null; next: FocusItem[]; dropped: FocusItem[] } {
  const r = pump(
    { inFlight: null, queue: queue.length > MAX_QUEUE ? [queue[queue.length - 1] as FocusItem] : queue, at: from },
    reduceMotion,
    queue.length > MAX_QUEUE ? queue.slice(0, -1) : [],
    screenId,
  );
  return { current: r.start, next: r.state.queue, dropped: r.dropped };
}
