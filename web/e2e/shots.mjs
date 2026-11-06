// Real-browser screenshots and checks in mock/replay mode (Playwright + its Chromium).
//   1. npm run dev:mock        (in another terminal; serves http://localhost:5173 with VITE_MODE=mock)
//   2. npm run shots           (BASE_URL=http://localhost:5173 by default)
// Writes PNGs to docs/handoff/c/shots/ and docs/handoff/c/shots/browser-checks.json.
// Nothing here talks to a backend or the live container: it plays recorded transcripts.
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, '..', '..', 'docs', 'handoff', 'c', 'shots');
const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const AXE = readFileSync(join(here, '..', 'node_modules', 'axe-core', 'axe.min.js'), 'utf8');
const PREFIX = process.env.SHOT_PREFIX ?? '';
mkdirSync(OUT, { recursive: true });

const report = { base: BASE, browser: null, axe: {}, checks: {} };
const shot = async (page, name) => {
  await page.screenshot({ path: join(OUT, `${PREFIX}${name}.png`), animations: 'allow' });
  console.log('shot', `${PREFIX}${name}.png`);
};

/** axe-core in the real browser, with colour-contrast ENABLED (jsdom could not measure it). */
async function axe(page, name) {
  await page.addScriptTag({ content: AXE });
  const r = await page.evaluate(async () => {
    // eslint-disable-next-line no-undef
    const res = await axe.run(document, { resultTypes: ['violations'] });
    return res.violations.map((v) => ({
      id: v.id, impact: v.impact, help: v.help,
      nodes: v.nodes.slice(0, 4).map((n) => ({ target: n.target.join(' '), summary: (n.failureSummary ?? '').split('\n').slice(0, 3).join(' | '), html: n.html.slice(0, 160) })),
    }));
  });
  report.axe[name] = r;
  console.log('axe', name, r.length === 0 ? 'clean' : r.map((v) => `${v.id}(${v.nodes.length})`).join(' '));
}

async function open(browser, scenario, ctxOpts = {}, narrow = false) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, ...ctxOpts });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  await page.goto(`${BASE}/?scenario=${scenario}`);
  // on a narrow viewport the systems list lives in the hidden Séance view until it is selected
  if (narrow) await page.getByRole('navigation', { name: 'Panes' }).waitFor({ timeout: 20000 });
  else await page.getByRole('button', { name: 'Begin séance' }).first().waitFor({ timeout: 20000 });
  return { ctx, page };
}

const connectFake = async (page) => {
  await page.locator('.system-card', { hasText: 'simulated' }).getByRole('button', { name: 'Begin séance' }).click();
  await page.getByLabel('Message to the séance').waitFor();
  await page.waitForFunction(() => !document.querySelector('#composer-input')?.disabled, null, { timeout: 20000 });
};
const ask = async (page, text) => {
  await page.getByLabel('Message to the séance').fill(text);
  await page.keyboard.press('Enter');
};

const browser = await chromium.launch();
report.browser = browser.version();

// ---- 1. dormant ---------------------------------------------------------------------------------------------
{
  const { ctx, page } = await open(browser, 'lookup');
  await page.waitForTimeout(600);
  await shot(page, '01-dormant');
  await axe(page, 'dormant');
  await ctx.close();
}

// ---- 2/3. populated, planchette mid-flight, answer ----------------------------------------------------------
{
  const { ctx, page } = await open(browser, 'lookup');
  await connectFake(page);
  await page.locator('.term-row').first().waitFor();
  await page.waitForFunction(() => document.querySelector('.term-grid')?.textContent?.includes('MAIN MENU'));
  await page.waitForTimeout(500);
  await shot(page, '02-populated');
  await axe(page, 'populated');

  await ask(page, 'Look up policy P0000003');
  // catch the planchette while it is gliding to a field
  await page.waitForFunction(() => /filling|reading/.test(document.querySelector('.planchette-label')?.textContent ?? ''), null, { timeout: 20000 });
  await page.waitForTimeout(220);
  await shot(page, '03-planchette-midflight');
  report.checks.planchetteLabel = await page.locator('.planchette-label').textContent();
  report.checks.planchetteAriaHidden = await page.locator('.planchette').getAttribute('aria-hidden');
  report.checks.planchettePointerEvents = await page.locator('.planchette').evaluate((e) => getComputedStyle(e).pointerEvents);

  await page.waitForFunction(() => document.querySelector('.chat-log')?.textContent?.includes('A. ROSE'), null, { timeout: 30000 });
  await page.waitForTimeout(700);
  await shot(page, '04-answer');
  await axe(page, 'answer-with-step-cards');

  // spirit-map view, with the current node highlighted
  await page.getByRole('button', { name: 'Spirit-map' }).click();
  await page.locator('.spirit-map').waitFor();
  await page.waitForTimeout(300);
  await shot(page, '07-spirit-map');
  await axe(page, 'spirit-map');

  // audit drawer
  await page.getByRole('button', { name: 'Audit log' }).click();
  await page.getByRole('complementary', { name: 'Audit log' }).waitFor();
  await page.waitForTimeout(300);
  await shot(page, '06-audit-drawer');
  await axe(page, 'audit-drawer');
  await ctx.close();
}

// ---- 4. confirmation modal, including the real-browser trusted-event check -----------------------------------
{
  const { ctx, page } = await open(browser, 'commit-approve');
  await connectFake(page);
  await ask(page, 'Set the premium of P0000003 to 300');
  await page.getByRole('alertdialog').waitFor({ timeout: 40000 });
  await page.waitForTimeout(900); // past the 600 ms approve delay
  await shot(page, '05-confirmation-modal');
  await axe(page, 'confirmation-modal');
  report.checks.modalInitialFocus = await page.evaluate(() => document.activeElement?.textContent);
  report.checks.modalRole = await page.getByRole('alertdialog').getAttribute('aria-modal');
  report.checks.appInertWhileOpen = await page.evaluate(() => document.querySelector('.app')?.hasAttribute('inert'));

  // 3.6: a script-dispatched click must NOT approve; a real activation must.
  await page.evaluate(() => document.querySelector('.btn-approve').click());
  await page.waitForTimeout(400);
  report.checks.scriptClickDidNotApprove = await page.getByRole('alertdialog').isVisible()
    && (await page.getByRole('button', { name: /^Approve/ }).isVisible());
  await page.getByRole('button', { name: /^Approve/ }).click();
  await page.getByText(/Approved\. The key was sent/).waitFor({ timeout: 20000 });
  report.checks.realClickApproved = true;
  await shot(page, '05b-confirmation-approved');
  await ctx.close();
}
{
  // Esc is Deny, and Approve is disabled during the first 600 ms.
  const { ctx, page } = await open(browser, 'commit-deny');
  await connectFake(page);
  await ask(page, 'Set the premium of P0000003 to 300');
  await page.getByRole('alertdialog').waitFor({ timeout: 40000 });
  report.checks.approveDisabledAtOpen = await page.getByRole('button', { name: /^Approve/ }).isDisabled();
  await page.keyboard.press('Escape');
  await page.getByText(/Denied\. Nothing was changed/).waitFor({ timeout: 20000 });
  report.checks.escDenied = true;
  await ctx.close();
}

// ---- 5. session lost, and the narrow (mobile) layout -------------------------------------------------------
{
  const { ctx, page } = await open(browser, 'session-lost');
  await connectFake(page);
  await ask(page, 'Look up policy P0000003');
  await page.getByText(/lost its connection/).waitFor({ timeout: 40000 }).catch(() => {});
  await page.waitForTimeout(400);
  await shot(page, '08-session-lost');
  await axe(page, 'session-lost');
  await ctx.close();
}
{
  const { ctx, page } = await open(browser, 'lookup', { viewport: { width: 390, height: 844 } }, true);
  await page.waitForTimeout(400);
  await shot(page, '09-narrow');
  await axe(page, 'narrow');
  report.checks.narrowHorizontalOverflowPx = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await ctx.close();
}

// ---- 6. reduced motion (OS setting) -----------------------------------------------------------------------
{
  const { ctx, page } = await open(browser, 'lookup', { reducedMotion: 'reduce' });
  await connectFake(page);
  await page.evaluate(() => {
    window.__animateCalls = 0;
    const orig = Element.prototype.animate;
    Element.prototype.animate = function (...a) { window.__animateCalls++; return orig.apply(this, a); };
  });
  await ask(page, 'Look up policy P0000003');
  await page.waitForFunction(() => document.querySelector('.chat-log')?.textContent?.includes('A. ROSE'), null, { timeout: 30000 });
  await page.waitForTimeout(500);
  report.checks.reducedMotionAnimateCalls = await page.evaluate(() => window.__animateCalls);
  report.checks.reducedMotionHtmlAttr = await page.evaluate(() => document.documentElement.getAttribute('data-motion'));
  report.checks.reducedMotionRunningAnimations = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === 'running').length);
  await shot(page, '10-reduced-motion');
  await ctx.close();
}

// ---- 7. zoom / reflow: 400% of 1280 is a 320 px wide viewport ---------------------------------------------
{
  const { ctx, page } = await open(browser, 'lookup', { viewport: { width: 320, height: 720 } }, true);
  await page.waitForTimeout(400);
  report.checks.reflow320HorizontalOverflowPx = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await shot(page, '11-reflow-320');
  await ctx.close();
}

await browser.close();
writeFileSync(join(OUT, `${PREFIX}browser-checks.json`), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report.checks, null, 2));
const bad = Object.entries(report.axe).filter(([, v]) => v.length);
console.log(bad.length ? `axe: ${bad.length} state(s) with violations` : 'axe: all clean');
