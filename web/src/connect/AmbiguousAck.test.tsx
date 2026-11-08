import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { initialState, reduce, type AppState } from '../state/reducer';
import { StateBanner, bannerFor } from './StateBanner';
import { StepCard } from '../chat/StepCard';
import { StoreProvider } from '../state/store';
import { AppShell } from '../AppShell';
import { AnnouncerProvider } from '../a11y/Announcer';
import { friendlyError, strings } from '../strings';
import { parseServerEvent } from '../protocol/guards';
import type { Transport, TransportHandlers } from '../protocol/transport';
import type { ClientMessage, ServerEvent } from '../protocol/types';
import { expectNoViolations } from '../../test/axe';

/**
 * Integrator status 2026-11-06: contracts 3.5 `ambiguous_ack` = the host stopped answering, the key may have run, the
 * session was closed, nothing was resent. The UI shows it as its own state and never retries.
 */

let seq = 0;
const ev = (type: ServerEvent['type'], data: unknown, turn: string | null = null): ServerEvent =>
  ({ v: 1, type, seq: ++seq, ts: 't', session_id: 's_01', turn_id: turn, data }) as ServerEvent;

const sessionState = (state: string, app: string | null = 'fake-insurance') =>
  ev('session_state', {
    state, app_id: app, read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true },
    tools: { business: 3, generic: 4 }, resync: false, controller: true,
  });

/** connected -> a commit tool is running -> the host goes silent -> the agent closes the session. */
function ambiguousStream(): ServerEvent[] {
  seq = 0;
  return [
    sessionState('connected'),
    ev('turn_started', { user_message_id: 'm_1' }, 't_1'),
    ev('tool_call', { tool_call_id: 'c_1', tool: 'update_policy', kind: 'business', arguments: { policy_number: 'P0000003' }, may_commit: true }, 't_1'),
    ev('tool_result', { tool_call_id: 'c_1', status: 'error', error_code: 'ambiguous_ack', summary: 'The host did not acknowledge', result: null, truncated: false }, 't_1'),
    sessionState('session_lost'),
  ];
}

const play = (events: ServerEvent[], from: AppState = reduce(initialState(), { type: 'connection', status: 'open' })): AppState =>
  events.reduce((s, e) => reduce(s, { type: 'server', event: e, at: 0 }), from);

describe('ambiguous_ack is its own state', () => {
  it('the guard accepts the event shape (error_code is a free string)', () => {
    const r = parseServerEvent(ambiguousStream()[3]);
    expect(r.ok).toBe(true);
  });

  it('a tool_result with ambiguous_ack sets the flag and adds one plain-language chat message', () => {
    const s = play(ambiguousStream());
    expect(s.ambiguousAck).toBe(true);
    const msgs = s.messages.filter((m) => m.kind === 'system' && m.code === 'ambiguous_ack');
    expect(msgs).toHaveLength(1);
    expect(msgs[0] && msgs[0].kind === 'system' && msgs[0].text).toBe(strings.states.ambiguousAck);
    expect(s.toolCalls['c_1']?.status).toBe('error');
    expect(s.toolCalls['c_1']?.errorCode).toBe('ambiguous_ack');
  });

  it('an `error` event with the same code does the same, and uses the plain wording not the server text', () => {
    seq = 0;
    const s = play([sessionState('connected'), ev('error', { code: 'ambiguous_ack', message: 'bridge raised AmbiguousAckError', recoverable: true, ref: null })]);
    expect(s.ambiguousAck).toBe(true);
    const m = s.messages.find((x) => x.kind === 'system' && x.code === 'ambiguous_ack');
    expect(m && m.kind === 'system' && m.text).toBe(strings.states.ambiguousAck);
  });

  it('even a tool_result for a call we never saw raises the flag (the warning matters more than the bookkeeping)', () => {
    seq = 0;
    const s = play([sessionState('connected'), ev('tool_result', { tool_call_id: 'ghost', status: 'error', error_code: 'ambiguous_ack', summary: 'x', result: null, truncated: false }, 't_9')]);
    expect(s.ambiguousAck).toBe(true);
    expect(s.toolCalls['ghost']).toBeUndefined();
  });

  it('it stays up through session_lost and clears only when a new session is connecting or connected', () => {
    let s = play(ambiguousStream());
    expect(s.session.state).toBe('session_lost');
    expect(s.ambiguousAck).toBe(true);
    s = play([sessionState('connecting')], s);
    expect(s.ambiguousAck).toBe(false);
  });

  it('other tool errors do not trip it', () => {
    seq = 0;
    const s = play([
      sessionState('connected'),
      ev('turn_started', { user_message_id: 'm_1' }, 't_1'),
      ev('tool_call', { tool_call_id: 'c_1', tool: 'x', kind: 'generic', arguments: {}, may_commit: false }, 't_1'),
      ev('tool_result', { tool_call_id: 'c_1', status: 'error', error_code: 'keyboard_timeout', summary: 'slow', result: null, truncated: false }, 't_1'),
    ]);
    expect(s.ambiguousAck).toBe(false);
  });

  it('live_not_allowed gets plain wording too; unknown codes keep the server text', () => {
    expect(friendlyError('live_not_allowed', 'raw')).toMatch(/not cleared/);
    expect(friendlyError('something_new', 'the server said this')).toBe('the server said this');
  });
});

describe('banner and step card', () => {
  it('shows the exact guidance, ahead of the generic "session lost" banner, with a reconnect action naming the system', async () => {
    const s = play(ambiguousStream());
    const b = bannerFor(s, () => {});
    expect(b?.text).toBe('The mainframe did not answer. Nothing was resent. Reconnect and check the screen.');
    expect(b?.level).toBe('error');
    expect(b?.action?.label).toBe('Reconnect to fake-insurance');
    let clicked = 0;
    render(<StateBanner state={s} onReconnect={() => clicked++} />);
    expect(screen.getByRole('alert')).toHaveTextContent(/did not answer\. Nothing was resent/);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reconnect to fake-insurance' }));
    expect(clicked).toBe(1);
  });

  it('a plain session loss (no ambiguity) keeps the ordinary banner', () => {
    seq = 0;
    const s = play([sessionState('connected'), sessionState('session_lost')]);
    expect(bannerFor(s, () => {})?.text).toBe(strings.states.sessionLost);
  });

  it('the step card says the key may or may not have run, and that it was not resent', () => {
    const s = play(ambiguousStream());
    render(<StepCard step={{ kind: 'tool', id: 't', callId: 'c_1' }} call={s.toolCalls['c_1']} />);
    const note = screen.getByRole('note');
    expect(note).toHaveTextContent(/may or may not have run/);
    expect(note).toHaveTextContent(/not resent/);
  });

  it('passes axe', async () => {
    const s = play(ambiguousStream());
    const { container } = render(
      <div>
        <StateBanner state={s} onReconnect={() => {}} />
        <StepCard step={{ kind: 'tool', id: 't', callId: 'c_1' }} call={s.toolCalls['c_1']} />
      </div>,
    );
    await expectNoViolations(container, { fragment: true });
  });
});

// ---- the part that matters: nothing is sent on its own --------------------------------------------------------

class SpyTransport implements Transport {
  readonly kind = 'replay' as const;
  sent: ClientMessage[] = [];
  private h: TransportHandlers | null = null;
  subscribe(h: TransportHandlers) {
    this.h = h;
    return () => {
      this.h = null;
    };
  }
  start() {
    this.h?.onStatus('open');
  }
  send(m: ClientMessage) {
    this.sent.push(m);
    return true;
  }
  requestResume() {}
  close() {}
  emit(e: ServerEvent) {
    this.h?.onEvent(e);
  }
}

describe('never resent (mainframe-safety: no dangerous retries)', () => {
  function mount(t: SpyTransport) {
    return render(
      <StrictMode>
        <AnnouncerProvider>
          <StoreProvider transport={t} now={() => 0}>
            <AppShell
              rest={{ apps: async () => [], audit: async () => ({ entries: [], chain_ok: true, broken_seq: null }), spiritMap: async () => null }}
              replay={false}
              now={() => 0}
            />
          </StoreProvider>
        </AnnouncerProvider>
      </StrictMode>,
    );
  }

  it('after ambiguous_ack and session_lost the UI sends nothing by itself; Reconnect sends one connect_system and nothing else', async () => {
    const t = new SpyTransport();
    mount(t);
    const { act } = await import('@testing-library/react');
    act(() => {
      for (const e of ambiguousStream()) t.emit(e);
    });
    const banner = (await waitFor(() => { const b = document.querySelector('.state-banner'); expect(b).not.toBeNull(); return b; })) as HTMLElement;
    expect(within(banner).getByText(/Nothing was resent/)).toBeInTheDocument();
    // the whole point: no user_message, confirm_decision, cancel_turn or connect_system appeared on its own
    await new Promise((r) => setTimeout(r, 150));
    expect(t.sent).toEqual([]);

    await userEvent.setup().click(within(banner).getByRole('button', { name: 'Reconnect to fake-insurance' }));
    expect(t.sent).toHaveLength(1);
    expect(t.sent[0]).toMatchObject({ type: 'connect_system', app_id: 'fake-insurance' });
    // and specifically never the tool call or a decision
    expect(t.sent.some((m) => m.type === 'user_message' || m.type === 'confirm_decision')).toBe(false);
  });

  it('a new connected session removes the warning', async () => {
    const t = new SpyTransport();
    mount(t);
    const { act } = await import('@testing-library/react');
    act(() => {
      for (const e of ambiguousStream()) t.emit(e);
    });
    await waitFor(() => expect(document.querySelector('.state-banner')?.textContent).toMatch(/did not answer/));
    act(() => {
      t.emit(sessionState('connecting'));
      t.emit(sessionState('connected'));
    });
    await waitFor(() => expect(document.querySelector('.state-banner')).toBeNull()); // the banner is gone
    // the earlier chat message stays as history of what happened
    expect(screen.getAllByText(/Nothing was resent/).length).toBeGreaterThan(0);
  });
});
