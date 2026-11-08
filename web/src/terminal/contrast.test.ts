import { describe, expect, it } from 'vitest';
import { contrastRatio, over, parseHex, palette, ratioHex, type Rgb } from './palette';

/**
 * REQ-004 / REQ-020: text >= 4.5:1, UI components and focus >= 3:1, at every effects level, including the
 * scanline overlay. jsdom has no layout, so this is pure arithmetic on the tokens: a token change that breaks
 * AA fails here. The scanline overlay darkens the background by a known alpha of black at each level.
 */

const bg = parseHex(palette.bg);

/** Background as seen through the scanline overlay at a given alpha of black. */
const darkened = (alpha: number): Rgb => over({ r: 0, g: 0, b: 0 }, alpha, bg);

const SCANLINE_ALPHA = { off: 0, low: 0.05, full: 0.08 } as const;

describe('contrast arithmetic sanity', () => {
  it('matches known pairs', () => {
    expect(ratioHex('#ffffff', '#000000')).toBeCloseTo(21, 0);
    expect(ratioHex('#000000', '#000000')).toBeCloseTo(1, 5);
  });
  it('is symmetric', () => {
    expect(contrastRatio(parseHex(palette.phosphor), bg)).toBeCloseTo(contrastRatio(bg, parseHex(palette.phosphor)), 10);
  });
});

describe('text contrast >= 4.5:1 at every effects level', () => {
  const textTokens: [string, string][] = [
    ['phosphor', palette.phosphor],
    ['phosphorDim', palette.phosphorDim],
    ['phosphorBright', palette.phosphorBright],
    ['warn', palette.warn],
    ['danger', palette.danger],
  ];

  for (const [level, alpha] of Object.entries(SCANLINE_ALPHA)) {
    const b = darkened(alpha);
    for (const [name, hex] of textTokens) {
      it(`${name} on background at "${level}" level`, () => {
        const ratio = contrastRatio(parseHex(hex), b);
        expect(ratio, `${name} @ ${level} = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});

describe('non-text contrast >= 3:1 at every effects level', () => {
  // Focus ring and field underline must stay visible against the darkest background (full effects).
  const uiTokens: [string, string][] = [
    ['focus ring', palette.focus],
    ['field underline', palette.phosphor],
    ['cursor block', palette.cursor],
  ];
  const darkest = darkened(SCANLINE_ALPHA.full);
  for (const [name, hex] of uiTokens) {
    it(`${name} against the darkest background`, () => {
      expect(contrastRatio(parseHex(hex), darkest)).toBeGreaterThanOrEqual(3);
    });
  }

  it('the cursor block (bg text on bright cursor) is legible both ways', () => {
    expect(contrastRatio(parseHex(palette.cursor), bg)).toBeGreaterThanOrEqual(3);
  });
});

describe('the field fill tint never pulls input text below AA', () => {
  // Input cells draw phosphor text over a 10% phosphor fill over the base background.
  const fill = over(parseHex(palette.phosphor), 0.1, bg);
  it('phosphor text over the field fill stays >= 4.5:1', () => {
    expect(contrastRatio(parseHex(palette.phosphor), fill)).toBeGreaterThanOrEqual(4.5);
  });
});
