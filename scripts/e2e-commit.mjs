// Integrator e2e, confirmation phase only: fresh agent (fake app on the menu) -> one commit proposal
// in a real browser -> modal checks -> approve or deny -> audit drawer -> server audit.
// Starting fresh routes around spirit-map's non-navigating `goto` (request-b-runtime-goto-navigate).
//
//   node scripts/e2e-commit.mjs --decision approve|deny [--web URL] [--agent URL] [--shots DIR]
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const require = createRequire(new URL('../web/package.json', import.meta.url));
const { chromium } = require('playwright');
const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : d; };
const WEB = arg('--web', 'http://127.0.0.1:5173');
const AGENT = arg('--agent', 'http://127.0.0.1:8000');
const DECISION = arg('--decision', 'approve');
const SHOTS = arg('--shots', path.join(process.env.TEMP || '.', `gss-e2e-${DECISION}`));
mkdirSync(SHOTS, { recursive: true });
const report = { decision: DECISION, checks: [], pageErrors: [], console: [] };
const norm = (s) => (s ?? '').replace(/\s+/g, ' ').trim();
let page;
async function check(name, fn) {
  const t0 = Date.now();
  try { const evidence = (await fn()) ?? null; report.checks.push({ name, ok: true, ms: Date.now() - t0, evidence }); }
  catch (e) {
    const shot = path.join(SHOTS, `FAIL-${report.checks.length}.png`); await page.screenshot({ path: shot }).catch(() => {});
    report.checks.push({ name, ok: false, ms: Date.now() - t0, error: String(e.message || e).split('\n')[0].slice(0, 300), shot });
  }
}
const shot = (n) => page.screenshot({ path: path.join(SHOTS, `${n}.png`) }).catch(() => {});

const browser = await chromium.launch();
page = await (await browser.newContext({ viewport: { width: 1360, height: 860 } })).newPage();
page.on('pageerror', (e) => report.pageErrors.push(String(e.message).slice(0, 240)));
page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) report.console.push(m.text().slice(0, 240)); });

await check('connect simulated system', async () => {
  await page.goto(WEB, { waitUntil: 'domcontentloaded' });
  const begin = page.locator('.system-card', { hasText: 'simulated' }).getByRole('button', { name: 'Begin séance' });
  await begin.waitFor({ timeout: 20000 });
  const connected = () => page.waitForFunction(
    () => [...document.querySelectorAll('header *')].some((el) => el.children.length === 0 && el.textContent.trim().toLowerCase() === 'connected'),
    null, { timeout: 8000 }).then(() => true, () => false);
  await begin.click();
  let clicks = 1;
  if (!(await connected())) { clicks = 2; await begin.click(); if (!(await connected())) throw new Error('still disconnected after 2 clicks'); }
  return { clicksNeeded: clicks };
});

let dlgText = '';
await check('proposal opens the modal: Deny focused, Approve delayed, gate facts, unverified agent text, screen drawn', async () => {
  const box = page.getByLabel('Message to the séance');
  await box.fill(DECISION === 'approve' ? 'Set premium to 300 for P0000003' : 'Set premium to 111 for P0000001');
  await box.press('Enter');
  const dlg = page.getByRole('alertdialog');
  await dlg.waitFor({ timeout: 30000 });
  dlgText = norm(await dlg.textContent());
  const approveDisabledAtOpen = await page.getByRole('button', { name: /^Approve/ }).isDisabled();
  const focus = await page.evaluate(() => (document.activeElement?.textContent || document.activeElement?.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim());
  const miniRows = await dlg.locator('.term-row').count();
  await shot('modal');
  const problems = [];
  if (!approveDisabledAtOpen) problems.push('Approve enabled at open');
  if (!/deny/i.test(focus)) problems.push(`initial focus "${focus}"`);
  if (!/unverified/i.test(dlgText)) problems.push('no "unverified" label');
  if (!/enter/i.test(dlgText)) problems.push('key not shown');
  const want = DECISION === 'approve' ? '300' : '111';
  if (!dlgText.includes(want)) problems.push(`new value ${want} not visible`);
  if (problems.length) throw new Error(problems.join('; '));
  return { focus, approveDisabledAtOpen, miniScreenRows: miniRows, modal: dlgText.slice(0, 420) };
});

await check('a synthetic (untrusted) click does NOT approve', async () => {
  await page.waitForTimeout(900);
  await page.getByRole('button', { name: /^Approve/ }).evaluate((b) => b.dispatchEvent(new MouseEvent('click', { bubbles: true })));
  await page.waitForTimeout(700);
  if (!(await page.getByRole('alertdialog').isVisible())) throw new Error('modal closed after an untrusted click');
});

await check(`${DECISION} resolves as expected`, async () => {
  if (DECISION === 'approve') {
    await page.getByRole('button', { name: /^Approve/ }).click();
    await page.getByText(/Approved\. The key was sent/).first().waitFor({ timeout: 20000 });
  } else {
    await page.keyboard.press('Escape');
    await page.getByText(/Denied\. Nothing was changed/).first().waitFor({ timeout: 20000 });
  }
  // The resolved outcome stays on screen until the user dismisses it (seance-ui REQ-017).
  const dismiss = page.getByRole('alertdialog').getByRole('button', { name: /dismiss|close/i });
  if (await dismiss.isVisible().catch(() => false)) await dismiss.click();
  await page.getByRole('alertdialog').waitFor({ state: 'detached', timeout: 10000 });
  await page.waitForTimeout(800);
  const row0 = norm(await page.locator('.term-row').first().textContent());
  const msg = norm(await page.locator('.term-row').nth(22).textContent());
  await shot('after');
  const log = norm(await page.locator('[role="log"]').first().textContent());
  return { screenTitle: row0, messageLine: msg, assistantTail: log.slice(-220) };
});

await check('audit drawer lists the decision', async () => {
  await page.getByRole('button', { name: 'Audit log' }).click();
  const drawer = page.getByRole('complementary', { name: 'Audit log' });
  await drawer.waitFor({ timeout: 10000 }); await page.waitForTimeout(600);
  const t = norm(await drawer.textContent());
  await shot('audit');
  const need = DECISION === 'approve' ? ['proposed', 'confirm_action', 'oob:web-ui'] : ['proposed', 'rejected'];
  const missing = need.filter((n) => !t.includes(n));
  if (missing.length) throw new Error(`missing: ${missing.join(', ')}`);
  return { chainBadge: (t.match(/Chain:[^A-Z]{0,30}[a-z ]+/) || [''])[0] };
});

await check('server audit agrees and the hash chain verifies', async () => {
  const a = await (await fetch(`${AGENT}/api/audit?limit=1000`, { headers: { Origin: WEB } })).json();
  const ok = a.entries.filter((e) => e.tool === 'confirm_action' && e.outcome === 'ok');
  const rej = a.entries.filter((e) => e.tool === 'deny_action' && e.outcome === 'rejected');
  if (!a.chain_ok) throw new Error(`chain broken at ${a.broken_seq}`);
  if (DECISION === 'approve' && (ok.length !== 1 || !/^oob:web-ui:/.test(ok[0].confirmed_by))) throw new Error(`confirmed=${ok.length} by=${ok[0]?.confirmed_by}`);
  if (DECISION === 'deny' && (ok.length !== 0 || rej.length !== 1)) throw new Error(`confirmed=${ok.length} denied=${rej.length}`);
  return { entries: a.entries.length, confirmed: ok.length, denied: rej.length, by: ok[0]?.confirmed_by ?? rej[0]?.confirmed_by };
});

report.ok = report.checks.every((c) => c.ok);
writeFileSync(path.join(SHOTS, 'report.json'), JSON.stringify(report, null, 2));
await browser.close();
process.exit(report.ok ? 0 : 1);
