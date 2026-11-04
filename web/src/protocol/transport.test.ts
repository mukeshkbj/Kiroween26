import { describe, expect, it } from 'vitest';
import { ReplayTransport } from './replayTransport';
import { BACKOFF_MS, CLOSE_FORBIDDEN_ORIGIN, WebSocketTransport, wsUrlFor, type WebSocketLike } from './wsTransport';
import type { Timer, TransportHandlers } from './transport';
import type { ClientMessage, ServerEvent } from './types';
import type { ConnectionStatus } from '../state/reducer';
import { loadExamples } from '../../test/examples';

const ex = loadExamples();

// ---- manual clock ------------------------------------------------------------

class ManualClock {
  now = 0;
  private tasks: { at: number; fn: () => void; id: number }[] = [];
  private n = 0;
  timer: Timer = (fn, ms) => {
    const id = ++this.n;
    this.tasks.push({ at: this.now + ms, fn, id });
    return () => {
      this.tasks = this.tasks.filter((t) => t.id !== id);
    };
  };
  get pending(): number {
    return this.tasks.length;
  }
  /** Advance time, firing due tasks in order (tasks may schedule more). */
  advance(ms: number) {
    const end = this.now + ms;
    for (;;) {
      const due = this.tasks.filter((t) => t.at <= end).sort((a, b) => a.at - b.at || a.id - b.id)[0];
      if (!due) break;
      this.tasks = this.tasks.filter((t) => t !== due);
      this.now = due.at;
      due.fn();
    }
    this.now = end;
  }
  nextDelay(): number | null {
    const t = this.tasks.slice().sort((a, b) => a.at - b.at)[0];
    return t ? t.at - this.now : null;
  }
}

function recorder() {
  const events: ServerEvent[] = [];
  const unknown: string[] = [];
  const invalid: (string | null)[] = [];
  const statuses: ConnectionStatus[] = [];
  const details: (string | undefined)[] = [];
  const h: TransportHandlers = {
    onEvent: (e) => events.push(e),
    onUnknown: (t) => unknown.push(t),
    onInvalid: (t) => invalid.push(t),
    onStatus: (s, d) => {
      statuses.push(s);
      details.push(d);
    },
  };
  return { h, events, unknown, invalid, statuses, details };
}

// ---- fake websocket -----------------------------------------------------------

class FakeSocket implements WebSocketLike {
  readyState = 0;
  sent: string[] = [];
  closedWith: number | undefined;
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code: number }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  constructor(readonly url: string) {}
  send(d: string) {
    this.sent.push(d);
  }
  close(code?: number) {
    this.closedWith = code;
    this.readyState = 3;
  }
  // test helpers
  open() {
    this.readyState = 1;
    this.onopen?.({});
  }
  receive(data: unknown) {
    this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) });
  }
  drop(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}

async function flush() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

function liveRig(over: { sessionId?: string; lastSeq?: number; sessionKnown?: string | null; fail?: () => boolean } = {}) {
  const clock = new ManualClock();
  const sockets: FakeSocket[] = [];
  let sessions = 0;
  const resume = { sessionId: over.sessionKnown ?? null, lastSeq: over.lastSeq ?? 0 };
  const t = new WebSocketTransport({
    agentUrl: 'http://127.0.0.1:8000',
    timer: clock.timer,
    getResume: () => resume,
    fetchSession: async () => {
      sessions += 1;
      if (over.fail?.()) throw new Error('down');
      return { token: 'tok_secret', session_id: over.sessionId ?? 's_01', v: 1 };
    },
    createSocket: (url) => {
      const s = new FakeSocket(url);
      sockets.push(s);
      return s;
    },
    newId: (() => {
      let n = 0;
      return () => `h_${++n}`;
    })(),
  });
  const rec = recorder();
  t.subscribe(rec.h);
  return { t, clock, sockets, rec, resume, sessions: () => sessions };
}

const pong = (seq: number): ServerEvent => ({ v: 1, type: 'pong', seq, ts: 't', session_id: 's_01', turn_id: null, data: {} });

describe('WebSocketTransport (REQ-011)', () => {
  it('derives the ws url from the http base', () => {
    expect(wsUrlFor('http://127.0.0.1:8000')).toBe('ws://127.0.0.1:8000/ws/seance');
    expect(wsUrlFor('https://agent.example')).toBe('wss://agent.example/ws/seance');
  });

  it('fetches a session, opens the socket and sends hello first with the token and resume_from null', async () => {
    const r = liveRig();
    r.t.start();
    expect(r.rec.statuses).toEqual(['connecting']);
    await flush();
    const s = r.sockets[0] as FakeSocket;
    expect(s.url).toBe('ws://127.0.0.1:8000/ws/seance');
    s.open();
    expect(s.sent).toHaveLength(1);
    expect(JSON.parse(s.sent[0] as string)).toEqual({
      id: 'h_1', type: 'hello', v: 1, client: 'seance-web/0.1.0', token: 'tok_secret', resume_from: null,
    });
    expect(r.rec.statuses.at(-1)).toBe('open');
  });

  it('never puts the token in the url', async () => {
    const r = liveRig();
    r.t.start();
    await flush();
    expect((r.sockets[0] as FakeSocket).url).not.toContain('tok_');
  });

  it('passes valid events on, reports unknown types, drops garbage without throwing', async () => {
    const r = liveRig();
    r.t.start();
    await flush();
    const s = r.sockets[0] as FakeSocket;
    s.open();
    s.receive(pong(1));
    s.receive({ v: 1, type: 'brand_new', seq: 2, ts: 't', session_id: 's_01', turn_id: null, data: {} });
    s.receive('{not json');
    s.receive({ v: 1, type: 'thinking', seq: 3, ts: 't', session_id: 's_01', turn_id: null, data: { summary: 7 } });
    s.receive(new ArrayBuffer(2) as unknown as string);
    expect(r.rec.events.map((e) => e.type)).toEqual(['pong']);
    expect(r.rec.unknown).toEqual(['brand_new']);
    expect(r.rec.invalid.length).toBe(3);
  });

  it('sends client messages only when open, never queues, never retries', async () => {
    const r = liveRig();
    const msg: ClientMessage = { id: 'u_1', type: 'user_message', text: 'hi' };
    expect(r.t.send(msg)).toBe(false); // not started
    r.t.start();
    await flush();
    const s = r.sockets[0] as FakeSocket;
    expect(r.t.send(msg)).toBe(false); // socket not open yet
    s.open();
    expect(r.t.send(msg)).toBe(true);
    expect(s.sent).toHaveLength(2); // hello + message
    s.drop();
    expect(r.t.send(msg)).toBe(false);
    // reconnect happens, but the earlier message is NOT replayed
    r.clock.advance(1000);
    await flush();
    (r.sockets[1] as FakeSocket).open();
    expect((r.sockets[1] as FakeSocket).sent.map((x) => JSON.parse(x).type)).toEqual(['hello']);
  });

  it('refuses to send hello from outside', async () => {
    const r = liveRig();
    r.t.start();
    await flush();
    (r.sockets[0] as FakeSocket).open();
    expect(r.t.send({ id: 'x', type: 'hello', v: 1, client: 'c', token: 't', resume_from: null })).toBe(false);
  });

  it('reconnects with backoff 1s, 2s, 4s, 8s, then 15s and shows a reconnecting status', async () => {
    let up = false;
    const r = liveRig({ fail: () => !up });
    r.t.start();
    const delays: number[] = [];
    for (let i = 0; i < 7; i++) {
      await flush();
      delays.push(r.clock.nextDelay() as number);
      r.clock.advance(r.clock.nextDelay() as number);
    }
    expect(delays).toEqual([1000, 2000, 4000, 8000, 15000, 15000, 15000]);
    expect(BACKOFF_MS.at(-1)).toBe(15000);
    expect(r.rec.statuses).toContain('reconnecting');
    expect(r.sockets).toHaveLength(0);
    up = true;
    await flush();
    r.clock.advance(15000);
    await flush();
    expect(r.sockets).toHaveLength(1);
  });

  it('resumes from the last applied seq when the session id is unchanged', async () => {
    const r = liveRig({ sessionKnown: 's_01', lastSeq: 42 });
    r.t.start();
    await flush();
    (r.sockets[0] as FakeSocket).open();
    expect(JSON.parse((r.sockets[0] as FakeSocket).sent[0] as string).resume_from).toBe(42);
  });

  it('starts fresh (resume_from null) when the agent has a new session id', async () => {
    const r = liveRig({ sessionKnown: 's_OLD', lastSeq: 42, sessionId: 's_NEW' });
    r.t.start();
    await flush();
    (r.sockets[0] as FakeSocket).open();
    expect(JSON.parse((r.sockets[0] as FakeSocket).sent[0] as string).resume_from).toBeNull();
  });

  it('after a drop it reconnects and resets the backoff once a valid event arrives', async () => {
    const r = liveRig();
    r.t.start();
    await flush();
    const a = r.sockets[0] as FakeSocket;
    a.open();
    a.receive(pong(1));
    a.drop();
    expect(r.rec.statuses.at(-1)).toBe('reconnecting');
    expect(r.clock.nextDelay()).toBe(1000);
    r.clock.advance(1000);
    await flush();
    const b = r.sockets[1] as FakeSocket;
    b.open();
    b.drop(); // dropped before any valid event: backoff keeps growing
    expect(r.clock.nextDelay()).toBe(2000);
    r.clock.advance(2000);
    await flush();
    const c = r.sockets[2] as FakeSocket;
    c.open();
    c.receive(pong(2));
    c.drop();
    expect(r.clock.nextDelay()).toBe(1000); // reset by the valid event
  });

  it('does not retry when the origin is forbidden (4403)', async () => {
    const r = liveRig();
    r.t.start();
    await flush();
    const s = r.sockets[0] as FakeSocket;
    s.open();
    s.drop(CLOSE_FORBIDDEN_ORIGIN);
    expect(r.rec.statuses.at(-1)).toBe('closed');
    expect(r.rec.details.at(-1)).toBe('forbidden_origin');
    expect(r.clock.pending).toBe(0);
  });

  it('ignores events from a socket that has been replaced', async () => {
    const r = liveRig();
    r.t.start();
    await flush();
    const a = r.sockets[0] as FakeSocket;
    a.open();
    r.t.requestResume();
    await flush();
    const b = r.sockets[1] as FakeSocket;
    expect(a.closedWith).toBe(1000);
    a.receive(pong(1)); // stale socket
    expect(r.rec.events).toHaveLength(0);
    b.open();
    b.receive(pong(1));
    expect(r.rec.events).toHaveLength(1);
  });

  it('close() stops everything', async () => {
    const r = liveRig();
    r.t.start();
    await flush();
    (r.sockets[0] as FakeSocket).open();
    r.t.close();
    expect(r.rec.statuses.at(-1)).toBe('closed');
    expect(r.t.send({ id: 'p', type: 'ping' })).toBe(false);
    expect(r.clock.pending).toBe(0);
  });
});

// ---- replay -------------------------------------------------------------------

function replay(name: string, speed = 1) {
  const clock = new ManualClock();
  const t = new ReplayTransport({ lines: ex.transcripts[name] ?? [], timer: clock.timer, speed });
  const rec = recorder();
  t.subscribe(rec.h);
  return { t, clock, rec };
}

describe('ReplayTransport (REQ-023)', () => {
  it('plays until the first client action, then waits', () => {
    const r = replay('lookup');
    r.t.start();
    r.clock.advance(100_000);
    // the first session_state, then it waits for connect_system
    expect(r.rec.events.map((e) => e.type)).toEqual(['session_state']);
    expect(r.t.expecting()?.type).toBe('connect_system');
    expect(r.rec.statuses).toEqual(['open']);
  });

  it('honours the recorded delays, scaled by speed', () => {
    const r = replay('lookup', 2);
    r.t.start();
    r.clock.advance(39); // delay_ms 80 / 2 = 40
    expect(r.rec.events).toHaveLength(0);
    r.clock.advance(1);
    expect(r.rec.events).toHaveLength(1);
  });

  it('plays the whole lookup transcript as the user acts, in recorded order', () => {
    const r = replay('lookup');
    r.t.start();
    r.clock.advance(100_000);
    expect(r.t.send({ id: 'u_01', type: 'connect_system', app_id: 'fake-insurance' })).toBe(true);
    r.clock.advance(100_000);
    expect(r.t.expecting()?.type).toBe('user_message');
    expect(r.t.send({ id: 'u_02', type: 'user_message', text: 'whatever the user typed' })).toBe(true);
    r.clock.advance(100_000);
    expect(r.t.expecting()).toBeNull();
    expect(r.t.finished).toBe(true);
    const seqs = r.rec.events.map((e) => e.seq);
    expect(seqs).toEqual([...seqs].sort((a, b) => a - b));
    expect(r.rec.events.at(-1)?.type).toBe('turn_finished');
    expect(r.rec.invalid).toEqual([]);
    expect(r.rec.unknown).toEqual([]);
  });

  it('rejects messages the script is not waiting for', () => {
    const r = replay('lookup');
    r.t.start();
    r.clock.advance(100_000);
    expect(r.t.send({ id: 'u_x', type: 'user_message', text: 'too early' })).toBe(false);
    expect(r.t.rejected).toHaveLength(1);
    expect(r.t.expecting()?.type).toBe('connect_system');
  });

  it('a scripted deny cannot be advanced by pressing approve', () => {
    const r = replay('commit-deny');
    r.t.start();
    const drive = () => r.clock.advance(100_000);
    drive();
    while (r.t.expecting() && r.t.expecting()?.type !== 'confirm_decision') {
      const want = r.t.expecting() as ClientMessage;
      r.t.send({ ...want, id: 'z' } as ClientMessage);
      drive();
    }
    const want = r.t.expecting();
    expect(want).toMatchObject({ type: 'confirm_decision', decision: 'deny' });
    const actionId = (want as Extract<ClientMessage, { type: 'confirm_decision' }>).action_id;
    expect(r.t.send({ id: 'd1', type: 'confirm_decision', action_id: actionId, decision: 'approve' })).toBe(false);
    expect(r.t.expecting()).not.toBeNull();
    expect(r.t.send({ id: 'd2', type: 'confirm_decision', action_id: actionId, decision: 'deny' })).toBe(true);
    drive();
    expect(r.rec.events.some((e) => e.type === 'confirmation_resolved' && e.data.outcome === 'denied')).toBe(true);
  });

  it.each(['lookup', 'commit-approve', 'commit-deny', 'commit-expire', 'injection', 'session-lost', 'read-only'])(
    '%s plays to the end by performing the scripted actions, with every event accepted',
    (name) => {
      const r = replay(name);
      r.t.start();
      for (let guard = 0; guard < 50; guard++) {
        r.clock.advance(1_000_000);
        const want = r.t.expecting();
        if (!want) break;
        expect(r.t.send(want)).toBe(true);
      }
      r.clock.advance(1_000_000);
      expect(r.t.finished).toBe(true);
      expect(r.rec.invalid).toEqual([]);
      expect(r.rec.unknown).toEqual([]);
      const expected = (ex.transcripts[name] ?? []).filter((l) => l.dir === 'server').length;
      expect(r.rec.events).toHaveLength(expected);
    },
  );

  it('close() cancels playback', () => {
    const r = replay('lookup');
    r.t.start();
    r.t.close();
    r.clock.advance(100_000);
    expect(r.rec.events).toHaveLength(0);
    expect(r.rec.statuses.at(-1)).toBe('closed');
  });
});
