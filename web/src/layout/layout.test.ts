import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { SPLIT_DEFAULT, SPLIT_MAX, SPLIT_MIN, clampSplit, resizeSplit, splitFromPointer } from './splitter';
import { SHORTCUTS, matchShortcut, nextEffects } from './shortcuts';

describe('splitter (REQ-001)', () => {
  it('arrow keys resize by a step; Home/End snap to the limits', () => {
    expect(resizeSplit(58, 'ArrowRight')).toBe(62);
    expect(resizeSplit(58, 'ArrowLeft')).toBe(54);
    expect(resizeSplit(58, 'Home')).toBe(SPLIT_MIN);
    expect(resizeSplit(58, 'End')).toBe(SPLIT_MAX);
    expect(resizeSplit(58, 'a')).toBeNull();
  });

  it('never leaves [MIN, MAX], whatever the input', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: -500, max: 500 }),
        fc.constantFrom('ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'),
        fc.boolean(),
        (v, key, shift) => {
          const r = resizeSplit(v, key, shift) as number;
          expect(r).toBeGreaterThanOrEqual(SPLIT_MIN);
          expect(r).toBeLessThanOrEqual(SPLIT_MAX);
        },
      ),
    );
    fc.assert(
      fc.property(fc.double(), fc.double(), fc.double(), (x, left, width) => {
        const r = splitFromPointer(x, left, width);
        expect(r).toBeGreaterThanOrEqual(SPLIT_MIN);
        expect(r).toBeLessThanOrEqual(SPLIT_MAX);
      }),
    );
  });

  it('clamps NaN and Infinity to a safe value', () => {
    expect(clampSplit(NaN)).toBe(SPLIT_DEFAULT);
    expect(clampSplit(Infinity)).toBe(SPLIT_DEFAULT);
  });

  it('pointer drag maps to a percentage of the container', () => {
    expect(splitFromPointer(500, 100, 800)).toBe(50);
    expect(splitFromPointer(0, 100, 800)).toBe(SPLIT_MIN);
    expect(splitFromPointer(5000, 100, 800)).toBe(SPLIT_MAX);
  });
});

describe('shortcuts (REQ-018)', () => {
  const ev = (code: string, o: Partial<{ altKey: boolean; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }> = {}) => ({
    code, altKey: true, shiftKey: true, ctrlKey: false, metaKey: false, ...o,
  });

  it('every shortcut needs a modifier: none fires on a bare key', () => {
    for (const s of SHORTCUTS) {
      expect(matchShortcut(ev(s.code, { altKey: false, shiftKey: false }))).toBeNull();
      expect(matchShortcut(ev(s.code, { altKey: true, shiftKey: false }))).toBeNull();
      expect(matchShortcut(ev(s.code, { altKey: false, shiftKey: true }))).toBeNull();
      expect(matchShortcut(ev(s.code, { ctrlKey: true }))).toBeNull();
      expect(matchShortcut(ev(s.code))).toBe(s.id);
    }
  });

  it('codes and ids are unique, and every shortcut is documented', () => {
    expect(new Set(SHORTCUTS.map((s) => s.code)).size).toBe(SHORTCUTS.length);
    expect(new Set(SHORTCUTS.map((s) => s.id)).size).toBe(SHORTCUTS.length);
    for (const s of SHORTCUTS) {
      expect(s.label).toMatch(/^Alt\+Shift\+/);
      expect(s.description.length).toBeGreaterThan(3);
    }
  });

  it('effects cycle visits all three levels and returns', () => {
    expect(nextEffects(nextEffects(nextEffects('low')))).toBe('low');
    expect(new Set(['full', 'low', 'off'].map((e) => nextEffects(e as 'full')))).toEqual(new Set(['full', 'low', 'off']));
  });
});
