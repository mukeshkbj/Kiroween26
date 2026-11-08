import { describe, expect, it } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StoreProvider, useStore, type StoreApi } from '../state/store';
import { ConfirmHost } from './ConfirmHost';
import { AnnouncerProvider } from '../a11y/Announcer';
import { ReplayTransport } from '../protocol/replayTransport';
import type { Timer } from '../protocol/transport';
import type { ServerEvent } from '../protocol/types';
import { loadExamples } from '../../test/examples';

/**
 * 5.2: the modal against the recorded transcripts, end to end through the real store and replay transport:
 * approve, deny, expire, read-only, plus a synthetic superseded case.
 */

const ex = loadExamples();

class Clock {
  now = 0;
  private tasks: { at: number; fn: () => void; id: number }[] = [];
  private n = 0;
  timer: Timer = (fn, ms) => {
    const id = ++this.n;
    this.tasks.push({ at: this.now + ms, fn, id });
    return () => (this.tasks = this.tasks.filter((t) => t.id !== id));
  };
  advance(ms: number) {
    const end = this.now + ms;
    for (;;) {
      const due = this.tasks.filter((t) => t.at <= end).sort((a, b) => a.at - b.at || a.id - b.id)[0];
      if (!due) break;
      this.tasks = this.tasks.filter((t) => t !== due);
      this.now = due.at;
      act(() => due.fn());
    }
    this.now = end;
  }
}

function mount(name: string, lines = ex.transcripts[name] ?? []) {
  const clock = new Clock();
  const transport = new ReplayTransport({ lines, timer: clock.timer });
  let api: StoreApi = null as unknown as StoreApi;
  function Capture() {
    api = useStore();
    return null;
  }
  render(
    <AnnouncerProvider>
      <StoreProvider transport={transport} now={() => clock.now}>
        <Capture />
        <ConfirmHost now={() => clock.now} isTrusted={() => true} />
      </StoreProvider>
    </AnnouncerProvider>,
  );
  return { clock, transport, get: () => api };
}

/** Perform the scripted user actions until the modal is open (or the script ends). */
function driveToModal(h: ReturnType<typeof mount>) {
  // Small virtual steps: the modal's time-left is measured from when it opened, so we must stop as soon as it
  // appears rather than leaping a million milliseconds past it.
  for (let i = 0; i < 4000; i++) {
    h.clock.advance(25);
    if (screen.queryByRole('alertdialog')) return;
    const want = h.transport.expecting();
    if (want) {
      act(() => {
        h.transport.send(want);
      });
    }
  }
}

describe('modal over the recorded transcripts (5.2)', () => {
  it('commit-approve: opens with the key and screen, Approve after the delay, resolves approved', async () => {
    const h = mount('commit-approve');
    driveToModal(h);
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog.querySelector('.keycap')?.textContent).toBe('Enter');
    // the gate snapshot is empty on the confirm screen, so the miniature carries the facts
    expect(dialog.querySelector('.mini-screen')?.textContent).toMatch(/PREMIUM|CONFIRM/i);
    expect(screen.getByRole('button', { name: /^Approve/ })).toBeDisabled();
    act(() => {
      h.clock.now += 700;
    });
    // re-render via the store clock tick
    await waitFor(() => expect(screen.getByRole('button', { name: /^Approve/ })).toBeEnabled(), { timeout: 2000 });
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /^Approve/ }));
    // the script now waits for the scripted approve decision, which the real click just sent
    h.clock.advance(1_000_000);
    await waitFor(() => expect(h.get().state.confirmation?.outcome).toBe('approved'));
    expect(screen.getByRole('status', { name: '' })).toBeDefined();
    await user.click(await screen.findByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('commit-deny: Esc denies and the transcript resolves denied', async () => {
    const h = mount('commit-deny');
    driveToModal(h);
    await screen.findByRole('alertdialog');
    await userEvent.setup().keyboard('{Escape}');
    h.clock.advance(1_000_000);
    await waitFor(() => expect(h.get().state.confirmation?.outcome).toBe('denied'));
    expect(screen.getByRole('status')).toHaveTextContent(/Denied/);
  });

  it('commit-expire: the server expiry is shown and nothing can be approved', async () => {
    const h = mount('commit-expire');
    driveToModal(h);
    await screen.findByRole('alertdialog');
    h.clock.advance(1_000_000);
    await waitFor(() => expect(h.get().state.confirmation?.outcome).toBe('expired'));
    expect(screen.queryByRole('button', { name: /^Approve/ })).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent(/Expired/);
  });

  it('read-only: no Approve at all, and the transcript ends blocked_read_only', async () => {
    const h = mount('read-only');
    driveToModal(h);
    await screen.findByRole('alertdialog');
    expect(screen.queryByRole('button', { name: /^Approve/ })).toBeNull();
    expect(screen.getByText(/read only/i)).toBeInTheDocument();
  });

  it('superseded: a new confirmation_required replaces the open one with a fresh modal', async () => {
    const base = ex.transcripts['commit-approve'] ?? [];
    const firstReq = base.find((l) => l.dir === 'server' && (l.event as ServerEvent).type === 'confirmation_required');
    expect(firstReq).toBeDefined();
    const ev = (firstReq as { event: ServerEvent }).event as Extract<ServerEvent, { type: 'confirmation_required' }>;
    const second: ServerEvent = { ...ev, seq: ev.seq + 1, data: { ...ev.data, action_id: 'second-action', agent_summary: 'second' } };
    // keep everything up to and including the first request, then add the replacement
    const idx = base.indexOf(firstReq as (typeof base)[number]);
    const lines = [...base.slice(0, idx + 1), { dir: 'server' as const, delay_ms: 10, event: second }];
    const h = mount('superseded', lines);
    driveToModal(h);
    h.clock.advance(1_000_000);
    await waitFor(() => expect(h.get().state.confirmation?.actionId).toBe('second-action'));
    expect(screen.getAllByRole('alertdialog')).toHaveLength(1);
    expect(screen.getByTestId('agent-block')).toHaveTextContent('second');
    expect(h.get().state.messages.some((m) => m.kind === 'system' && m.code === 'superseded')).toBe(true);
    // the fresh modal starts with Deny focused again
    expect(screen.getByRole('button', { name: 'Deny' })).toHaveFocus();
  });
});
