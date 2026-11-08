import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import fc from 'fast-check';
import { AppShell } from '../AppShell';
import { StoreProvider } from '../state/store';
import { MAX_RESUMES_WITHOUT_PROGRESS } from '../state/store';
import { AnnouncerProvider } from '../a11y/Announcer';
import { initialState, reduce } from '../state/reducer';
import type { RestApi } from '../protocol/mock';
import { parseApps } from '../protocol/guards';
import type { Transport, TransportHandlers } from '../protocol/transport';
import type { ClientMessage, ServerEvent } from '../protocol/types';
import type { ConnectionStatus } from '../state/reducer';
import { loadExamples } from '../../test/examples';
import { expectNoViolations } from '../../test/axe';

/**
 * Integrator findings 2026-11-06:
 *  C-2 no way to change or reconnect the system once connected -> header "Change system" and "Reconnect".
 *  C-3 a "Begin séance" click right after load sometimes did nothing. Live probe: a fresh page against an agent with
 *      history looped hello -> resume -> hello about every 30 ms (the reducer demanded seq 1), and a click in that
 *      window was refused by the transport and dropped silently. Fixed in the reducer; guarded here.
 */

const ex = loadExamples();
const apps = parseApps(ex.rest['apps'])!;
const rest: RestApi = { apps: async () => apps, audit: async () => ({ entries: [], chain_ok: true, broken_seq: null }), spiritMap: async () => null };

class SpyTransport implements Transport {
  readonly kind = 'live' as const;
  sent: ClientMessage[] = [];
  resumes = 0;
  accept = true;
  private h: TransportHandlers | null = null;
  subscribe(h: TransportHandlers) {
    this.h = h;
    return () => (this.h = null);
  }
  start() {}
  send(m: ClientMessage) {
    if (!this.accept) return false;
    this.sent.push(m);
    return true;
  }
  requestResume() {
    this.resumes += 1;
  }
  close() {}
  status(s: ConnectionStatus) {
    act(() => this.h?.onStatus(s));
  }
  emit(...es: ServerEvent[]) {
    act(() => {
      for (const e of es) this.h?.onEvent(e);
    });
  }
  private acked = new Set<string>();
  /** Answer like D does, all in ONE batch: ack every unanswered connect_system, then connecting -> connected. */
  answer() {
    const acks = this.sent.filter((m) => m.type === 'connect_system' && !this.acked.has(m.id)).map((m) => {
      this.acked.add(m.id);
      return ack(m.id);
    });
    this.emit(...acks, st('connecting'), st('connected'));
  }
}

let seq = 100; // the agent has history: nothing here starts at seq 1
const st = (state: string, over: Record<string, unknown> = {}): ServerEvent =>
  ({
    v: 1, type: 'session_state', seq: ++seq, ts: 't', session_id: 's_01', turn_id: null,
    data: { state, app_id: state === 'disconnected' ? null : 'fake-insurance', read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true }, tools: { business: 3, generic: 4 }, resync: false, controller: true, ...over },
  }) as ServerEvent;
const ack = (ref: string): ServerEvent => ({ v: 1, type: 'ack', seq: ++seq, ts: 't', session_id: 's_01', turn_id: null, data: { ref } }) as ServerEvent;
const turn = (type: 'turn_started' | 'turn_finished'): ServerEvent =>
  ({ v: 1, type, seq: ++seq, ts: 't', session_id: 's_01', turn_id: 't_1', data: type === 'turn_started' ? { user_message_id: 'm' } : { reason: 'completed', usage: null } }) as ServerEvent;

beforeEach(() => {
  seq = 100;
  (window as unknown as { matchMedia: unknown }).matchMedia = (q: string) => ({ matches: q.includes('min-width'), media: q, addEventListener() {}, removeEventListener() {} });
  (Element.prototype as unknown as { animate: unknown }).animate = () => ({ addEventListener() {}, removeEventListener() {}, cancel() {}, finish() {} });
});
afterEach(() => {
  delete (window as unknown as { matchMedia?: unknown }).matchMedia;
});

function mount() {
  const t = new SpyTransport();
  render(
    <AnnouncerProvider>
      <StoreProvider transport={t} now={() => 0}>
        <AppShell rest={rest} replay={false} now={() => 0} />
      </StoreProvider>
    </AnnouncerProvider>,
  );
  return t;
}
const connects = (t: SpyTransport) => t.sent.filter((m) => m.type === 'connect_system');
const simulatedBegin = () =>
  within(screen.getByText('Seance Insurance (simulated)').closest('.system-card') as HTMLElement).getByRole('button', { name: 'Begin séance' });

describe('C-3: the reconnect storm and the lost first click', () => {
  it('a fresh client accepts the server\'s current session_state at a high seq: no resume request at all', () => {
    let s = reduce(initialState(), { type: 'connection', status: 'open' });
    s = reduce(s, { type: 'server', event: st('disconnected'), at: 0 });
    expect(s.needsResume).toBe(false);
    expect(s.session.lastSeq).toBe(101);
    expect(s.helloAcked).toBe(true);
  });

  it('a page load against an agent with history never asks the transport to resume (it used to loop)', async () => {
    const t = mount();
    t.status('open');
    t.emit(st('disconnected'));
    await screen.findAllByRole('button', { name: 'Begin séance' });
    expect(t.resumes).toBe(0);
  });

  it('"Begin séance" is disabled until the agent has answered this connection\'s hello, with the reason shown', async () => {
    const t = mount();
    t.status('open'); // socket open, hello sent, no answer yet
    await screen.findAllByRole('button', { name: 'Begin séance' });
    expect(simulatedBegin()).toBeDisabled();
    expect(screen.getByText(/Waiting for the agent to answer/)).toBeInTheDocument();
    t.emit(st('disconnected'));
    await waitFor(() => expect(simulatedBegin()).toBeEnabled());
    await userEvent.setup().click(simulatedBegin());
    expect(connects(t)).toHaveLength(1);
  });

  it('an observer tab (e.g. a reload inside the agent 60 s controller grace) sees the buttons disabled with that reason, not a dead button', async () => {
    const t = mount();
    t.status('open');
    t.emit(st('disconnected', { controller: false }));
    await screen.findAllByRole('button', { name: 'Begin séance' });
    expect(simulatedBegin()).toBeDisabled();
    expect(within(document.querySelector('.connect') as HTMLElement).getByText(/Only the controller can change or reconnect/)).toBeInTheDocument();
    expect(screen.queryByText(/Waiting for the agent to answer/)).toBeNull();
    expect(t.sent).toHaveLength(0);
  });

  it('every new socket needs its own answer: a reconnect disables the buttons again', async () => {
    const t = mount();
    t.status('open');
    t.emit(st('disconnected'));
    await waitFor(() => expect(simulatedBegin()).toBeEnabled());
    t.status('reconnecting');
    t.status('open');
    expect(simulatedBegin()).toBeDisabled();
  });

  it('if the transport refuses the send, the page says "not sent" instead of doing nothing, and nothing is retried', async () => {
    const t = mount();
    t.status('open');
    t.emit(st('disconnected'));
    await waitFor(() => expect(simulatedBegin()).toBeEnabled());
    t.accept = false;
    await userEvent.setup().click(simulatedBegin());
    expect(screen.getByTestId('connect-not-sent')).toHaveTextContent(/not sent/i);
    expect(t.sent).toHaveLength(0);
    await new Promise((r) => setTimeout(r, 50));
    expect(t.sent).toHaveLength(0); // no automatic retry
  });

  it('defence in depth: resumes that make no progress stop after a few tries with a visible error (no storm)', async () => {
    const t = mount();
    t.status('open');
    t.emit(st('disconnected'));
    // a server that keeps skipping ahead: every event leaves a gap, lastSeq never moves
    for (let i = 0; i < 10; i++) {
      seq += 5;
      t.emit(st('disconnected'));
    }
    expect(t.resumes).toBeLessThanOrEqual(MAX_RESUMES_WITHOUT_PROGRESS);
    await waitFor(() => expect(screen.getAllByText(/stopped retrying/).length).toBeGreaterThan(0));
  });
});

describe('C-2: change or reconnect the system while connected', () => {
  async function connected(t: SpyTransport) {
    t.status('open');
    t.emit(st('disconnected'));
    await waitFor(() => expect(simulatedBegin()).toBeEnabled());
    await userEvent.setup().click(simulatedBegin());
    t.answer();
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Begin séance' })).toBeNull());
    t.sent.length = 0;
  }

  it('the header offers Change system and Reconnect, and both are reachable by keyboard', async () => {
    const t = mount();
    await connected(t);
    const group = screen.getByRole('group', { name: 'Change system' });
    const change = within(group).getByRole('button', { name: 'Change system' });
    const again = within(group).getByRole('button', { name: 'Reconnect' });
    expect(change).toBeEnabled();
    expect(again).toBeEnabled();
    const user = userEvent.setup();
    change.focus();
    await user.keyboard('{Enter}');
    expect(change).toHaveAttribute('aria-expanded', 'true');
    // the connect screen is back, the current system is marked, and nothing was sent yet
    expect(screen.getAllByRole('button', { name: 'Begin séance' }).length).toBeGreaterThan(0);
    expect(screen.getByText('connected now')).toBeInTheDocument();
    expect(t.sent).toHaveLength(0);
  });

  it('choosing another system sends exactly one connect_system and closes the chooser', async () => {
    const t = mount();
    await connected(t);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Change system' }));
    const tk4 = within(screen.getByText('TK4- built-in screens').closest('.system-card') as HTMLElement).getByRole('button', { name: 'Begin séance' });
    await user.dblClick(tk4); // a double click must still send one
    expect(connects(t)).toEqual([expect.objectContaining({ type: 'connect_system', app_id: 'tk4-builtins' })]);
    expect(t.sent).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Change system' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('"Back to the séance" closes the chooser without sending anything', async () => {
    const t = mount();
    await connected(t);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Change system' }));
    await user.click(screen.getByRole('button', { name: 'Back to the séance' }));
    expect(screen.queryByRole('button', { name: 'Begin séance' })).toBeNull();
    expect(t.sent).toHaveLength(0);
  });

  it('a refusal (error with the ref, e.g. session_busy) also re-enables the controls', async () => {
    const t = mount();
    await connected(t);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Reconnect' }));
    const id = t.sent[0]!.id;
    expect(screen.getByRole('button', { name: 'Reconnect' })).toBeDisabled();
    t.emit({ v: 1, type: 'error', seq: ++seq, ts: 't', session_id: 's_01', turn_id: null, data: { code: 'session_busy', message: 'busy', recoverable: true, ref: id } } as ServerEvent);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reconnect' })).toBeEnabled());
  });

  it('Reconnect sends exactly one connect_system for the current system, however often it is clicked before the answer', async () => {
    const t = mount();
    await connected(t);
    const user = userEvent.setup();
    const again = screen.getByRole('button', { name: 'Reconnect' });
    await user.click(again);
    await user.click(again);
    await user.click(again);
    expect(t.sent).toEqual([expect.objectContaining({ type: 'connect_system', app_id: 'fake-insurance' })]);
    // after the server answers (ack + connecting + connected in one batch), another reconnect is allowed again
    t.answer();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reconnect' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Reconnect' }));
    expect(connects(t)).toHaveLength(2);
  });

  it('is disabled with a stated reason while a turn runs, and for observers', async () => {
    const t = mount();
    await connected(t);
    t.emit(turn('turn_started'));
    const again = screen.getByRole('button', { name: 'Reconnect' });
    expect(again).toBeDisabled();
    expect(again).toHaveAccessibleDescription(/Finish or cancel the running turn first/);
    t.emit(turn('turn_finished'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reconnect' })).toBeEnabled());
    t.emit(st('connected', { controller: false }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reconnect' })).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Reconnect' })).toHaveAccessibleDescription(/Only the controller/);
  });

  it('an agent stuck in "connecting" with no app still offers Change system (no reload needed); Reconnect needs an app', async () => {
    const t = mount();
    t.status('open');
    t.emit(st('connecting', { app_id: null }));
    const change = await screen.findByRole('button', { name: 'Change system' });
    expect(screen.queryByRole('button', { name: 'Reconnect' })).toBeNull();
    await userEvent.setup().click(change);
    expect(screen.getAllByRole('button', { name: 'Begin séance' }).length).toBeGreaterThan(0);
  });

  it('passes axe with the chooser open over a live session', async () => {
    const t = mount();
    await connected(t);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Change system' }));
    await expectNoViolations();
  });

  it('property: any sequence of clicks on Reconnect / Change / Begin sends at most one connect_system per server answer', async () => {
    await fc.assert(
      fc.asyncProperty(fc.array(fc.constantFrom('reconnect', 'change', 'begin', 'answer'), { minLength: 1, maxLength: 12 }), async (ops) => {
        document.body.innerHTML = '';
        const t = mount();
        await connected(t);
        const user = userEvent.setup();
        let answers = 0;
        for (const op of ops) {
          if (op === 'answer') {
            t.answer();
            answers += 1;
          } else if (op === 'reconnect') {
            const b = screen.queryByRole('button', { name: 'Reconnect' });
            if (b && !(b as HTMLButtonElement).disabled) await user.click(b);
          } else if (op === 'change') {
            const b = screen.queryByRole('button', { name: 'Change system' });
            if (b && !(b as HTMLButtonElement).disabled) await user.click(b);
          } else {
            const b = screen.queryAllByRole('button', { name: 'Begin séance' }).find((x) => !(x as HTMLButtonElement).disabled);
            if (b) await user.click(b);
          }
        }
        expect(connects(t).length).toBeLessThanOrEqual(answers + 1);
        expect(t.sent.every((m) => m.type === 'connect_system')).toBe(true); // nothing else is ever sent by these controls
      }),
      { numRuns: 15 },
    );
  }, 120_000);
});
