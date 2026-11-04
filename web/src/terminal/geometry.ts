import type { FieldFocus, FieldOut } from '../protocol/types';

/**
 * The only place with grid numbers. Everything is in cell units (1 unit = 1ch wide, 1 line-height tall),
 * so the DOM (CSS ch / line-height) and the planchette (CSS transform in the same box) agree at any zoom.
 * Positions are 0-origin: (row, col) with 0 <= row < 24, 0 <= col < 80.
 */

export const ROWS = 24;
export const COLS = 80;
/** The grid plus the 25th status line (OIA / key bar) below it. */
export const OIA_ROW = ROWS;

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const GRID: Rect = { x: 0, y: 0, w: COLS, h: ROWS };
/** The area the planchette may visit: the grid plus the key bar under it. */
export const STAGE: Rect = { x: 0, y: 0, w: COLS, h: ROWS + 1 };

export const inGrid = (row: number, col: number): boolean =>
  Number.isInteger(row) && Number.isInteger(col) && row >= 0 && row < ROWS && col >= 0 && col < COLS;

export function cellRect(row: number, col: number): Rect {
  return { x: col, y: row, w: 1, h: 1 };
}

/** Inverse of `cellRect` for a point in cell units; null outside the grid. */
export function cellAt(x: number, y: number): { row: number; col: number } | null {
  const row = Math.floor(y);
  const col = Math.floor(x);
  return inGrid(row, col) ? { row, col } : null;
}

export const rectContains = (outer: Rect, inner: Rect): boolean =>
  inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.w <= outer.x + outer.w && inner.y + inner.h <= outer.y + outer.h;

export const rectsOverlap = (a: Rect, b: Rect): boolean =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

export const rectCenter = (r: Rect): { x: number; y: number } => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 });

/**
 * The data cells of a field as one rect per row it touches. A field that runs past column 79 wraps to the
 * next row (3270 buffer addressing); cells past the last row are dropped. Out-of-range input yields [].
 */
export function fieldRects(pos: { row: number; col: number; length: number }): Rect[] {
  const { row, col, length } = pos;
  if (!inGrid(row, col) || !Number.isInteger(length) || length < 1) return [];
  const start = row * COLS + col;
  const end = Math.min(start + length, ROWS * COLS); // exclusive
  const rects: Rect[] = [];
  let i = start;
  while (i < end) {
    const r = Math.floor(i / COLS);
    const c = i % COLS;
    const n = Math.min(end - i, COLS - c);
    rects.push({ x: c, y: r, w: n, h: 1 });
    i += n;
  }
  return rects;
}

/** Number of cells covered, for tests and for the typing reveal. */
export const fieldCellCount = (rects: Rect[]): number => rects.reduce((n, r) => n + r.w * r.h, 0);

export const fieldOutRects = (f: Pick<FieldOut, 'row' | 'col' | 'length'>): Rect[] => fieldRects(f);

/** The attribute byte sits one cell before the first data column. Null when it would fall off the grid. */
export function attributeCell(f: { row: number; col: number }): Rect | null {
  const i = f.row * COLS + f.col - 1;
  if (!inGrid(f.row, f.col) || i < 0) return null;
  return cellRect(Math.floor(i / COLS), i % COLS);
}

export type TargetShape = 'field' | 'screen' | 'key';

export interface FocusTarget {
  shape: TargetShape;
  rect: Rect;
  /** For `key`: the key name to show on the bar. */
  key: string | null;
  label: string | null;
}

/** Where the key bar's key pill sits: left-aligned on the status line, wide enough for a long key name. */
export function keyBarRect(key: string): Rect {
  const w = Math.max(3, Math.min(COLS, key.length + 2));
  return { x: 1, y: OIA_ROW, w, h: 1 };
}

/**
 * Planchette target for a `field_focus` event. Fails closed: anything that does not describe a place inside the
 * stage returns null and the planchette simply does not move.
 */
export function focusTarget(f: Pick<FieldFocus, 'mode' | 'row' | 'col' | 'length' | 'key' | 'label'>): FocusTarget | null {
  if (f.mode === 'key') {
    if (f.key === null || f.key === '') return null;
    return { shape: 'key', rect: keyBarRect(f.key), key: f.key, label: f.label };
  }
  if (f.row === null || f.col === null || f.length === null) {
    // `read` without a position sweeps the whole screen; a `fill` without one is malformed.
    return f.mode === 'read' ? { shape: 'screen', rect: GRID, key: null, label: f.label } : null;
  }
  const rects = fieldRects({ row: f.row, col: f.col, length: f.length });
  const first = rects[0];
  if (!first) return null;
  // The planchette tracks the first row segment of a wrapped field; the sweep covers it, the ring settles on it.
  return { shape: 'field', rect: first, key: null, label: f.label };
}
