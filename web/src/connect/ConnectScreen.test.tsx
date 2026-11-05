import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConnectScreen } from './ConnectScreen';
import { StateBanner, bannerFor } from './StateBanner';
import { AnnouncerProvider, POLITE_INTERVAL_MS, useAnnouncer } from '../a11y/Announcer';
import { RestClient, RestError } from '../protocol/rest';
import { initialState, reduce, type AppState } from '../state/reducer';
import { loadExamples } from '../../test/examples';
import type { AppInfo } from '../protocol/types';
import { useEffect } from 'react';

const ex = loadExamples();
const apps = (ex.rest['apps'] as { apps: AppInfo[] }).apps;

describe('RestClient (REST section 5)', () => {
  const okFetch = (body: unknown, status = 200): typeof fetch =>
    (async () => ({ ok: status < 400, status, json: async () => body })) as unknown as typeof fetch;

  it('parses /api/apps', async () => {
    const c = new RestClient('http://127.0.0.1:8000', okFetch(ex.rest['apps']));
    const list = await c.apps();
    expect(list).toHaveLength(3);
    expect(list[0]?.app_id).toBe('fake-insurance');
  });

  it('parses /api/audit', async () => {
    const c = new RestClient('http://127.0.0.1:8000', okFetch(ex.rest['audit']));
    const a = await c.audit();
    expect(Array.isArray(a.entries)).toBe(true);
    expect(typeof a.chain_ok).toBe('boolean');
  });

  it('returns null spirit-map on 404 no_map', async () => {
    const c = new RestClient('http://127.0.0.1:8000', okFetch({ error: 'no_map' }, 404));
    expect(await c.spiritMap('tk4-builtins')).toBeNull();
  });

  it('throws a RestError when the agent is unreachable', async () => {
    const c = new RestClient('http://127.0.0.1:8000', (async () => {
      throw new Error('ECONN');
    }) as unknown as typeof fetch);
    await expect(c.apps()).rejects.toBeInstanceOf(RestError);
  });

  it('rejects a malformed apps body rather than trusting it', async () => {
    const c = new RestClient('http://127.0.0.1:8000', okFetch({ apps: [{ app_id: 123 }] }));
    await expect(c.apps()).rejects.toBeInstanceOf(RestError);
  });
});

describe('ConnectScreen (REQ-010)', () => {
  it('lists systems with kind, reachability, map and tool counts', () => {
    render(<ConnectScreen load={{ status: 'ready', apps }} onConnect={() => {}} onRetry={() => {}} />);
    expect(screen.getByText('Seance Insurance (simulated)')).toBeInTheDocument();
    expect(screen.getByText(/3 of 3 tools approved/)).toBeInTheDocument();
    // the unreachable live app's connect button is disabled
    const kicks = screen.getByText('Seance Insurance (KICKS)').closest('.system-card') as HTMLElement;
    expect(kicks.querySelector('button')).toBeDisabled();
  });

  it('sends connect_system when a reachable system is chosen', async () => {
    const onConnect = vi.fn();
    const user = userEvent.setup();
    render(<ConnectScreen load={{ status: 'ready', apps }} onConnect={onConnect} onRetry={() => {}} />);
    const fake = screen.getByText('Seance Insurance (simulated)').closest('.system-card') as HTMLElement;
    await user.click(fake.querySelector('button') as HTMLButtonElement);
    expect(onConnect).toHaveBeenCalledWith('fake-insurance');
  });

  it('shows an empty state when no systems are configured', () => {
    render(<ConnectScreen load={{ status: 'ready', apps: [] }} onConnect={() => {}} onRetry={() => {}} />);
    expect(screen.getByText(/No systems are configured/)).toBeInTheDocument();
  });

  it('shows an error state with a retry action', async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(<ConnectScreen load={{ status: 'error' }} onConnect={() => {}} onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent(/Could not reach the agent/);
    await user.click(screen.getByText('Try again'));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe('StateBanner (REQ-012)', () => {
  const connected = (): AppState => {
    let s = initialState();
    s = reduce(s, { type: 'connection', status: 'open' });
    return reduce(s, {
      type: 'server',
      at: 0,
      event: { v: 1, type: 'session_state', seq: 1, ts: 't', session_id: 's', turn_id: null, data: { state: 'connected', app_id: 'x', read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true }, tools: { business: 1, generic: 1 }, resync: false, controller: true } },
    });
  };

  it('no banner on a healthy connected session', () => {
    expect(bannerFor(connected(), () => {})).toBeNull();
  });

  it('session lost offers a reconnect action', async () => {
    const onReconnect = vi.fn();
    let s = connected();
    s = reduce(s, { type: 'server', at: 0, event: { v: 1, type: 'session_state', seq: 2, ts: 't', session_id: 's', turn_id: null, data: { state: 'session_lost', app_id: 'x', read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true }, tools: { business: 1, generic: 1 }, resync: false, controller: true } } });
    const user = userEvent.setup();
    render(<StateBanner state={s} onReconnect={onReconnect} />);
    expect(screen.getByRole('alert')).toHaveTextContent(/lost its connection/);
    await user.click(screen.getByText('Reconnect'));
    expect(onReconnect).toHaveBeenCalled();
  });

  it('observer, read-only and llm-unavailable each produce their banner', () => {
    const base = connected();
    const obs = reduce(base, { type: 'server', at: 0, event: { v: 1, type: 'session_state', seq: 2, ts: 't', session_id: 's', turn_id: null, data: { state: 'connected', app_id: 'x', read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true }, tools: { business: 1, generic: 1 }, resync: false, controller: false } } });
    expect(bannerFor(obs, () => {})?.text).toMatch(/observing/);
    const ro = reduce(base, { type: 'server', at: 0, event: { v: 1, type: 'session_state', seq: 2, ts: 't', session_id: 's', turn_id: null, data: { state: 'connected', app_id: 'x', read_only: true, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true }, tools: { business: 1, generic: 1 }, resync: false, controller: true } } });
    expect(bannerFor(ro, () => {})?.text).toMatch(/read only/);
    const noLlm = reduce(base, { type: 'server', at: 0, event: { v: 1, type: 'session_state', seq: 2, ts: 't', session_id: 's', turn_id: null, data: { state: 'connected', app_id: 'x', read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: false }, tools: { business: 1, generic: 1 }, resync: false, controller: true } } });
    expect(bannerFor(noLlm, () => {})?.text).toMatch(/language model is unavailable/);
  });
});

describe('Announcer (REQ-019)', () => {
  function Harness() {
    const { announce } = useAnnouncer();
    useEffect(() => {
      announce('first');
      announce('second'); // within the same tick -> rate limited to one
    }, [announce]);
    return null;
  }

  it('rate-limits polite announcements to roughly one per second', async () => {
    const clock = { now: 0 };
    render(
      <AnnouncerProvider now={() => clock.now}>
        <Harness />
      </AnnouncerProvider>,
    );
    // first announcement is immediate; "second" is queued for POLITE_INTERVAL_MS
    await waitFor(() => expect(screen.getByTestId('live-polite').textContent).toBe('first'));
    expect(POLITE_INTERVAL_MS).toBe(1000);
  });

  it('assertive announcements go to the alert region', async () => {
    function A() {
      const { announce } = useAnnouncer();
      useEffect(() => announce('urgent', 'assertive'), [announce]);
      return null;
    }
    render(
      <AnnouncerProvider>
        <A />
      </AnnouncerProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('live-assertive').textContent).toBe('urgent'));
  });
});
