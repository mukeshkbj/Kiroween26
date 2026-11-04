import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import {
  COLS,
  GRID,
  ROWS,
  STAGE,
  attributeCell,
  cellAt,
  cellRect,
  fieldCellCount,
  fieldRects,
  focusTarget,
  inGrid,
  keyBarRect,
  rectCenter,
  rectContains,
  rectsOverlap,
} from './geometry';

const rowArb = fc.integer({ min: 0, max: ROWS - 1 });
const colArb = fc.integer({ min: 0, max: COLS - 1 });

describe('cells', () => {
  it('every (row, col) maps to a rect inside the grid and back to the same cell (exhaustive)', () => {
    for (let row = 0; row < ROWS; row++) {
      for (let col = 0; col < COLS; col++) {
        const r = cellRect(row, col);
        expect(rectContains(GRID, r)).toBe(true);
        const c = rectCenter(r);
        expect(cellAt(c.x, c.y)).toEqual({ row, col });
        // Any point inside the cell maps back to it, including the top-left corner.
        expect(cellAt(r.x, r.y)).toEqual({ row, col });
        expect(cellAt(r.x + 0.999, r.y + 0.999)).toEqual({ row, col });
      }
    }
  });

  it('points outside the grid map to nothing', () => {
    expect(cellAt(-0.1, 0)).toBeNull();
    expect(cellAt(0, -0.1)).toBeNull();
    expect(cellAt(COLS, 0)).toBeNull();
    expect(cellAt(0, ROWS)).toBeNull();
  });

  it('inGrid rejects non-integers and out-of-range values', () => {
    fc.assert(
      fc.property(fc.double({ noNaN: true }), fc.double({ noNaN: true }), (r, c) => {
        if (inGrid(r, c)) {
          expect(Number.isInteger(r) && Number.isInteger(c) && r >= 0 && r < ROWS && c >= 0 && c < COLS).toBe(true);
        }
      }),
    );
  });
});

describe('field rectangles', () => {
  it('stay inside the grid, cover exactly the visible cells, and every cell round-trips', () => {
    fc.assert(
      fc.property(rowArb, colArb, fc.integer({ min: 1, max: 400 }), (row, col, length) => {
        const rects = fieldRects({ row, col, length });
        expect(rects.length).toBeGreaterThan(0);
        for (const r of rects) {
          expect(rectContains(GRID, r)).toBe(true);
          expect(r.h).toBe(1);
        }
        const expected = Math.min(length, ROWS * COLS - (row * COLS + col));
        expect(fieldCellCount(rects)).toBe(expected);
        // first rect starts at the field's first data column
        expect(rects[0]).toMatchObject({ x: col, y: row });
        // every covered cell maps back to a cell of this field
        for (const r of rects) {
          for (let x = r.x; x < r.x + r.w; x++) {
            expect(cellAt(x + 0.5, r.y + 0.5)).toEqual({ row: r.y, col: x });
          }
        }
        // all rects except possibly the last span to the end of the row (wrap)
        for (const r of rects.slice(0, -1)) expect(r.x + r.w).toBe(COLS);
      }),
      { numRuns: 300 },
    );
  });

  it('fields that do not overlap never produce overlapping rectangles', () => {
    // Build non-overlapping fields by construction: walk the buffer, leaving one attribute cell before each field.
    const plan = fc.array(fc.tuple(fc.integer({ min: 0, max: 30 }), fc.integer({ min: 1, max: 25 })), { maxLength: 30 });
    fc.assert(
      fc.property(plan, (steps) => {
        const fields: { row: number; col: number; length: number }[] = [];
        let cursor = 1; // the first attribute byte sits at cell 0
        for (const [gap, length] of steps) {
          const start = cursor + gap;
          if (start + length > ROWS * COLS) break;
          fields.push({ row: Math.floor(start / COLS), col: start % COLS, length });
          cursor = start + length + 1; // +1 for the next field's attribute byte
        }
        const all = fields.map((f) => fieldRects(f));
        for (let i = 0; i < all.length; i++) {
          for (let j = i + 1; j < all.length; j++) {
            for (const a of all[i] as ReturnType<typeof fieldRects>) {
              for (const b of all[j] as ReturnType<typeof fieldRects>) expect(rectsOverlap(a, b)).toBe(false);
            }
          }
          // a field never covers its own attribute byte
          const attr = attributeCell(fields[i] as { row: number; col: number });
          if (attr) for (const r of all[i] as ReturnType<typeof fieldRects>) expect(rectsOverlap(r, attr)).toBe(false);
        }
      }),
      { numRuns: 300 },
    );
  });

  it('rejects out-of-range or empty fields instead of guessing', () => {
    expect(fieldRects({ row: -1, col: 0, length: 3 })).toEqual([]);
    expect(fieldRects({ row: 0, col: COLS, length: 3 })).toEqual([]);
    expect(fieldRects({ row: ROWS, col: 0, length: 3 })).toEqual([]);
    expect(fieldRects({ row: 0, col: 0, length: 0 })).toEqual([]);
    expect(fieldRects({ row: 0.5, col: 0, length: 3 })).toEqual([]);
  });

  it('wraps a field that crosses column 79 onto the next row', () => {
    expect(fieldRects({ row: 2, col: 78, length: 5 })).toEqual([
      { x: 78, y: 2, w: 2, h: 1 },
      { x: 0, y: 3, w: 3, h: 1 },
    ]);
    // and truncates at the bottom-right corner
    expect(fieldCellCount(fieldRects({ row: 23, col: 79, length: 10 }))).toBe(1);
  });

  it('the attribute byte of col 0 has no cell on the same row (it is the previous row end or off-grid)', () => {
    expect(attributeCell({ row: 0, col: 0 })).toBeNull();
    expect(attributeCell({ row: 3, col: 0 })).toEqual({ x: 79, y: 2, w: 1, h: 1 });
    expect(attributeCell({ row: 3, col: 14 })).toEqual({ x: 13, y: 3, w: 1, h: 1 });
  });
});

describe('planchette targets stay inside the stage', () => {
  const focusArb = fc.record({
    mode: fc.constantFrom('read', 'fill', 'key') as fc.Arbitrary<'read' | 'fill' | 'key'>,
    row: fc.option(fc.integer({ min: -5, max: 40 }), { nil: null }),
    col: fc.option(fc.integer({ min: -5, max: 120 }), { nil: null }),
    length: fc.option(fc.integer({ min: -2, max: 300 }), { nil: null }),
    key: fc.option(fc.string({ maxLength: 12 }), { nil: null }),
    label: fc.option(fc.string({ maxLength: 12 }), { nil: null }),
  });

  it('any focus event yields null or a target within the stage', () => {
    fc.assert(
      fc.property(focusArb, (f) => {
        const t = focusTarget(f);
        if (t === null) return;
        expect(rectContains(STAGE, t.rect)).toBe(true);
        if (t.shape === 'field') expect(rectContains(GRID, t.rect)).toBe(true);
        if (t.shape === 'key') expect(t.rect.y).toBe(ROWS);
        const c = rectCenter(t.rect);
        expect(Number.isFinite(c.x) && Number.isFinite(c.y)).toBe(true);
      }),
      { numRuns: 500 },
    );
  });

  it('every key name fits on the key bar', () => {
    fc.assert(
      fc.property(fc.string({ minLength: 1, maxLength: 200 }), (key) => {
        expect(rectContains(STAGE, keyBarRect(key))).toBe(true);
      }),
    );
  });

  it('read without a position sweeps the screen; fill without a position is refused', () => {
    expect(focusTarget({ mode: 'read', row: null, col: null, length: null, key: null, label: null })?.shape).toBe('screen');
    expect(focusTarget({ mode: 'fill', row: null, col: null, length: null, key: null, label: null })).toBeNull();
    expect(focusTarget({ mode: 'key', row: null, col: null, length: null, key: null, label: null })).toBeNull();
  });
});
