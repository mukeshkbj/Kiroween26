// Integrator end-to-end check of the REAL stack in a real browser:
//   web (VITE_MODE=live) -> websocket -> agent (scripted model) -> in-process MCP -> fake-insurance
// It never touches the live container (the fake app has no 3270 session).
//
//   node scripts/e2e-stack.mjs [--web URL] [--agent URL] [--shots DIR] [--workaround-goto]
//
// --workaround-goto reconnects (fresh fake app on the menu) before each business tool, to route
// around spirit-map's `goto` not navigating (handoff request-b-runtime-goto-navigate). Without it
// the run shows the bug as found. Prints a JSON report; exit 1 if any check failed.
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const require = createRequire(new URL('../web/package.json', import.meta.url));
const { chromium } = require('playwright');

const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : d; };
const WEB = arg('--web', 'http://127.0.0.1:5173');
const AGENT = arg('--agent', 'http://127.0.0.1:8000');
const SHOTS = arg('--shots', path.join(process.env.TEMP || '.', 'gss-e2e'));
const WORKAROUND = process.argv.includes('--workaround-goto');
mkdirSync(SHOTS, { recursive: true });

const report = { web: WEB, agent: AGENT, workaroundGoto: WORKAROUND, started: new Date().toISOString(), checks: [],
  console: [], pageErrors: [], failedRequests: [], wsFrames: { in: 0, out: 0, types: {} } };
let page;

async function check(name, fn) {
  const t0 = Date.now();
  try {
    const evidence = await fn();
    report.checks.push({ name, ok: true, ms: Date.now() - t0, evidence: evidence ?? null });
  } catch (e) {
    let shot = null;
    try { shot = path.join(SHOTS, `FAIL-${report.checks.length}.png`); await page.screenshot({ path: shot }); } catch { shot = null; }
    report.checks.push({ name, ok: false, ms: Date.now() - t0, error: String(e.message || e).split('\n')[0].slice(0, 300), shot });
  }
}
const shot = (n) => page.screenshot({ path: path.join(SHOTS, `${n}.png`) }).catch(() => {});
const norm = (s) => (s ?? '').replace(/\s+/g, ' ').trim();
const logText = async () => norm(await page.locator('[role="log"]').first().textContent({ timeout: 3000 }).catch(() => ''));
// Wait for the n-th completed assistant answer (turns are serial).
async function send(msg) {
  const before = await page.locator('[role="log"] [data-role="assistant"], [role="log"] .msg-assistant, [role="log"] .message.assistant').count();
  const box = page.getByLabel('Message to the séance');
  await box.waitFor({ state: 'visible', timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector('[aria-label="Message to the séance"]')?.disabled, null, { timeout: 30000 });
  await box.fill(msg);
  await box.press('Enter');
  return before;
}
async function connectSimulated() {
  // From anywhere: open the connect screen if there is a way back to it, then begin.
  const begin = page.locator('.system-card', { hasText: 'simulated' }).getByRole('button', { name: 'Begin séance' });
  if (!(await begin.isVisible().catch(() => false))) {
    const sw = page.getByRole('button', { name: /switch system|change system|systems|disconnect/i }).first();
    if (await sw.isVisible().catch(() => false)) await sw.click();
    else { await page.goto(WEB, { waitUntil: 'domcontentloaded' }); }
  }
  await begin.waitFor({ timeout: 20000 });
  await begin.click();
  await page.locator('.term-row').first().waitFor({ timeout: 20000 });
  await page.waitForFunction(() => document.querySelectorAll('.term-row').length === 24, null, { timeout: 10000 });
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1360, height: 860 } });
page = await ctx.newPage();
page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) report.console.push(`${m.type()}: ${m.text().slice(0, 240)}`); });
page.on('pageerror', (e) => report.pageErrors.push(String(e.message).slice(0, 240)));
page.on('requestfailed', (r) => report.failedRequests.push(`${r.method()} ${r.url()} ${r.failure()?.errorText}`));
page.on('websocket', (ws) => {
  ws.on('framereceived', (f) => { report.wsFrames.in++; try { const t = JSON.parse(f.payload).type; report.wsFrames.types[t] = (report.wsFrames.types[t] || 0) + 1; } catch { /* non-json */ } });
  ws.on('framesent', () => { report.wsFrames.out++; });
});

await check('web loads, connect screen, no REPLAY badge in live mode', async () => {
  await page.goto(WEB, { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'Begin séance' }).first().waitFor({ timeout: 20000 });
  const replay = await page.getByText('REPLAY', { exact: true }).count();
  await shot('01-connect');
  if (replay) throw new Error('REPLAY badge visible in live mode');
  return { cards: (await page.locator('.system-card').allTextContents()).map((c) => norm(c).slice(0, 90)) };
});

await check('connect: 24x80 green screen rendered', async () => {
  await connectSimulated();
  await shot('02-connected');
  return { rows: await page.locator('.term-row').count() };
});

await check('lookup via chat: business tool, real screen data, planchette moved', async () => {
  const positions = new Set(); const labels = new Set();
  let stop = false;
  const sampler = (async () => { while (!stop) {
    const b = await page.locator('.planchette').first().boundingBox().catch(() => null);
    if (b) positions.add(`${Math.round(b.x)},${Math.round(b.y)}`);
    const l = norm(await page.locator('.planchette-label').first().textContent({ timeout: 200 }).catch(() => ''));
    if (l) labels.add(l);
    await page.waitForTimeout(30);
  } })();
  await send('Look up policy P0000003');
  await page.getByText(/A\. ROSE/).first().waitFor({ timeout: 30000 });
  stop = true; await sampler;
  await shot('03-lookup');
  const ariaHidden = await page.locator('.planchette').first().getAttribute('aria-hidden');
  if (positions.size < 2) throw new Error(`planchette did not move (distinct positions ${positions.size})`);
  return { distinctPositions: positions.size, labels: [...labels].slice(0, 5), planchetteAriaHidden: ariaHidden };
});

await check('second business tool in the same session (spirit-map goto must navigate home)', async () => {
  await send('Look up policy P0000005');
  await page.waitForFunction(() => /LINDQVIST|did not work/i.test(document.querySelector('[role="log"]')?.textContent || ''), null, { timeout: 30000 });
  const t = await logText();
  if (!/LINDQVIST/.test(t)) throw new Error(`second lookup failed: ${(t.match(/That did not work[^.]*\.?/) || ['?'])[0]}`);
});

async function proposal(msg) {
  if (WORKAROUND) await connectSimulated();
  await send(msg);
  await page.getByRole('alertdialog').waitFor({ timeout: 30000 });
  return page.getByRole('alertdialog');
}

let modal1 = '';
await check('commit proposal -> confirmation modal (Deny focused, Approve delayed, gate facts + unverified agent text)', async () => {
  const dlg = await proposal('Set premium to 300 for P0000003');
  modal1 = norm(await dlg.textContent());
  const approveDisabled = await page.getByRole('button', { name: /^Approve/ }).isDisabled();
  const focus = await page.evaluate(() => {
    const el = document.activeElement;
    return ((el && (el.textContent || el.getAttribute('aria-label'))) || '').replace(/\s+/g, ' ').trim();
  });
  await shot('04-modal');
  const problems = [];
  if (!approveDisabled) problems.push('Approve enabled at open');
  if (!/deny/i.test(focus)) problems.push(`initial focus "${focus}"`);
  if (!/unverified/i.test(modal1)) problems.push('no "unverified" label');
  if (!/enter/i.test(modal1)) problems.push('key not shown');
  if (!/300/.test(modal1)) problems.push('new premium 300 not visible in the modal');
  if (problems.length) throw new Error(problems.join('; '));
  return { focus, modal: modal1.slice(0, 380) };
});

await check('approve: real click sends the key; same session shows premium 300.00', async () => {
  await page.waitForTimeout(800);
  await page.getByRole('button', { name: /^Approve/ }).click();
  await page.getByText(/Approved\. The key was sent/).waitFor({ timeout: 20000 });
  await page.getByRole('alertdialog').waitFor({ state: 'detached', timeout: 10000 });
  if (!WORKAROUND) { await send('Look up policy P0000003'); }
  else {
    // fresh connect reseeds the fake, so prove persistence through the server's own record instead
    return { note: 'persistence proven by the REST audit check (fresh connect reseeds the fake)' };
  }
  await page.getByText(/premium 300\.00/).last().waitFor({ timeout: 30000 });
  await shot('05-approved');
});

await check('deny via Escape: nothing changes', async () => {
  await proposal('Set premium to 111 for P0000001');
  await page.keyboard.press('Escape');
  await page.getByText(/Denied\. Nothing was changed/).waitFor({ timeout: 20000 });
  await shot('06-denied');
});

await check('audit drawer shows proposed, confirmed (oob:web-ui) and rejected', async () => {
  await page.getByRole('button', { name: 'Audit log' }).click();
  const drawer = page.getByRole('complementary', { name: 'Audit log' });
  await drawer.waitFor({ timeout: 10000 });
  await page.waitForTimeout(600);
  const t = norm(await drawer.textContent());
  await shot('07-audit');
  const missing = ['proposed', 'confirm_action', 'rejected'].filter((n) => !t.includes(n));
  if (missing.length) throw new Error(`audit drawer missing: ${missing.join(', ')} | sample: ${t.slice(0, 200)}`);
  return { oobShown: /oob:web-ui/.test(t), chainBadge: (t.match(/chain[^.]{0,40}/i) || [''])[0] };
});

await check('spirit-map view renders and marks the current screen', async () => {
  await page.keyboard.press('Escape').catch(() => {});
  await page.getByRole('button', { name: 'Spirit-map' }).click();
  await page.locator('.spirit-map').waitFor({ timeout: 10000 });
  await shot('08-spirit-map');
  return { nodes: await page.locator('.spirit-map [class*="node"]').count(), youAreHere: await page.getByText(/you are here/i).count() };
});

await check('server audit: chain verifies; exactly one commit, confirmed via oob:web-ui; denial recorded', async () => {
  const a = await (await fetch(`${AGENT}/api/audit?limit=1000`, { headers: { Origin: WEB } })).json();
  if (!a.chain_ok) throw new Error(`chain broken at ${a.broken_seq}`);
  const ok = a.entries.filter((e) => e.tool === 'confirm_action' && e.outcome === 'ok');
  const rej = a.entries.filter((e) => e.tool === 'deny_action' && e.outcome === 'rejected');
  if (ok.length !== 1) throw new Error(`expected 1 confirmed commit, got ${ok.length}`);
  if (!/^oob:web-ui:/.test(ok[0].confirmed_by)) throw new Error(`confirmed_by=${ok[0].confirmed_by}`);
  if (rej.length !== 1) throw new Error(`expected 1 denial, got ${rej.length}`);
  return { entries: a.entries.length, confirmedBy: ok[0].confirmed_by };
});

report.finished = new Date().toISOString();
report.ok = report.checks.every((c) => c.ok);
writeFileSync(path.join(SHOTS, 'report.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ ok: report.ok, checks: report.checks.map((c) => ({ ok: c.ok, name: c.name, error: c.error })) }, null, 2));
await browser.close();
process.exit(report.ok ? 0 : 1);
