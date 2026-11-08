import type { AuditEntry } from '../protocol/types';

/** Pure helpers for the audit drawer (REQ-015): outcome groups, JSON export, and list windowing. */

export type OutcomeFilter = 'all' | 'ok' | 'pending' | 'blocked' | 'rejected';
export const FILTERS: readonly OutcomeFilter[] = ['all', 'ok', 'pending', 'blocked', 'rejected'];

const GROUPS: Record<Exclude<OutcomeFilter, 'all'>, readonly string[]> = {
  ok: ['ok'],
  pending: ['proposed', 'awaiting_oob'],
  blocked: [
    'blocked_read_only',
    'stale_screen',
    'needs_resync',
    'not_connected',
    'confirmation_unavailable',
    'session_lost',
    'ambiguous_ack',
    'error',
  ],
  rejected: ['rejected', 'superseded', 'expired', 'unknown_action', 'field_invalid'],
};

export function outcomeGroup(outcome: string): Exclude<OutcomeFilter, 'all'> | null {
  for (const [g, list] of Object.entries(GROUPS)) if (list.includes(outcome)) return g as Exclude<OutcomeFilter, 'all'>;
  return null; // an outcome this client does not know: shown under "all" only
}

export function filterEntries(entries: AuditEntry[], f: OutcomeFilter): AuditEntry[] {
  if (f === 'all') return entries;
  return entries.filter((e) => outcomeGroup(e.outcome) === f);
}

/** Entries are exported exactly as received (the hash chain covers their text), pretty-printed. */
export function exportAudit(entries: AuditEntry[]): string {
  return JSON.stringify(entries, null, 2);
}

export const VIRTUALISE_ABOVE = 500;

export interface Window {
  start: number;
  end: number; // exclusive
  padTop: number;
  padBottom: number;
}

/** Which rows to render for a scroll position. Below the threshold everything is rendered. */
export function windowSlice(
  total: number,
  scrollTop: number,
  viewportH: number,
  rowH: number,
  overscan = 10,
  threshold = VIRTUALISE_ABOVE,
): Window {
  if (total <= threshold || rowH <= 0) return { start: 0, end: total, padTop: 0, padBottom: 0 };
  const first = Math.max(0, Math.floor(scrollTop / rowH) - overscan);
  const last = Math.min(total, Math.ceil((scrollTop + viewportH) / rowH) + overscan);
  return { start: first, end: last, padTop: first * rowH, padBottom: (total - last) * rowH };
}

/** Display-only time: HH:MM:SS.mmm from the ISO text. The stored string is never reformatted. */
export function shortTime(ts: string): string {
  const m = /T(\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?/.exec(ts);
  return m ? `${m[1]}${m[2] ? '.' + m[2].padEnd(3, '0') : ''}` : ts;
}

export const shortScreen = (id: string | null): string => (id ? id.slice(0, 8) : '');
