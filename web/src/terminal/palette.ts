/**
 * The phosphor palette as data, mirroring styles/tokens.css. The contrast test imports this so a token change
 * that breaks WCAG AA fails in CI (jsdom has no layout, so contrast is pure arithmetic here, not measured).
 */

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export const palette = {
  bg: '#020a04',
  bgRaised: '#06180d',
  phosphor: '#3dff7a',
  phosphorDim: '#52c47d',
  phosphorBright: '#c9ffd9',
  danger: '#ff8f6b',
  warn: '#ffd166',
  focus: '#ffffff',
  cursor: '#c9ffd9',
} as const;

export type TokenName = keyof typeof palette;

export function parseHex(hex: string): Rgb {
  const h = hex.replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

/** Composite an rgba colour over an opaque background. alpha in [0,1]. */
export function over(fg: Rgb, alpha: number, bg: Rgb): Rgb {
  return {
    r: fg.r * alpha + bg.r * (1 - alpha),
    g: fg.g * alpha + bg.g * (1 - alpha),
    b: fg.b * alpha + bg.b * (1 - alpha),
  };
}

const channel = (c: number): number => {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};

export function relativeLuminance(c: Rgb): number {
  return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
}

/** WCAG 2.x contrast ratio, 1..21. */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

export const ratioHex = (a: string, b: string): number => contrastRatio(parseHex(a), parseHex(b));
