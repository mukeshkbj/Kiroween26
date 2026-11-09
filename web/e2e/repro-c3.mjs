// C-3 repro record (integrator finding: a "Begin séance" click right after load sometimes did nothing).
// Run against the live stack: agent :8000 that already has history, vite in live mode on :5173. Takes about 90 s.
//   node e2e/repro-c3.mjs     (N=6 fresh tabs by default; env N to change)
// Results of the 2026-11-08 run are in docs/handoff/c/response-integrator-e2e-findings.md.
// Part 1: back-to-back fresh tabs. Per tab: websockets opened in 3 s (storm check), controller flag, and what the
//         "Begin séance" / "Reconnect" controls say. Old code: a new socket every ~30 ms and a clickable dead button.
// Part 2: one tab after the agent's 60 s controller grace has run out: it must be the controller and connect.
import { chromium } from 'playwright';

const N = Number(process.env.N ?? 6);
const b = await chromium.launch();

async function tab(label) {
  const ctx = await b.newContext();
  const page = await ctx.newPage();
  let sockets = 0;
  const states = [];
  page.on('websocket', (ws) => {
    if (!ws.url().includes('/ws/seance')) return;
    sockets += 1;
    ws.on('framereceived', (f) => {
      try {
        const e = JSON.parse(f.payload);
        if (e.type === 'session_state') states.push(`${e.data.state}/controller=${e.data.controller}`);
        if (e.type === 'error') states.push(`error:${e.data.code}`);
      } catch {}
    });
  });
  await page.goto('http://localhost:5173/');
  await page.waitForTimeout(3000);
  const begin = page.locator('.system-card', { hasText: 'simulated' }).getByRole('button', { name: 'Begin séance' });
  const reconnect = page.getByRole('button', { name: 'Reconnect' });
  const r = {
    label,
    socketsIn3s: sockets,
    states: states.join(' '),
    header: await page.locator('.header-state').textContent(),
    begin: (await begin.isVisible()) ? (await begin.isEnabled() ? 'enabled' : 'disabled') : 'hidden',
    reconnect: (await reconnect.isVisible()) ? (await reconnect.isEnabled() ? 'enabled' : 'disabled') : 'hidden',
    reason: (await page.locator('#sys-ctl-reason, .connect-waiting').first().textContent().catch(() => null)) ?? null,
  };
  return { r, page, ctx, begin, reconnect };
}

const rows = [];
for (let i = 0; i < N; i++) {
  const t = await tab(`fresh tab ${i + 1}`);
  rows.push(t.r);
  await t.ctx.close();
}
console.log(JSON.stringify({ part: 1, rows }, null, 1));

console.log('waiting 65 s for the controller grace to run out...');
await new Promise((r) => setTimeout(r, 65_000));
const t = await tab('after grace');
let outcome = 'no control to use';
if (t.r.reconnect === 'enabled') {
  await t.reconnect.click();
  await t.page.waitForFunction(() => document.querySelector('.header-state')?.textContent === 'connected' && !document.querySelector('#composer-input')?.disabled, null, { timeout: 15000 }).then(() => (outcome = 'Reconnect -> connected, composer usable'), () => (outcome = 'Reconnect clicked, did not reach connected'));
} else if (t.r.begin === 'enabled') {
  await t.begin.click();
  await t.page.waitForFunction(() => document.querySelector('.header-state')?.textContent === 'connected', null, { timeout: 15000 }).then(() => (outcome = 'Begin -> connected'), () => (outcome = 'Begin clicked, did not connect'));
}
console.log(JSON.stringify({ part: 2, row: t.r, outcome }, null, 1));
await t.ctx.close();
await b.close();
