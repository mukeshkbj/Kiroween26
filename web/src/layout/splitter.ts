/**
 * Pure splitter logic (REQ-001): the terminal/chat divider as a percentage for the terminal pane. Arrow keys
 * resize by a step, Home/End snap to the limits. Everything is clamped so neither pane can disappear.
 */

export const SPLIT_MIN = 30;
export const SPLIT_MAX = 75;
export const SPLIT_DEFAULT = 58;
export const SPLIT_STEP = 4;
export const WIDE_BREAKPOINT_PX = 1100;

export const clampSplit = (v: number): number =>
  Number.isFinite(v) ? Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, Math.round(v))) : SPLIT_DEFAULT;

/** New split after a key on the separator, or null if the key is not a splitter key. */
export function resizeSplit(current: number, key: string, shift = false): number | null {
  const step = shift ? SPLIT_STEP * 3 : SPLIT_STEP;
  switch (key) {
    case 'ArrowLeft':
    case 'ArrowUp':
      return clampSplit(current - step);
    case 'ArrowRight':
    case 'ArrowDown':
      return clampSplit(current + step);
    case 'Home':
      return SPLIT_MIN;
    case 'End':
      return SPLIT_MAX;
    default:
      return null;
  }
}

/** Pointer drag: position within the container as a percentage. */
export const splitFromPointer = (clientX: number, left: number, width: number): number =>
  width <= 0 ? SPLIT_DEFAULT : clampSplit(((clientX - left) / width) * 100);
