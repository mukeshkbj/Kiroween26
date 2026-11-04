import type { AppState, Confirmation, ScreenState } from './reducer';

/** Derived values. Anything computable from AppState lives here, not in state. */

/** REQ-013/012: the map node for the screen on display, or null ("uncharted"). */
export function currentNodeId(s: AppState): string | null {
  if (!s.map || !s.screen) return null;
  return s.map.nodes.find((n) => n.screen_id === s.screen?.screenId)?.id ?? null;
}

/** True when a screen is showing, a map is loaded, and the screen is not in it. */
export function isUncharted(s: AppState): boolean {
  return s.map !== null && s.screen !== null && currentNodeId(s) === null;
}

export function activeTurnId(s: AppState): string | null {
  for (let i = s.turnOrder.length - 1; i >= 0; i--) {
    const id = s.turnOrder[i] as string;
    if (s.turns[id]?.status === 'running') return id;
  }
  return null;
}

export const isBusy = (s: AppState): boolean => activeTurnId(s) !== null;

export const hasOpenConfirmation = (s: AppState): boolean =>
  s.confirmation !== null && (s.confirmation.phase === 'open' || s.confirmation.phase === 'sending');

export type ComposerBlock =
  | 'observer'
  | 'disconnected'
  | 'no_system'
  | 'llm_unavailable'
  | 'confirmation_open'
  | null;

/** REQ-008: why the composer is disabled, or null when it is usable. */
export function composerBlock(s: AppState): ComposerBlock {
  if (s.observerOnly) return 'observer';
  if (s.connection !== 'open') return 'disconnected';
  if (s.session.state !== 'connected') return 'no_system';
  if (s.session.llm && !s.session.llm.available) return 'llm_unavailable';
  if (hasOpenConfirmation(s)) return 'confirmation_open';
  return null;
}

/** Seconds left on a confirmation, from the monotonic receipt time (never server wall-clock). */
export function secondsLeft(c: Confirmation, nowMs: number): number {
  return Math.max(0, c.expiresInS - (nowMs - c.receivedAt) / 1000);
}

/**
 * REQ-016: the screen to draw in the modal. Only a screen whose id equals the gate's `screen_id`
 * qualifies; otherwise null and Approve stays disabled.
 */
export function confirmationScreen(s: AppState): ScreenState | null {
  const c = s.confirmation;
  if (!c) return null;
  return s.screensById[c.screenId] ?? null;
}

export function canApprove(s: AppState, nowMs: number, openedMs: number): boolean {
  const c = s.confirmation;
  if (!c || c.phase !== 'open' || c.readOnly || s.session.readOnly) return false;
  if (s.observerOnly) return false;
  if (confirmationScreen(s) === null) return false;
  if (secondsLeft(c, nowMs) <= 0) return false;
  return nowMs - openedMs >= APPROVE_DELAY_MS;
}

export const APPROVE_DELAY_MS = 600;
