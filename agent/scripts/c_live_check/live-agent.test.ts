/**
 * Agent D's live-mode check of Agent C's web client (task 8.2).
 *
 * Drives C's REAL pieces (WebSocketTransport, guards, reducer, RestClient) against a RUNNING
 * agent (`python -m seance_agent`) with the fake-insurance app. No browser, no mock data.
 *
 * Not part of either suite. To run it, copy this file into `web/test/` of a scratch checkout
 * of C's branch (never commit it there; `web/` is C's) and start the agent first:
 *
 *   $env:SEANCE_ALLOW_COMMIT = "1"; agent\.venv\Scripts\python.exe -m seance_agent
 *   cd web; npx vitest --run test/live-agent.test.ts --environment-options.jsdom.url=http://localhost:5173
 *
 * jsdom's WebSocket sends `Origin` from its document URL, which is why the URL option matters:
 * the agent refuses any Origin outside AGENT_ALLOWED_ORIGINS (4403).
 */
import { afterAll, describe, expect, it } from 'vitest';
import { WebSocketTransport } from '../src/protocol/wsTransport';
import { parseApps, parseAudit, parseSessionInfo, parseSpiritMap } from '../src/protocol/guards';
import { initialState, reduce, type AppState } from '../src/state/reducer';
import type { ClientMessage } from '../src/protocol/types';

const AGENT = process.env.AGENT_URL ?? 'http://127.0.0.1:8000';
const ORIGIN = 'http://localhost:5173';

let state: AppState = initialState();
const unknown: string[] = [];
const invalid: (string | null)[] = [];
let n = 0;
const send = (msg: Omit<ClientMessage, 'id'> & { id?: string }): boolean =>
  transport.send({ id: `t_${++n}`, ...msg } as ClientMessage);

const transport = new WebSocketTransport({
  agentUrl: AGENT,
  getResume: () => ({ sessionId: state.session.id, lastSeq: state.session.lastSeq }),
  // Node's WebSocket (undici) sends no Origin by default; a browser always does. Send the dev origin.
  createSocket: (url) => new (globalThis as any).WebSocket(url, { headers: { origin: ORIGIN } }),
  backoffMs: [200],
});
transport.subscribe({
  onEvent: (event) => {
    state = reduce(state, { type: 'server', event, at: Date.now() });
  },
  onUnknown: (t) => unknown.push(t),
  onInvalid: (t) => invalid.push(t),
  onStatus: (status) => {
    state = reduce(state, { type: 'connection', status });
  },
});

async function until(what: string, pred: () => boolean, ms = 8000): Promise<void> {
  const t0 = Date.now();
  while (!pred()) {
    if (Date.now() - t0 > ms) {
      const why = JSON.stringify({ connection: state.connection, session: state.session.state, id: state.session.id, lastSeq: state.session.lastSeq, invalid, unknown, confirmation: state.confirmation, turns: state.turnOrder.map((id) => [id, state.turns[id]?.status, state.turns[id]?.reason]), msgs: state.messages.slice(-4).map((x) => (x as any).text ?? (x as any).code) });
      throw new Error(`timed out waiting for ${what}: ${why}`);
    }
    await new Promise((r) => setTimeout(r, 25));
  }
}
/** A late client receives the whole session from seq 1 (old `connected` and snapshots included), so
 * "connected" can be seen mid-replay. Wait until the stream is quiet before acting. */
async function settle(quietMs = 300): Promise<void> {
  let last = -1;
  let since = Date.now();
  while (Date.now() - since < quietMs) {
    if (state.session.lastSeq !== last) {
      last = state.session.lastSeq;
      since = Date.now();
    }
    await new Promise((r) => setTimeout(r, 25));
  }
}
/** Snapshot before acting; the agent may replay earlier turns to a late client, so key on new ids. */
const mark = () => ({ turns: new Set(state.turnOrder), action: state.confirmation?.actionId ?? null });
const newTurnDone = (m: ReturnType<typeof mark>) =>
  state.turnOrder.some((id) => !m.turns.has(id) && state.turns[id]?.status === 'finished');
const newConfirmationOpen = (m: ReturnType<typeof mark>) =>
  state.confirmation?.phase === 'open' && state.confirmation.actionId !== m.action;

afterAll(() => transport.close());

describe('C web client against the real agent (fake-insurance)', () => {
  it('REST bodies satisfy C guards', async () => {
    const h = { headers: { origin: ORIGIN } };
    expect(parseSessionInfo(await (await fetch(`${AGENT}/api/session`, h)).json())).not.toBeNull();
    const apps = parseApps(await (await fetch(`${AGENT}/api/apps`, h)).json());
    expect(apps?.map((a) => a.app_id)).toContain('fake-insurance');
    expect(parseSpiritMap(await (await fetch(`${AGENT}/api/apps/fake-insurance/spirit-map`, h)).json())).not.toBeNull();
    expect(parseAudit(await (await fetch(`${AGENT}/api/audit?limit=50`, h)).json())).not.toBeNull();
  });

  it('hello, session_state and connect_system', async () => {
    transport.start();
    await until('first session_state', () => state.session.id !== null && state.connection === 'open');
    await settle();
    expect(state.session.controller).toBe(true);
    expect(send({ type: 'connect_system', app_id: 'fake-insurance' })).toBe(true);
    await until('connected + snapshot', () => state.session.state === 'connected' && state.screen !== null);
    await settle();
    expect(state.session.appId).toBe('fake-insurance');
    expect(state.session.tools.business).toBe(3);
  });

  it('a read turn streams, reduces and finishes', async () => {
    await settle();
    const m = mark();
    send({ type: 'user_message', text: 'Look up policy P0000003' });
    await until('turn finished', () => newTurnDone(m));
    const calls = Object.values(state.toolCalls);
    expect(calls.some((c) => c.tool === 'lookup_policy' && c.status === 'ok')).toBe(true);
    expect(JSON.stringify(state.messages)).toContain('A. ROSE');
    expect(state.focusQueue.length + (state.lastFill ? 1 : 0)).toBeGreaterThan(0);
  });

  it('a commit stops at the modal, then the controller approves', async () => {
    await settle();
    const m = mark();
    send({ type: 'user_message', text: 'Set the premium of policy P0000003 to 300' });
    await until('confirmation open', () => newConfirmationOpen(m));
    const c = state.confirmation!;
    expect(c.key).toBe('Enter');
    expect(state.screensById[c.screenId]).toBeDefined(); // the modal's miniature has a screen to draw
    expect(c.fieldSnapshot).toEqual([]); // review screen: all protected, per contracts 4.3
    send({ type: 'confirm_decision', action_id: c.actionId, decision: 'approve' } as never);
    await until('turn finished', () => newTurnDone(m));
    expect(state.confirmation?.outcome).toBe('approved');
    expect(state.confirmation?.confirmedBy).toMatch(/^oob:web-ui:/);
  });

  it('a deny leaves the system unchanged', async () => {
    await settle();
    const m = mark();
    send({ type: 'user_message', text: 'Set the premium of policy P0000004 to 0' });
    await until('confirmation open', () => newConfirmationOpen(m));
    send({ type: 'confirm_decision', action_id: state.confirmation!.actionId, decision: 'deny' } as never);
    await until('turn finished', () => newTurnDone(m));
    expect(state.confirmation?.outcome).toBe('denied');
  });

  it('reconnect with a fresh token resumes as controller without a resync', async () => {
    const seq = state.session.lastSeq;
    transport.requestResume();
    await until('reopened', () => state.connection === 'open');
    await until('new events', () => state.session.lastSeq > seq);
    expect(state.session.controller).toBe(true);
    expect(state.session.resynced).toBe(false);
  });

  it('nothing was dropped as unknown or invalid', () => {
    expect(invalid).toEqual([]);
    expect(unknown).toEqual([]);
    expect(state.observerOnly).toBe(false);
  });
});
