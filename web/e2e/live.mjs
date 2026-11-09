// Task 7: the web UI in LIVE mode against Agent D's real service (scripted provider, fake-insurance). No mock data.
//   terminal 1: agent\.venv\Scripts\python.exe -m seance_agent   (LLM_PROVIDER=scripted, SEANCE_ALLOW_COMMIT=1)
//   terminal 2: cd web; $env:VITE_MODE='live'; npx vite --port 5173
//   terminal 3: cd web; node e2e/live.mjs
// It never touches the live container: the fake app has no 3270 session, and the agent refuses live hosts without
// GSS_LIVE_OK. Writes docs/handoff/c/shots/live-*.png and docs/handoff/c/shots/live-report.json. Exit 1 on any failure.
//
// One tab for the whole run: the agent reserves the controller seat for 60 s after a controller tab closes, so a new
// tab inside that window is an observer (by design, REQ-003). If this tab starts as an observer it waits that out.
// Between business tools it presses Reconnect (C-2): a fresh fake app on the menu, which also routes around B-1
// (spirit-map goto does not navigate home, so only the first business tool per session works).
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, '..', '..', 'docs', 'handoff', 'c', 'shots');
const WEB = process.env.WEB_URL ?? 'http://localhost:5173';
const AXE = readFileSync(join(here, '..', 'node_modules', 'axe-core', 'axe.min.js'), 'utf8');
mkdirSync(OUT, { recursive: true });

const report = { web: WEB, started: new Date().toISOString(), browser: null, checks: [], axe: {}, frames: { in: 0, types: {} }, ids: [], sent: [], pageErrors: [], consoleErrors: [] };
let page;
const check = async (name, fn) => {
  const t0 = Date.now();
  try {
    const evidence = await fn();
    report.checks.push({ name, ok: true, ms: Date.now() - t0, evidence: evidence ?? null });
    console.log('ok  ', name, evidence ? JSON.stringify(evidence).slice(0, 160) : '');
  } catch (e) {
    const shot = join(OUT, `live-FAIL-${report.checks.length}.png`);
    await page.screenshot({ path: shot }).catch(() => {});
    report.checks.push({ name, ok: false, ms: Date.now() - t0, error: String(e.message ?? e).split('\n')[0].slice(0, 300) });
    console.log('FAIL', name, String(e.message ?? e).split('\n')[0].slice(0, 200));
  }
};
const shot = (n) => page.screenshot({ path: join(OUT, `live-${n}.png`) });
const axe = async (name) => {
  await page.addScriptTag({ content: AXE });
  const v = await page.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'] })).violations.map((x) => ({ id: x.id, impact: x.impact, n: x.nodes.length, target: x.nodes[0]?.target.join(' ') })));
  report.axe[name] = v;
  if (v.length) throw new Error(`axe: ${v.map((x) => `${x.id}(${x.n}) ${x.target}`).join('; ')}`);
  return 'axe clean (colour contrast on)';
};
const composer = () => page.getByLabel('Message to the séance');
const composerReady = () => page.waitForFunction(() => !document.querySelector('#composer-input')?.disabled, null, { timeout: 30000 });
const assistantCount = () => page.locator('.msg-assistant').count();
async function ask(text) {
  await composerReady();
  const before = turnsDone();
  await composer().fill(text);
  await composer().press('Enter');
  return before;
}
// A turn is answered when the agent says so (turn_finished), not when a new message element appears: the element count
// is not reliable while the agent reuses message ids after a reconnect (finding 7.2-a).
const turnsDone = () => report.frames.types.turn_finished ?? 0;
const answered = async (beforeTurns, timeout = 30000) => {
  const t0 = Date.now();
  while (turnsDone() <= beforeTurns) {
    if (Date.now() - t0 > timeout) throw new Error('no turn_finished');
    await page.waitForTimeout(50);
  }
  await page.waitForFunction(() => !document.querySelector('.oia-lock[data-busy="true"]'), null, { timeout: 5000 });
};
async function reconnect() {
  const before = report.sent.filter((t) => t === 'connect_system').length;
  await page.getByRole('button', { name: 'Reconnect' }).click();
  await page.waitForFunction(() => document.querySelector('.header-state')?.textContent === 'connected', null, { timeout: 15000 });
  await composerReady();
  // the agent sends 'connected' just BEFORE the fresh screen snapshot: wait for the menu itself
  await page.waitForFunction(() => /MAIN MENU/.test(document.querySelector('.term-grid')?.textContent ?? ''), null, { timeout: 10000 });
  return report.sent.filter((t) => t === 'connect_system').length - before;
}

const browser = await chromium.launch();
report.browser = browser.version();
page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('pageerror', (e) => report.pageErrors.push(e.message));
page.on('console', (m) => m.type() === 'error' && report.consoleErrors.push(m.text().slice(0, 200)));
page.on('websocket', (ws) => {
  if (!ws.url().includes('/ws/seance')) return;
  ws.on('framesent', (f) => { try { report.sent.push(JSON.parse(f.payload).type); } catch {} });
  ws.on('framereceived', (f) => {
    try {
      const e = JSON.parse(f.payload);
      report.frames.in += 1;
      report.frames.types[e.type] = (report.frames.types[e.type] ?? 0) + 1;
      // Ids that the contract treats as unique per session (evidence for the 7.2 id-reuse finding).
      if (e.type === 'turn_started') report.ids.push(['turn', e.turn_id, e.seq]);
      if (e.type === 'tool_call') report.ids.push(['tool_call', e.data.tool_call_id, e.seq]);
      if (e.type === 'assistant_message') report.ids.push(['message', e.data.message_id, e.seq]);
      if (e.type === 'session_state') report.ids.push(['state', e.data.state, e.seq]);
    } catch {}
  });
});

await page.goto(WEB);

await check('7.1 live mode: no REPLAY badge, websocket up, this tab is the controller', async () => {
  await page.locator('.header-state').waitFor();
  expect(await page.locator('.header-replay').count() === 0, 'REPLAY badge shown in live mode');
  // Wait out the controller grace if a previous tab just closed. First let the controls render (the systems list
  // comes from REST and the controller flag from the websocket), THEN decide; deciding too early saw nothing.
  const controls = page.locator('.system-card button, .system-controls button');
  const isObserver = async () => {
    await controls.first().waitFor({ timeout: 15000 });
    await page.waitForTimeout(500);
    const why = await page.locator('#sys-ctl-reason, .connect-waiting').allTextContents();
    return why.some((t) => /Only the controller/.test(t));
  };
  for (let i = 0; i < 9 && (await isObserver()); i++) {
    console.log('     observer for now (agent controller grace); waiting 10 s and reloading');
    await page.waitForTimeout(10000);
    await page.reload();
    await page.locator('.header-state').waitFor();
  }
  expect(!(await isObserver()), 'still an observer after 90 s');
  const state = await page.locator('.header-state').textContent();
  return { state, sockets: report.frames.types.session_state ?? 0 };
});

await check('7.1 connect: Begin séance (fresh agent) or Reconnect (agent has history) -> connected, one connect_system', async () => {
  const begin = page.locator('.system-card', { hasText: 'simulated' }).getByRole('button', { name: 'Begin séance' });
  await shot('01-connect');
  await axe('connect');
  if (await begin.isVisible()) {
    await page.waitForFunction(() => !document.querySelector('.system-card button')?.disabled, null, { timeout: 15000 });
    await begin.click();
    await page.waitForFunction(() => document.querySelector('.header-state')?.textContent === 'connected', null, { timeout: 15000 });
    await composerReady();
    return { via: 'Begin séance', connectSent: report.sent.filter((t) => t === 'connect_system').length };
  }
  const n = await reconnect();
  expect(n === 1, `Reconnect sent ${n} connect_system`);
  return { via: 'Reconnect', connectSent: n };
});

await check('7.1 lookup: real screen data in the answer; planchette follows to POLNO and never shows OPTION over the enquiry screen (C-1)', async () => {
  const labels = [];
  const sampler = setInterval(async () => {
    const l = await page.locator('.planchette-label').textContent({ timeout: 100 }).catch(() => null);
    const grid = await page.locator('.term-grid').textContent({ timeout: 100 }).catch(() => '');
    if (l && labels[labels.length - 1]?.l !== l) labels.push({ l, onEnquiry: /POLICY ENQUIRY/.test(grid) });
  }, 40);
  const before = await ask('Look up policy P0000003');
  await page.waitForFunction(() => /filling|reading|pressing/.test(document.querySelector('.planchette-label')?.textContent ?? ''), null, { timeout: 15000 });
  await page.waitForTimeout(150);
  await shot('02-lookup-planchette');
  await answered(before);
  const answer = await page.locator('.msg-assistant').last().textContent();
  await page.waitForTimeout(3500); // last glide + rest hold
  clearInterval(sampler);
  expect(/A\. ROSE/.test(answer), `answer: ${answer.slice(0, 120)}`);
  expect(labels.some((x) => x.l === 'filling POLNO'), `labels: ${labels.map((x) => x.l).join(' > ')}`);
  expect(!labels.some((x) => x.l === 'filling OPTION' && x.onEnquiry), 'OPTION label shown over the enquiry screen');
  const rested = (await page.locator('.planchette').count()) === 0;
  expect(rested, 'planchette still visible 3.5 s after the turn ended');
  await shot('03-lookup-answer');
  await axe('lookup-answer');
  return { labels: labels.map((x) => x.l), rested, answer: answer.replace(/\s+/g, ' ').slice(0, 110) };
});

await check('7.1 spirit-map view: the current screen is highlighted', async () => {
  await page.getByRole('button', { name: 'Spirit-map' }).click();
  await page.locator('.spirit-map').waitFor();
  const here = await page.locator('.node-here').count();
  expect(here === 1, `${here} nodes marked "you are here"`);
  await page.waitForTimeout(300);
  const nodes = await page.locator('.map-node').count();
  await shot('04-spirit-map');
  await axe('spirit-map');
  await page.getByRole('button', { name: 'Screen', exact: true }).first().click();
  return { nodes, here };
});

await check('7.1 C-2: Reconnect sends exactly one connect_system and lands on the menu', async () => {
  const n = await reconnect();
  expect(n === 1, `${n} connect_system sent`);
  const grid = await page.locator('.term-grid').textContent();
  expect(/MAIN MENU/.test(grid), 'not on the menu after reconnect');
  return { connectSent: n };
});

let approveOk = false;
await check('7.1 commit + Approve: modal shows the gate facts and the confirm screen; a script click is refused; a real click approves once', async () => {
  const before = await ask('Set the premium of policy P0000003 to 300');
  const dialog = page.getByRole('alertdialog');
  await dialog.waitFor({ timeout: 30000 });
  const focus = await page.evaluate(() => document.activeElement?.textContent);
  const disabledAtOpen = await page.getByRole('button', { name: /^Approve/ }).isDisabled();
  const mini = await dialog.locator('.mini-screen').textContent();
  const agent = await dialog.getByTestId('agent-block').textContent().catch(() => '');
  const inert = await page.evaluate(() => document.querySelector('.app')?.hasAttribute('inert'));
  await page.waitForTimeout(800);
  await shot('05-confirmation-modal');
  await axe('confirmation-modal');
  const sentBefore = report.sent.filter((t) => t === 'confirm_decision').length;
  await page.evaluate(() => document.querySelector('.btn-approve')?.click());
  await page.waitForTimeout(400);
  const scriptRefused = report.sent.filter((t) => t === 'confirm_decision').length === sentBefore && (await dialog.isVisible());
  await page.getByRole('button', { name: /^Approve/ }).click();
  await dialog.getByText(/Approved\. The key was sent/).waitFor({ timeout: 20000 });
  const decisions = report.sent.filter((t) => t === 'confirm_decision').length - sentBefore;
  await shot('06-approved');
  await page.getByRole('button', { name: 'Dismiss' }).click();
  await answered(before);
  expect(focus === 'Deny', `initial focus on ${focus}`);
  expect(disabledAtOpen, 'Approve enabled at open');
  expect(/CONFIRM/.test(mini), 'mini-screen does not show the confirm screen');
  expect(/unverified/i.test(agent), 'agent text not in its unverified block');
  expect(inert, 'app not inert while the dialog is open');
  expect(scriptRefused, 'a script-dispatched click approved');
  expect(decisions === 1, `${decisions} confirm_decision sent`);
  approveOk = true;
  return { focus, disabledAtOpen, scriptRefused, decisions, screen: /POLICY UPDATED/.test(await page.locator('.term-grid').textContent()) ? 'POLICY UPDATED' : 'other' };
});

await check('7.1 commit + Deny (Esc): denied, and nothing approved', async () => {
  await reconnect();
  const before = await ask('Set the premium of policy P0000003 to 300');
  const dialog = page.getByRole('alertdialog');
  await dialog.waitFor({ timeout: 30000 });
  await page.keyboard.press('Escape');
  await dialog.getByText(/Denied\. Nothing was changed/).waitFor({ timeout: 20000 });
  await page.getByRole('button', { name: 'Dismiss' }).click();
  await answered(before);
  return 'denied';
});

await check('7.1 audit drawer: live entries incl. the oob confirmation, honest chain badge', async () => {
  await page.getByRole('button', { name: 'Audit log' }).click();
  const drawer = page.getByRole('complementary', { name: 'Audit log' });
  await drawer.waitFor();
  await page.waitForFunction(() => document.querySelectorAll('.audit-table tbody tr').length > 3, null, { timeout: 10000 });
  const text = await drawer.textContent();
  const rows = await drawer.locator('tbody tr').count();
  const chain = await drawer.getByTestId('chain-status').textContent();
  await shot('07-audit-drawer');
  await axe('audit-drawer');
  await page.keyboard.press('Escape');
  if (approveOk) expect(/oob:web-ui:/.test(text), 'no oob:web-ui confirmation in the audit');
  return { rows, chain, hasOob: /oob:web-ui:/.test(text), hasRejected: /rejected/.test(text) };
});

await check('7.2 protocol: only the six contract client messages were sent; no page or console errors', async () => {
  const allowed = new Set(['hello', 'connect_system', 'user_message', 'confirm_decision', 'cancel_turn', 'ping']);
  const bad = report.sent.filter((t) => !allowed.has(t));
  expect(bad.length === 0, `sent non-contract messages: ${bad.join(',')}`);
  expect(report.pageErrors.length === 0, `page errors: ${report.pageErrors.join(' | ')}`);
  expect(report.consoleErrors.length === 0, `console errors: ${report.consoleErrors.join(' | ')}`);
  return { sent: report.sent.reduce((a, t) => ((a[t] = (a[t] ?? 0) + 1), a), {}), framesIn: report.frames.in };
});

await browser.close();
report.finished = new Date().toISOString();
writeFileSync(join(OUT, 'live-report.json'), JSON.stringify(report, null, 2));
const failed = report.checks.filter((c) => !c.ok);
console.log(`${report.checks.length - failed.length}/${report.checks.length} checks passed`);
process.exit(failed.length ? 1 : 0);

function expect(cond, msg) {
  if (!cond) throw new Error(msg);
}
