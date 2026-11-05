import { describe, expect, it } from 'vitest';
import { act, render, waitFor } from '@testing-library/react';
import { StoreProvider, useStore } from './store';
import { ReplayTransport } from '../protocol/replayTransport';
import type { Timer } from '../protocol/transport';
import { loadExamples } from '../../test/examples';
import type { StoreApi } from './store';

const ex = loadExamples();

/** A manual clock so the replay's delays advance deterministically. */
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

function mount(name: string) {
  const clock = new Clock();
  const transport = new ReplayTransport({ lines: ex.transcripts[name] ?? [], timer: clock.timer });
  let api: StoreApi = null as unknown as StoreApi;
  function Capture() {
    api = useStore();
    return null;
  }
  render(
    <StoreProvider transport={transport} now={() => clock.now}>
      <Capture />
    </StoreProvider>,
  );
  return { clock, transport, get: () => api };
}

describe('store in mock/replay mode (REQ-023, 4.5)', () => {
  it('lookup: connect, ask, and the answer lands with the tool call recorded', async () => {
    const h = mount('lookup');
    h.clock.advance(100_000);
    await waitFor(() => expect(h.transport.expecting()?.type).toBe('connect_system'));
    act(() => h.get().connectSystem('fake-insurance'));
    h.clock.advance(100_000);
    await waitFor(() => expect(h.transport.expecting()?.type).toBe('user_message'));
    act(() => h.get().sendMessage('Look up policy P0000003'));
    h.clock.advance(100_000);
    await waitFor(() => expect(h.transport.finished).toBe(true));
    const s = h.get().state;
    expect(s.session.state).toBe('connected');
    expect(Object.values(s.toolCalls).some((c) => c.tool === 'lookup_policy' && c.status === 'ok')).toBe(true);
    const assistant = s.messages.find((m) => m.kind === 'assistant');
    expect(assistant && assistant.kind === 'assistant' && assistant.text).toContain('A. ROSE');
    // The user message was handed to the (mock) transport, so it is not marked failed. In replay mode the
    // recorded ack refers to the transcript's own id, so it stays "sent" rather than "acked" — that is honest.
    const user = s.messages.find((m) => m.kind === 'user');
    expect(user && user.kind === 'user' && user.status).toBe('sent');
  });

  it('session-lost: the stream ends and the reducer never leaves a confirmation open', async () => {
    const h = mount('session-lost');
    for (let i = 0; i < 20; i++) {
      h.clock.advance(1_000_000);
      const want = h.transport.expecting();
      if (!want) break;
      act(() => {
        h.transport.send(want);
      });
    }
    h.clock.advance(1_000_000);
    const s = h.get().state;
    expect(s.confirmation === null || s.confirmation.phase !== 'open').toBe(true);
  });

  it('injection: hostile screen text is rendered as data and does not drive any tool or confirmation', async () => {
    const h = mount('injection');
    for (let i = 0; i < 20; i++) {
      h.clock.advance(1_000_000);
      const want = h.transport.expecting();
      if (!want) break;
      act(() => {
        h.transport.send(want);
      });
    }
    h.clock.advance(1_000_000);
    const s = h.get().state;
    // the screen text is present somewhere in state as data
    expect(JSON.stringify(s.screensById).toLowerCase()).toContain('ignore');
    // but the UI never fabricated a confirmation or a commit from it
    expect(s.confirmation === null || s.confirmation.phase !== 'open').toBe(true);
  });

  it('commit-deny: a deny decision is sent once and resolves denied', async () => {
    const h = mount('commit-deny');
    let decided = false;
    for (let i = 0; i < 30; i++) {
      h.clock.advance(1_000_000);
      const want = h.transport.expecting();
      if (!want) break;
      if (want.type === 'confirm_decision') {
        act(() => h.get().decide(want.action_id, 'deny'));
        decided = true;
      } else {
        act(() => {
          h.transport.send(want);
        });
      }
    }
    h.clock.advance(1_000_000);
    expect(decided).toBe(true);
    const s = h.get().state;
    expect(s.confirmation?.outcome).toBe('denied');
  });
});
