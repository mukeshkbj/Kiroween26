import { describe, expect, it } from 'vitest';
import { contrastRatio, over, palette, parseHex, type TokenName } from '../terminal/palette';
import tokensCss from '../styles/tokens.css?raw';
import crtCss from '../styles/crt.css?raw';
import layoutCss from '../styles/layout.css?raw';
import appCss from '../styles/app.css?raw';
import indexHtml from '../../index.html?raw';

/**
 * REQ-020, 6.4: visual accessibility that can be checked without a browser. Contrast under prefers-contrast: more,
 * forced-colors handling, font sizes in rem, reflow safety at 400% zoom and the viewport meta. The rendered result
 * at 200% / 400% zoom, in Windows High Contrast and in the OS contrast mode is verified by hand in web/A11Y.md.
 */

const strip = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, '');

/** Custom properties declared in a block of CSS text. */
function vars(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) out[m[1] as string] = (m[2] as string).trim();
  return out;
}

/** The body of the first `@media (<query>) { ... }` block. */
function mediaBlock(css: string, query: string): string {
  const c = strip(css);
  const start = c.indexOf(query);
  expect(start, `no @media ${query}`).toBeGreaterThanOrEqual(0);
  const open = c.indexOf('{', start);
  let depth = 1;
  let j = open + 1;
  while (j < c.length && depth > 0) {
    if (c[j] === '{') depth++;
    else if (c[j] === '}') depth--;
    j++;
  }
  return c.slice(open + 1, j - 1);
}

const rootBlock = (css: string) => {
  const c = strip(css);
  const i = c.indexOf(':root');
  return c.slice(c.indexOf('{', i) + 1, c.indexOf('}', i));
};

describe('tokens.css and palette.ts agree (so the contrast arithmetic measures the real colours)', () => {
  const root = vars(rootBlock(tokensCss));
  const pairs: [string, TokenName][] = [
    ['--bg', 'bg'], ['--bg-raised', 'bgRaised'], ['--phosphor', 'phosphor'], ['--phosphor-dim', 'phosphorDim'],
    ['--phosphor-bright', 'phosphorBright'], ['--danger', 'danger'], ['--warn', 'warn'], ['--focus', 'focus'], ['--cursor', 'cursor'],
  ];
  it.each(pairs)('%s equals palette.%s', (cssVar, token) => {
    expect(root[cssVar]?.toLowerCase()).toBe(palette[token].toLowerCase());
  });
});

describe('prefers-contrast: more (REQ-020)', () => {
  const block = vars(mediaBlock(tokensCss, '@media (prefers-contrast: more)'));
  const bg = parseHex(palette.bg);

  it('brightens the phosphor and drops translucent effects', () => {
    expect(block['--phosphor']).toBeDefined();
    expect(block['--phosphor-dim']).toBeDefined();
    expect(block['--field-fill']).toBe('transparent');
    expect(block['--scanline-alpha']).toBe('0');
    expect(block['--vignette-alpha']).toBe('0');
    expect(block['--glow']).toBe('none');
  });

  it('every text token stays at or above 7:1 on the background', () => {
    for (const k of ['--phosphor', '--phosphor-dim'] as const) {
      const ratio = contrastRatio(parseHex(block[k] as string), bg);
      expect(ratio, `${k} = ${ratio.toFixed(2)}:1`).toBeGreaterThanOrEqual(7);
    }
    // the unchanged tokens (warn, danger, bright) are checked against the same bar
    for (const k of ['warn', 'danger', 'phosphorBright'] as const) {
      expect(contrastRatio(parseHex(palette[k]), bg)).toBeGreaterThanOrEqual(7);
    }
  });

  it('with no scanlines, text over the (now transparent) field fill is just text on the background', () => {
    const fill = over(parseHex(block['--phosphor'] as string), 0, bg);
    expect(contrastRatio(parseHex(block['--phosphor'] as string), fill)).toBeGreaterThanOrEqual(7);
  });
});

describe('forced-colors (REQ-020)', () => {
  it('turns off glow, scanlines and the vignette', () => {
    const block = vars(mediaBlock(tokensCss, '@media (forced-colors: active)'));
    expect(block['--glow']).toBe('none');
    expect(block['--scanline-alpha']).toBe('0');
    expect(block['--vignette-alpha']).toBe('0');
  });

  it('gives controls and the planchette system colours so they survive the forced palette', () => {
    const app = mediaBlock(appCss, '@media (forced-colors: active)');
    expect(app).toMatch(/ButtonText/);
    expect(app).toMatch(/Highlight/);
  });

  it('meaning never rests on colour alone: read-only edges are solid, others dashed AND labelled (see map tests)', () => {
    // The structural guarantee is tested in SpiritMap.test.tsx; here we only assert that the stylesheet does not
    // rely on a colour-only distinction for input fields: they carry an underline.
    expect(strip(layoutCss)).toMatch(/\.cell-input\s*\{[^}]*border-bottom/);
  });
});

describe('text sizing and reflow (REQ-020)', () => {
  const all = strip([tokensCss, crtCss, layoutCss, appCss].join('\n'));

  it('no font size is set in px (sizes follow the user\'s text size)', () => {
    const px = [...all.matchAll(/font-size\s*:\s*([^;}]+)/gi)].map((m) => (m[1] as string).trim()).filter((v) => /\d\s*px\b/.test(v));
    expect(px).toEqual([]);
  });

  it('there are font sizes in rem or relative units (so the audit above is not vacuous)', () => {
    expect([...all.matchAll(/font-size\s*:\s*[^;}]*rem/gi)].length).toBeGreaterThan(3);
  });

  it('no fixed minimum width exceeds a 320 CSS px viewport (400% zoom of 1280)', () => {
    const offenders: string[] = [];
    for (const m of all.matchAll(/(^|[;{\s])min-width\s*:\s*([^;}]+)/gi)) {
      const v = (m[2] as string).trim();
      if (/^min\(/.test(v)) continue; // min(22rem, 100%) can shrink
      const n = /^([\d.]+)(px|rem|em)$/.exec(v);
      if (!n) continue;
      const px = Number(n[1]) * (n[2] === 'px' ? 1 : 16);
      if (px > 320) offenders.push(v);
    }
    expect(offenders).toEqual([]);
  });

  it('the terminal grid scrolls horizontally instead of shrinking or clipping (two-dimensional content)', () => {
    expect(all).toMatch(/\.term-screen\s*\{[^}]*overflow-x:\s*auto/);
  });

  it('the page does not block pinch-zoom or text scaling', () => {
    expect(indexHtml).toMatch(/name="viewport"/);
    expect(indexHtml).not.toMatch(/user-scalable\s*=\s*(no|0)/i);
    expect(indexHtml).not.toMatch(/maximum-scale/i);
    expect(all).toMatch(/html\s*\{[^}]*font-size:\s*100%/);
  });

  it('there is a visible focus style that is not removed anywhere', () => {
    expect(all).toMatch(/:focus-visible\s*\{[^}]*outline:\s*3px/);
    expect(all).not.toMatch(/outline\s*:\s*(none|0)\b(?![^}]*focus-visible)/);
  });
});
