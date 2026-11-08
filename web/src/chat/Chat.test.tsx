import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Chat } from './Chat';
import { StepCard } from './StepCard';
import { Composer } from './Composer';
import { redactArguments } from './redact';
import { initialState, reduce, type AppState, type ToolCallState } from '../state/reducer';
import { parseServerEvent } from '../protocol/guards';
import { loadExamples } from '../../test/examples';

const ex = loadExamples();

function playLookup(): AppState {
  let s = initialState();
  s = reduce(s, { type: 'connection', status: 'open' });
  for (const line of ex.transcripts['lookup'] ?? []) {
    if (line.dir !== 'server') continue;
    const r = parseServerEvent(line.event);
    if (r.ok) s = reduce(s, { type: 'server', event: r.event, at: r.event.seq * 10 });
  }
  return s;
}

describe('Chat (REQ-007)', () => {
  it('is a polite log region and shows the streamed assistant answer', () => {
    const s = playLookup();
    render(<Chat state={s} onSend={() => {}} onCancel={() => {}} />);
    const log = screen.getByRole('log');
    expect(log.getAttribute('aria-live')).toBe('polite');
    expect(log.textContent).toContain('A. ROSE');
  });

  it('shows a user message, acked, and the assistant turn with step cards', () => {
    const s = playLookup();
    // simulate the user having sent the message the transcript answers
    const withUser = reduce(s, { type: 'user_sent', id: 'u_02', text: 'Look up policy P0000003' });
    render(<Chat state={withUser} onSend={() => {}} onCancel={() => {}} />);
    expect(screen.getByText('Look up policy P0000003')).toBeInTheDocument();
    // the business tool name appears in a step card
    expect(screen.getByText('lookup_policy')).toBeInTheDocument();
  });
});

describe('StepCard (REQ-009)', () => {
  const call: ToolCallState = {
    id: 'c_1', turnId: 't_1', tool: 'lookup_policy', toolKind: 'business',
    arguments: { policy_number: 'P0000003', pin: '9999' }, mayCommit: false,
    status: 'ok', errorCode: null, summary: 'Found policy P0000003',
    result: { data: { holder: 'A. ROSE', status: 'ACTIVE' } }, truncated: false,
  };

  it('shows the tool name, a business badge, and redacts credential-like arguments', () => {
    render(<StepCard step={{ kind: 'tool', id: 't', callId: 'c_1' }} call={call} />);
    expect(screen.getByText('lookup_policy')).toBeInTheDocument();
    expect(screen.getByText('business')).toBeInTheDocument();
    expect(screen.getByText('P0000003')).toBeInTheDocument();
    expect(screen.getByText('<redacted>')).toBeInTheDocument(); // pin
  });

  it('labels legacy result data as untrusted', () => {
    render(<StepCard step={{ kind: 'tool', id: 't', callId: 'c_1' }} call={call} />);
    const holderRow = screen.getByText('holder').closest('.step-data-row') as HTMLElement;
    expect(within(holderRow).getByText('A. ROSE')).toBeInTheDocument();
    expect(within(holderRow).getByText(/legacy screen/i)).toBeInTheDocument();
  });

  it('redactArguments never emits a credential value', () => {
    const out = redactArguments({ password: 'hunter2', token: 'abc', premium: '300.00' });
    expect(out.find((a) => a.key === 'password')?.value).toBe('<redacted>');
    expect(out.find((a) => a.key === 'token')?.value).toBe('<redacted>');
    expect(out.find((a) => a.key === 'premium')?.value).toBe('300.00');
    expect(JSON.stringify(out)).not.toContain('hunter2');
  });
});

describe('Composer (REQ-008)', () => {
  it('Enter sends, Shift+Enter inserts a newline', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer block={null} canCancel={false} onSend={onSend} onCancel={() => {}} />);
    const box = screen.getByLabelText(/Message to the séance/i);
    await user.type(box, 'hello');
    await user.keyboard('{Shift>}{Enter}{/Shift}world');
    expect(onSend).not.toHaveBeenCalled();
    await user.keyboard('{Enter}');
    expect(onSend).toHaveBeenCalledWith('hello\nworld');
  });

  it('Esc cancels a running turn', async () => {
    const onCancel = vi.fn();
    const user = userEvent.setup();
    render(<Composer block={null} canCancel={true} onSend={() => {}} onCancel={onCancel} />);
    await user.type(screen.getByLabelText(/Message to the séance/i), 'x');
    await user.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('is disabled with a stated reason when blocked', () => {
    render(<Composer block="observer" canCancel={false} onSend={() => {}} onCancel={() => {}} />);
    expect(screen.getByLabelText(/Message to the séance/i)).toBeDisabled();
    expect(screen.getByText(/only the controller/i)).toBeInTheDocument();
  });

  it('does not send empty or whitespace-only text', async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer block={null} canCancel={false} onSend={onSend} onCancel={() => {}} />);
    await user.type(screen.getByLabelText(/Message to the séance/i), '   ');
    await user.keyboard('{Enter}');
    expect(onSend).not.toHaveBeenCalled();
  });
});
