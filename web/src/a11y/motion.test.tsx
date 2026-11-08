import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppShell } from '../AppShell';
import { StoreProvider } from '../state/store';
import { AnnouncerProvider } from './Announcer';
import { ReplayTransport } from '../protocol/replayTransport';
import type { RestApi } from '../protocol/mock';
import { parseApps, parseAudit, parseSpiritMap } from '../protocol/guards';
import { useRevealedRows } from '../terminal/useRevealedRows';
import { MAX_REVEAL_MS } from '../terminal/typing';
import { Clock } from '../../test/clock';
import { loadExamples } from '../../test/examples';
import crtCss from '../styles/crt.css?raw';
import layoutCss from '../styles/layout.css?raw';
import tokensCss from '../styles/tokens.css?raw';
import appCss from '../styles/app.css?raw';

/**
 * REQ-021: every animation honours reduced motion, from the OS media query and from the in-app toggle.
 * Two kinds of evidence: a static audit of the stylesheets (every animation has an off switch for both), and a
 * runtime check that no Web Animation or reveal runs while reduce is on.
 */

// ---- 1. static audit of the CSS ------------------------------------------------------------------------------

interface Rule {
  selector: string;
  body: string;
  /** enclosing at-rule preludes, outermost first */
  at: string[];
}

/** A small brace-matching reader. Good enough for our hand-written CSS; it ignores comments. */
function parseCss(src: string, at: string[] = []): Rule[] {
  const css = src.replace(/\/\*[\s\S]*?\*\//g, '');
  const rules: Rule[] = [];
  let i = 0;
  while (i < css.length) {
    const open = css.indexOf('{', i);
    if (open < 0) break;
    const prelude = css.slice(i, open).trim();
    let depth = 1;
    let j = open + 1;
    while (j < css.length && depth > 0) {
      if (css[j] === '{') depth++;
      else if (css[j] === '}') depth--;
      j++;
    }
    const body = css.slice(open + 1, j - 1);
    if (prelude.startsWith('@')) {
      if (/^@(media|supports|container|layer)/.test(prelude)) rules.push(...parseCss(body, [...at, prelude]));
      else rules.push({ selector: prelude, body, at }); // @keyframes etc.
    } else {
      rules.push({ selector: prelude.replace(/\s+/g, ' '), body, at });
    }
    i = j;
  }
  return rules;
}

const allCss = [crtCss, layoutCss, tokensCss, appCss].join('\n');
const rules = parseCss(allCss);
const isKeyframes = (r: Rule) => r.selector.startsWith('@keyframes');
const startsAnimation = (r: Rule) => !isKeyframes(r) && /(^|[;\s])animation(-name)?\s*:\s*(?!none\b)\S[^;]*/i.test(r.body);
const disablesAnimation = (r: Rule) => /animation\s*:\s*none/i.test(r.body);
const reduceMedia = (r: Rule) => r.at.some((a) => /prefers-reduced-motion:\s*reduce/.test(a));

describe('stylesheet audit: every animation can be switched off (REQ-021)', () => {
  const animated = rules.filter(startsAnimation);

  it('finds the animations we know about (so the audit is not vacuous)', () => {
    const sels = animated.map((r) => r.selector).join(' | ');
    expect(animated.length).toBeGreaterThanOrEqual(3);
    expect(sels).toContain('.term-screen');
    expect(sels).toContain('.crt-overlay::after');
    expect(sels).toContain('.planchette-settle');
  });

  it.each(animated.map((r) => [r.selector, r] as const))('%s: off under the OS setting AND the in-app toggle', (selector) => {
    const parts = selector.split(',').map((s) => s.trim());
    for (const part of parts) {
      const os = rules.some(
        (r) => reduceMedia(r) && disablesAnimation(r) && r.selector.split(',').map((s) => s.trim()).includes(part),
      );
      const inApp = rules.some(
        (r) => disablesAnimation(r) && r.selector.split(',').map((s) => s.trim()).includes(`[data-motion="reduce"] ${part}`),
      );
      expect(os, `${part} lacks an animation:none rule under prefers-reduced-motion: reduce`).toBe(true);
      expect(inApp, `${part} lacks an animation:none rule under [data-motion="reduce"]`).toBe(true);
    }
  });

  it('no CSS transitions exist (they would be unguarded motion)', () => {
    const transitions = rules.filter((r) => /(^|[;\s])transition\s*:/i.test(r.body) && !reduceMedia(r));
    expect(transitions.map((r) => r.selector)).toEqual([]);
  });

  it('the in-app toggle and the OS query both zero the motion variables', () => {
    const tokens = parseCss(tokensCss);
    const inApp = tokens.find((r) => r.selector === '[data-motion="reduce"]');
    const os = tokens.find((r) => r.at.some((a) => /prefers-reduced-motion:\s*reduce/.test(a)));
    for (const r of [inApp, os]) {
      expect(r).toBeDefined();
      expect(r!.body).toMatch(/--glide-ms:\s*0ms/);
      expect(r!.body).toMatch(/--reveal-ms:\s*0ms/);
      expect(r!.body).toMatch(/--flicker-play:\s*paused/);
      expect(r!.body).toMatch(/--sweep-play:\s*paused/);
    }
  });

  it('the CSS audit would catch an unguarded animation (control)', () => {
    const bad = parseCss('.x { animation: spin 1s infinite; }');
    expect(bad.filter(startsAnimation)).toHaveLength(1);
    expect(rules.some((r) => r.selector === '.x')).toBe(false);
  });
});

// ---- 2. runtime: no Web Animation runs with reduce on ---------------------------------------------------------

const ex = loadExamples();
const rest: RestApi = {
  apps: async () => parseApps(ex.rest['apps'])!,
  audit: async () => parseAudit(ex.rest['audit'])!,
  spiritMap: async () => parseSpiritMap(ex.spiritMap),
};

let animateCalls = 0;
beforeEach(() => {
  animateCalls = 0;
  (Element.prototype as unknown as { animate: unknown }).animate = function () {
    animateCalls += 1;
    const listeners: (() => void)[] = [];
    // finish asynchronously so the planchette can chain steps like a real browser would
    queueMicrotask(() => listeners.forEach((l) => l()));
    return { addEventListener: (_t: string, fn: () => void) => listeners.push(fn), removeEventListener() {}, cancel() {}, finish() {} };
  };
  (window as unknown as { matchMedia: unknown }).matchMedia = (q: string) => ({
    matches: q.includes('min-width'), media: q, addEventListener() {}, removeEventListener() {},
  });
});
afterEach(() => {
  delete (window as unknown as { matchMedia?: unknown }).matchMedia;
  document.documentElement.removeAttribute('data-motion');
});

async function runLookup(reduce: boolean) {
  const clock = new Clock();
  const transport = new ReplayTransport({ lines: ex.transcripts['lookup'] ?? [], timer: clock.timer });
  render(
    <AnnouncerProvider>
      <StoreProvider transport={transport} now={() => clock.now}>
        <AppShell rest={rest} replay now={() => clock.now} />
      </StoreProvider>
    </AnnouncerProvider>,
  );
  await screen.findAllByRole('button', { name: 'Begin séance' });
  if (reduce) fireEvent.keyDown(window, { code: 'KeyR', altKey: true, shiftKey: true });
  for (let i = 0; i < 6000 && !transport.finished; i++) {
    await act(async () => {
      clock.advance(25);
    });
    const want = transport.expecting();
    if (want) {
      act(() => {
        transport.send(want);
      });
    }
  }
  await waitFor(() => expect(transport.finished).toBe(true));
}

describe('runtime: reduced motion stops all animation (REQ-021, 6.3)', () => {
  it('control: with motion allowed, the planchette does animate during a lookup', async () => {
    await runLookup(false);
    expect(animateCalls).toBeGreaterThan(0);
  });

  it('with the in-app toggle on, no Web Animation runs for a whole lookup', async () => {
    await runLookup(true);
    expect(document.documentElement.getAttribute('data-motion')).toBe('reduce');
    expect(animateCalls).toBe(0);
  });

  it('with the OS preference on, no Web Animation runs either', async () => {
    (window as unknown as { matchMedia: unknown }).matchMedia = (q: string) => ({
      matches: q.includes('reduce') ? true : q.includes('min-width'),
      media: q, addEventListener() {}, removeEventListener() {},
    });
    await runLookup(false);
    expect(animateCalls).toBe(0);
    expect(document.documentElement.getAttribute('data-motion')).toBe('reduce');
  });

  it('the Reduce motion checkbox does the same as the shortcut', async () => {
    const clock = new Clock();
    const transport = new ReplayTransport({ lines: [], timer: clock.timer });
    render(
      <AnnouncerProvider>
        <StoreProvider transport={transport} now={() => clock.now}>
          <AppShell rest={rest} replay now={() => clock.now} />
        </StoreProvider>
      </AnnouncerProvider>,
    );
    await userEvent.setup().click(screen.getByLabelText('Reduce motion'));
    expect(document.documentElement.getAttribute('data-motion')).toBe('reduce');
  });
});

// ---- 3. typing reveal ----------------------------------------------------------------------------------------

describe('typing reveal wiring (REQ-006)', () => {
  const blank = Array.from({ length: 24 }, () => ' '.repeat(80));
  const withValue = (v: string) => blank.map((r, i) => (i === 3 ? r.slice(0, 13) + v.padEnd(8, ' ') + r.slice(21) : r));
  const fill = { seq: 5, row: 3, col: 13, length: 8 };

  function setup(opts: { reduceMotion?: boolean; skip?: boolean } = {}) {
    const clock = { t: 0 };
    let cb: (() => void) | null = null;
    const hook = renderHook(
      ({ rows, f }: { rows: string[]; f: typeof fill | null }) =>
        useRevealedRows(rows, f, {
          reduceMotion: opts.reduceMotion ?? false,
          skip: opts.skip ?? false,
          now: () => clock.t,
          raf: (fn) => ((cb = fn), 1),
          cancelRaf: () => {},
        }),
      { initialProps: { rows: blank, f: null as typeof fill | null } },
    );
    const tick = (ms: number) => {
      clock.t += ms;
      act(() => {
        const fn = cb;
        cb = null;
        fn?.();
      });
    };
    return { hook, clock, tick };
  }

  const fieldText = (rows: string[]) => rows[3]!.slice(13, 21);

  it('types the new value in over time and finishes within the budget', () => {
    const h = setup();
    h.hook.rerender({ rows: withValue('P0000003'), f: fill });
    const start = fieldText(h.hook.result.current);
    expect(start.trim().length).toBeLessThan(8);
    h.tick(MAX_REVEAL_MS / 2);
    const mid = fieldText(h.hook.result.current).trim().length;
    expect(mid).toBeGreaterThan(start.trim().length - 1);
    expect(mid).toBeLessThan(8);
    h.tick(MAX_REVEAL_MS);
    expect(fieldText(h.hook.result.current)).toBe('P0000003');
    expect(h.hook.result.current).toEqual(withValue('P0000003'));
  });

  it('reveals only a prefix of the real value, never different text', () => {
    const h = setup();
    h.hook.rerender({ rows: withValue('P0000003'), f: fill });
    for (let i = 0; i < 6; i++) {
      expect('P0000003'.startsWith(fieldText(h.hook.result.current).trimEnd())).toBe(true);
      h.tick(70);
    }
  });

  it('is skipped under reduced motion: the whole value at once', () => {
    const h = setup({ reduceMotion: true });
    h.hook.rerender({ rows: withValue('P0000003'), f: fill });
    expect(fieldText(h.hook.result.current)).toBe('P0000003');
  });

  it('is skipped when more moves are queued', () => {
    const h = setup({ skip: true });
    h.hook.rerender({ rows: withValue('P0000003'), f: fill });
    expect(fieldText(h.hook.result.current)).toBe('P0000003');
  });

  it('does not animate when the field text did not change, or without a fill hint', () => {
    const h = setup();
    h.hook.rerender({ rows: withValue('P0000003'), f: null });
    expect(fieldText(h.hook.result.current)).toBe('P0000003');
    const h2 = setup();
    h2.hook.rerender({ rows: blank.map((r) => r), f: fill });
    expect(h2.hook.result.current).toEqual(blank);
  });

  it('animates each fill once', () => {
    const h = setup();
    h.hook.rerender({ rows: withValue('P0000003'), f: fill });
    h.tick(MAX_REVEAL_MS + 10);
    h.hook.rerender({ rows: withValue('P0000003'.replace('3', '4')), f: fill }); // same seq: already handled
    expect(fieldText(h.hook.result.current)).toBe('P0000004');
  });
});
