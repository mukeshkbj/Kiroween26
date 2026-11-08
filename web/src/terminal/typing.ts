/**
 * Typing reveal (REQ-006): when a fill lands, the characters of the new value appear progressively, up to a
 * total of MAX_REVEAL_MS. Pure scheduling here (how many characters are visible at time t); the component just
 * reads it. Skipped (full value at once) under reduced motion or when more animations are queued.
 */

export const MAX_REVEAL_MS = 400;

/** How many characters of a `length`-long value are visible `elapsed` ms into the reveal. */
export function revealedCount(length: number, elapsedMs: number, reduceMotion: boolean, skip = false): number {
  if (length <= 0) return 0;
  if (reduceMotion || skip) return length;
  if (elapsedMs <= 0) return 0;
  if (elapsedMs >= MAX_REVEAL_MS) return length;
  const perChar = MAX_REVEAL_MS / length;
  return Math.min(length, Math.floor(elapsedMs / perChar) + 1);
}

/** The substring to show; the rest of the field stays blank until it arrives. */
export function revealedText(value: string, elapsedMs: number, reduceMotion: boolean, skip = false): string {
  const n = revealedCount(value.length, elapsedMs, reduceMotion, skip);
  return value.slice(0, n);
}
