// Integrator ACCEPTANCE check (status-2026-11-08): one browser conversation, real stack.
//   web (VITE_MODE=live) -> agent (scripted model) -> in-process MCP -> fake-insurance
// In ONE session, with no reconnect between steps:
//   1. lookup_policy   "Look up policy P0000003"            -> A. ROSE, premium 250.00
//   2. list_policies   "List the policies"                   -> 8 policies P0000001..P0000008
//   3. update_policy   "Set the premium of policy P0000003 to 300" -> modal -> real Approve click
//      -> app says POLICY UPDATED; server audit: exactly 1 confirmed commit by oob:web-ui
//   4. lookup_policy   "Look up policy P0000003"            -> premium 300.00 (the change is real)
//   5. update_policy   "Set the premium of policy P0000001 to 111" -> modal -> Escape (Deny)
//      -> no new commit; 1 deny_action rejected; the fake app's data unchanged (step 6)
//   6. lookup_policy   "Look up policy P0000001"            -> still 180.00
// Each step also checks the tool that ran (step card) so a wrong tool cannot pass by luck.
// The agent must be started fresh before each run (the fake app is reseeded per agent process;
// scripts/e2e-accept.ps1 does that).
//
//   node scripts/e2e-accept.mjs [--web URL] [--agent URL] [--shots DIR]
// Prints one JSON line; writes DIR/report.json; exit 1 if any step failed.
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const require = createRequire(new URL('../web/package.json', import.meta.url));
const { chromium } = require('playwright');
const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : d; };
const WEB = arg('--web', 'http://127.0.0.1:5173');
const AGENT = arg('--agent', 'http://127.0.0.1:8000');
const SHOTS = arg('--shots', path.join(process.env.TEMP || '.', 'gss-accept'));
mkdirSync(SHOTS, { recursive: true });

const report = { started: new Date().toISOString(), steps: [], pageErrors: [], console: [] };
const norm = (s) => (s ?? '').replace(/\s+/g, ' ').trim();
let page;
let failed = false;

async function step(name, fn) {
  const t0 = Date.now();
  if (failed) { report.steps.push({ name, ok: false, skipped: true }); return; }
  try {
    const evidence = (await fn()) ?? null;
    report.steps.push({ name, ok: true, ms: Date.now() - t0, evidence });
  } catch (e) {
    failed = true;
    const shot = path.join(SHOTS, `FAIL-${report.steps.length}.png`);
    await page.screenshot({ path: shot }).catch(() => {});
    report.steps.push({ name, ok: false, ms: Date.now() - t0, error: String(e.message || e).split('\n')[0].slice(0, 300), shot });
  }
}

// The text of the assistant's turn that answers our n-th message: everything in the log after
// the n-th "YOU" block. Robust to markup: works on the log's text.
async function turnText(n) {
  // C's markup: <li class="msg msg-user"> for ours, then <li class="msg msg-assistant|msg-system">.
  return page.evaluate((k) => {
    const items = [...document.querySelectorAll('.chat-list > li.msg')];
    let seen = 0; const out = [];
    for (const li of items) {
      if (li.classList.contains('msg-user')) { seen += 1; continue; }
      if (seen === k) out.push(li.textContent || '');
    }
    return out.join(' ').replace(/\s+/g, ' ').trim();
  }, n);
}
let sent = 0;
async function ask(msg) {
  const box = page.getByLabel('Message to the séance');
  // The field is labelled by a <label>, not aria-label, so use Playwright's own checks.
  const t0 = Date.now();
  while (!(await box.isEnabled().catch(() => false))) {
    if (Date.now() - t0 > 30000) throw new Error('composer stayed disabled for 30 s');
    await page.waitForTimeout(150);
  }
  await box.fill(msg);
  await box.press('Enter');
  sent += 1;
  return sent;
}
// Wait until our n-th turn has finished: the composer is enabled again and the turn has text.
async function settled(n, re, timeout = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const t = await turnText(n);
    if (re.test(t)) return t;
    if (/That did not work/.test(t)) throw new Error(`tool failed: ${t.match(/That did not work[^.]*\./)?.[0] ?? t.slice(-160)}`);
    await page.waitForTimeout(150);
  }
  throw new Error(`timeout waiting for ${re} in turn ${n}: "${(await turnText(n)).slice(-200)}"`);
}
// The confirm screen drawn in the modal has "PREMIUM: <old> <new>" (contracts 10.1).
function premiumRow(text) {
  const m = /PREMIUM:\s+(\d+\.\d\d)\s+(\d+\.\d\d)/.exec(text);
  return m ? { old: m[1], new: m[2] } : null;
}
const serverAudit = async () => (await fetch(`${AGENT}/api/audit?limit=2000`, { headers: { Origin: WEB } })).json();
const commits = (a) => a.entries.filter((e) => e.tool === 'confirm_action' && e.outcome === 'ok');
const denials = (a) => a.entries.filter((e) => e.tool === 'deny_action' && e.outcome === 'rejected');

const browser = await chromium.launch();
page = await (await browser.newContext({ viewport: { width: 1360, height: 860 } })).newPage();
page.on('pageerror', (e) => report.pageErrors.push(String(e.message).slice(0, 240)));
page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) report.console.push(m.text().slice(0, 240)); });

await step('connect the simulated system', async () => {
  await page.goto(WEB, { waitUntil: 'domcontentloaded' });
  const begin = page.locator('.system-card', { hasText: 'simulated' }).getByRole('button', { name: 'Begin séance' });
  await begin.waitFor({ timeout: 20000 });
  await begin.click();
  await page.waitForFunction(
    () => [...document.querySelectorAll('header *')].some((el) => el.children.length === 0 && el.textContent.trim().toLowerCase() === 'connected'),
    null, { timeout: 15000 });
  const a = await serverAudit();
  if (commits(a).length) throw new Error('commits already present before the conversation (agent not fresh)');
});

await step('1 lookup_policy P0000003 -> A. ROSE, 250.00', async () => {
  const n = await ask('Look up policy P0000003');
  const t = await settled(n, /A\. ROSE.*250\.00/);
  if (!/lookup_policy/.test(t)) throw new Error('lookup_policy step card not shown');
  return { answer: t.slice(-140) };
});

await step('2 list_policies -> 8 policies (P0000001..P0000008)', async () => {
  const n = await ask('List the policies');
  const t = await settled(n, /P0000008/);
  if (!/list_policies/.test(t)) throw new Error('list_policies step card not shown');
  const found = [...new Set(t.match(/P000000[1-8]/g) || [])];
  if (found.length < 8) throw new Error(`only ${found.length} of 8 policies in the answer`);
  return { policies: found.length, answer: t.slice(-160) };
});

await step('3 update_policy P0000003 premium 300 -> modal -> Approve -> POLICY UPDATED, 1 commit', async () => {
  const n = await ask('Set the premium of policy P0000003 to 300');
  const dlg = page.getByRole('alertdialog');
  await dlg.waitFor({ timeout: 30000 });
  const m = norm(await dlg.textContent());
  await page.screenshot({ path: path.join(SHOTS, '3-modal.png') });
  // Act like a careful human: read the OLD/NEW premium off the drawn screen, approve only if right.
  const prem = premiumRow(m);
  const problems = [];
  if (!prem || prem.old !== '250.00' || prem.new !== '300.00') problems.push(`modal shows PREMIUM ${prem ? `${prem.old} -> ${prem.new}` : '(row not found)'}, expected 250.00 -> 300.00`);
  if (!/unverified/i.test(m)) problems.push('no unverified label');
  if (!(await page.getByRole('button', { name: /^Approve/ }).isDisabled())) problems.push('Approve enabled at open');
  if (problems.length) {
    await page.keyboard.press('Escape'); // never approve a change we did not ask for
    throw new Error(`refused to approve: ${problems.join('; ')}`);
  }
  await page.waitForTimeout(900);
  await page.getByRole('button', { name: /^Approve/ }).click();
  await page.getByText(/Approved\. The key was sent/).first().waitFor({ timeout: 20000 });
  const dismiss = dlg.getByRole('button', { name: /dismiss|close/i });
  if (await dismiss.isVisible().catch(() => false)) await dismiss.click();
  await dlg.waitFor({ state: 'detached', timeout: 10000 });
  await settled(n, /confirmed by you|Done\./);
  const msgLine = norm(await page.locator('.term-row').nth(22).textContent());
  const a = await serverAudit();
  const c = commits(a);
  if (c.length !== 1) throw new Error(`expected 1 commit, server has ${c.length}`);
  if (!/^oob:web-ui:/.test(c[0].confirmed_by)) throw new Error(`confirmed_by ${c[0].confirmed_by}`);
  if (!/POLICY UPDATED/.test(msgLine)) throw new Error(`message line "${msgLine}"`);
  return { messageLine: msgLine, confirmedBy: c[0].confirmed_by };
});

await step('4 lookup_policy P0000003 again -> premium 300.00 (the change is real)', async () => {
  const n = await ask('Look up policy P0000003');
  const t = await settled(n, /A\. ROSE.*premium 300\.00/);
  return { answer: t.slice(-140) };
});

let commitsBeforeDeny = 0;
await step('5 update_policy P0000001 premium 111 -> modal -> Escape (Deny) -> nothing sent', async () => {
  commitsBeforeDeny = commits(await serverAudit()).length;
  const n = await ask('Set the premium of policy P0000001 to 111');
  const dlg = page.getByRole('alertdialog');
  await dlg.waitFor({ timeout: 30000 });
  const prem = premiumRow(norm(await dlg.textContent()));
  await page.keyboard.press('Escape');
  if (!prem || prem.old !== '180.00' || prem.new !== '111.00') throw new Error(`modal showed PREMIUM ${prem ? `${prem.old} -> ${prem.new}` : '(row not found)'}, expected 180.00 -> 111.00 (denied anyway)`);
  await page.getByText(/Denied\. Nothing was changed/).first().waitFor({ timeout: 20000 });
  const dismiss = dlg.getByRole('button', { name: /dismiss|close/i });
  if (await dismiss.isVisible().catch(() => false)) await dismiss.click();
  await dlg.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
  await settled(n, /declined|Nothing was changed|unchanged/i);
  const a = await serverAudit();
  if (commits(a).length !== commitsBeforeDeny) throw new Error(`a commit was sent after Deny (${commits(a).length} vs ${commitsBeforeDeny})`);
  if (denials(a).length !== 1) throw new Error(`expected 1 denial, got ${denials(a).length}`);
  return { commits: commits(a).length, denials: denials(a).length };
});

await step('6 lookup_policy P0000001 -> still 180.00', async () => {
  const n = await ask('Look up policy P0000001');
  const t = await settled(n, /MARLOWE.*180\.00/);
  if (/111/.test(t.split(/Look up policy P0000001/).pop() || '')) throw new Error('premium 111 appears after Deny');
  return { answer: t.slice(-140) };
});

await step('server audit chain verifies; totals 1 commit, 1 denial', async () => {
  const a = await serverAudit();
  if (!a.chain_ok) throw new Error(`chain broken at ${a.broken_seq}`);
  if (commits(a).length !== 1 || denials(a).length !== 1) throw new Error(`commits=${commits(a).length} denials=${denials(a).length}`);
  return { entries: a.entries.length };
});

await page.screenshot({ path: path.join(SHOTS, 'end.png') }).catch(() => {});
report.ok = report.steps.every((s) => s.ok);
report.finished = new Date().toISOString();
writeFileSync(path.join(SHOTS, 'report.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ ok: report.ok, steps: report.steps.map((s) => `${s.ok ? 'PASS' : s.skipped ? 'SKIP' : 'FAIL'} ${s.name}${s.error ? ' -> ' + s.error : ''}`) }));
await browser.close();
process.exit(report.ok ? 0 : 1);
