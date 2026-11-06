import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { MAX_REVEAL_MS, revealedCount, revealedText } from './typing';

describe('typing reveal (REQ-006)', () => {
  it('reveals nothing at t=0, everything at t>=MAX, and is monotonic non-decreasing in between', () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 40 }), (len) => {
        expect(revealedCount(len, 0, false)).toBe(0);
        expect(revealedCount(len, MAX_REVEAL_MS, false)).toBe(len);
        expect(revealedCount(len, MAX_REVEAL_MS + 100, false)).toBe(len);
        let prev = 0;
        for (let t = 0; t <= MAX_REVEAL_MS; t += 10) {
          const n = revealedCount(len, t, false);
          expect(n).toBeGreaterThanOrEqual(prev);
          expect(n).toBeLessThanOrEqual(len);
          prev = n;
        }
      }),
      { numRuns: 100 },
    );
  });

  it('reduced motion shows the whole value immediately', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 40 }), fc.integer({ min: 0, max: 1000 }), (len, t) => {
        expect(revealedCount(len, t, true)).toBe(Math.max(0, len));
      }),
    );
  });

  it('skip (more events queued) shows the whole value immediately', () => {
    expect(revealedCount(8, 0, false, true)).toBe(8);
  });

  it('empty field reveals nothing', () => {
    expect(revealedCount(0, 100, false)).toBe(0);
    expect(revealedText('', 100, false)).toBe('');
  });

  it('revealedText is a prefix of the value', () => {
    fc.assert(
      fc.property(fc.string({ maxLength: 20 }), fc.integer({ min: 0, max: 500 }), (value, t) => {
        const shown = revealedText(value, t, false);
        expect(value.startsWith(shown)).toBe(true);
      }),
    );
  });

  it('a value longer than the reveal budget still finishes by MAX_REVEAL_MS', () => {
    expect(revealedText('P0000003', MAX_REVEAL_MS, false)).toBe('P0000003');
  });
});
