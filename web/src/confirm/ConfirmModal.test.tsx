import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfirmModal, type ConfirmModalProps } from './ConfirmModal';
import type { Confirmation, ScreenState } from '../state/reducer';

/**
 * REQ-029 safety tests. The modal is a safety control: Deny first, Esc denies, Approve delayed, only trusted
 * activations approve, agent words never in the authoritative block, one decision, expiry blocks approval.
 *
 * jsdom marks EVERY event untrusted (element.click() and user-event included), so the default isTrusted check is
 * exercised as "blocks everything", and an injected predicate simulates a genuine user activation. A real-browser
 * check of event.isTrusted is on the manual list in web/A11Y.md.
 */

const SCREEN_ID = 'c'.repeat(64);

const screenState = (): ScreenState => ({
  screenId: SCREEN_ID,
  cursor: [0, 0],
  rows: Array.from({ length: 24 }, (_, i) => (i === 3 ? '  OLD PREMIUM 250.00   NEW PREMIUM 300.00'.padEnd(80) : ' '.repeat(80))),
  fields: [],
});

const conf = (over: Partial<Confirmation> = {}): Confirmation => ({
  actionId: 'act_1', toolCallId: 'c_1', turnId: 't_1', screenId: SCREEN_ID, key: 'Enter',
  fieldSnapshot: [{ index: 3, row: 5, col: 14, label: 'PREMIUM', value: '300.00' }],
  expiresInS: 300, receivedAt: 0, readOnly: false,
  agentSummary: 'Change the premium of P0000003 from 250.00 to 300.00',
  phase: 'open', outcome: null, errorCode: null, confirmedBy: null, ...over,
});

function setup(over: Partial<ConfirmModalProps> = {}, c: Confirmation = conf()) {
  const clock = { t: 0 };
  const onDecide = vi.fn();
  const onTimeout = vi.fn();
  const onDismiss = vi.fn();
  const props: ConfirmModalProps = {
    confirmation: c, screen: screenState(), sessionReadOnly: false, observerOnly: false,
    now: () => clock.t, onDecide, onTimeout, onDismiss, ...over,
  };
  const view = render(<ConfirmModal {...props} />);
  const rerender = (patch: Partial<ConfirmModalProps> = {}) => view.rerender(<ConfirmModal {...props} {...patch} />);
  return { clock, onDecide, onTimeout, onDismiss, rerender, props };
}

const approveBtn = () => screen.queryByRole('button', { name: /^Approve/ });
const denyBtn = () => screen.getByRole('button', { name: 'Deny' });

describe('ConfirmModal safety (REQ-017, REQ-029)', () => {
  it('is an alertdialog, and Deny is the initially focused control', () => {
    setup();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(denyBtn()).toHaveFocus();
  });

  it('Esc means Deny', async () => {
    const h = setup();
    await userEvent.setup().keyboard('{Escape}');
    expect(h.onDecide).toHaveBeenCalledOnce();
    expect(h.onDecide).toHaveBeenCalledWith('deny');
  });

  it('Approve is disabled for 600 ms, with the wait visible, then enabled', () => {
    const h = setup();
    expect(approveBtn()).toBeDisabled();
    expect(approveBtn()?.textContent).toMatch(/\d/); // countdown in the label
    h.clock.t = 599;
    h.rerender();
    expect(approveBtn()).toBeDisabled();
    h.clock.t = 600;
    h.rerender();
    expect(approveBtn()).toBeEnabled();
    expect(approveBtn()?.textContent).toBe('Approve');
  });

  it('an untrusted (synthetic) click never approves, even when Approve is enabled', () => {
    const h = setup();
    h.clock.t = 1000;
    h.rerender();
    const b = approveBtn() as HTMLButtonElement;
    expect(b).toBeEnabled();
    b.dispatchEvent(new MouseEvent('click', { bubbles: true })); // isTrusted === false
    b.click(); // also untrusted in a script
    expect(h.onDecide).not.toHaveBeenCalled();
  });

  it('a trusted activation approves, exactly once', async () => {
    const h = setup({ isTrusted: () => true });
    h.clock.t = 1000;
    h.rerender({ isTrusted: () => true });
    const user = userEvent.setup();
    await user.click(approveBtn() as HTMLButtonElement);
    await user.click(approveBtn() as HTMLButtonElement);
    expect(h.onDecide).toHaveBeenCalledTimes(1);
    expect(h.onDecide).toHaveBeenCalledWith('approve');
  });

  it('exactly one decision per modal, even if Deny is pressed repeatedly', async () => {
    const h = setup();
    const user = userEvent.setup();
    await user.click(denyBtn());
    await user.click(denyBtn());
    await user.keyboard('{Escape}');
    expect(h.onDecide).toHaveBeenCalledTimes(1);
    expect(h.onDecide).toHaveBeenCalledWith('deny');
  });

  it('Enter on the dialog does not approve; with focus on Deny it denies', async () => {
    const h = setup({ isTrusted: () => true });
    h.clock.t = 1000;
    h.rerender({ isTrusted: () => true });
    await userEvent.setup().keyboard('{Enter}');
    expect(h.onDecide).not.toHaveBeenCalledWith('approve');
  });

  it('after expiry it cannot approve and reports the timeout once', () => {
    const h = setup({ isTrusted: () => true });
    h.clock.t = 301_000; // past expires_in_s = 300
    h.rerender({ isTrusted: () => true });
    expect(h.onTimeout).toHaveBeenCalledTimes(1);
    expect(approveBtn()).toBeDisabled();
    h.rerender({ isTrusted: () => true });
    expect(h.onTimeout).toHaveBeenCalledTimes(1);
  });

  it('time left is computed from the monotonic receipt time', () => {
    const h = setup({}, conf({ receivedAt: 10_000, expiresInS: 60 }));
    h.clock.t = 10_000 + 20_000;
    h.rerender();
    expect(screen.getByText(/Time left: 40 s/)).toBeInTheDocument();
  });

  it('Approve stays disabled when no screen with the gate screen_id is known', () => {
    const h = setup({ screen: null });
    h.clock.t = 5000;
    h.rerender({ screen: null });
    expect(approveBtn()).toBeDisabled();
    expect(screen.getByText(/not available, so Approve is disabled/)).toBeInTheDocument();
  });

  it('read-only: banner shown and no Approve button at all', () => {
    setup({ sessionReadOnly: true });
    expect(screen.getByText(/read only/i)).toBeInTheDocument();
    expect(approveBtn()).toBeNull();
    expect(denyBtn()).toBeInTheDocument();
  });

  it('observers cannot approve', () => {
    const h = setup({ observerOnly: true });
    h.clock.t = 5000;
    h.rerender({ observerOnly: true });
    expect(approveBtn()).toBeDisabled();
  });
});

describe('ConfirmModal content (REQ-016, REQ-029)', () => {
  it('draws the gate key, the miniature screen and the gate fields', () => {
    setup();
    const dialog = screen.getByRole('alertdialog');
    expect(within(dialog).getByText('Enter')).toBeInTheDocument(); // the keycap
    expect(dialog.querySelector('.mini-screen')?.textContent).toContain('NEW PREMIUM 300.00');
    expect(within(dialog).getByText('PREMIUM')).toBeInTheDocument();
    expect(within(dialog).getByText('300.00')).toBeInTheDocument();
  });

  it('agent_summary is never inside the authoritative block; it sits in its own labelled "unverified" block', () => {
    setup();
    const summary = 'Change the premium of P0000003 from 250.00 to 300.00';
    const authoritative = document.querySelector('.confirm-authoritative') as HTMLElement;
    expect(authoritative.textContent).not.toContain(summary);
    const agent = screen.getByTestId('agent-block');
    expect(agent.textContent).toContain(summary);
    expect(within(agent).getByText(/The agent says \(unverified\)/)).toBeInTheDocument();
  });

  it('hidden and redacted snapshot values are shown as "hidden", never as text', () => {
    setup({}, conf({ fieldSnapshot: [{ index: 1, row: 2, col: 3, label: 'PIN', value: '<hidden>' }] }));
    const list = document.querySelector('.confirm-fields') as HTMLElement;
    expect(list.textContent).toContain('PIN');
    expect(list.textContent).toContain('hidden');
    expect(list.textContent).not.toContain('<hidden>');
  });

  it('an empty snapshot (review screen) says so and relies on the screen', () => {
    setup({}, conf({ fieldSnapshot: [] }));
    expect(screen.getByText(/No editable fields on this screen/)).toBeInTheDocument();
    expect(document.querySelector('.mini-screen')?.textContent).toContain('OLD PREMIUM 250.00');
  });

  it('escapes server text: agent summary containing markup is rendered as text', () => {
    setup({}, conf({ agentSummary: '<img src=x onerror=alert(1)>' }));
    expect(document.querySelector('.confirm-agent img')).toBeNull();
    expect(screen.getByTestId('agent-block').textContent).toContain('<img src=x onerror=alert(1)>');
  });
});

describe('ConfirmModal outcomes and states', () => {
  it('shows the sending state with no decision buttons', () => {
    setup({}, conf({ phase: 'sending' }));
    expect(screen.getByText(/Sending your decision/)).toBeInTheDocument();
    expect(approveBtn()).toBeNull();
  });

  it.each([
    ['approved', /Approved/],
    ['denied', /Denied/],
    ['expired', /Expired/],
    ['blocked_read_only', /read only/],
    ['stale', /Stale/],
  ] as const)('resolved %s shows its outcome and a dismiss button', (outcome, text) => {
    const h = setup({}, conf({ phase: 'resolved', outcome }));
    expect(screen.getByRole('status')).toHaveTextContent(text);
    expect(approveBtn()).toBeNull();
    expect(screen.getByRole('button', { name: 'Dismiss' })).toBeInTheDocument();
    expect(h.onDecide).not.toHaveBeenCalled();
  });

  it('locally expired shows the expired message and cannot be approved', () => {
    setup({}, conf({ phase: 'expired' }));
    expect(screen.getByText(/This confirmation expired/)).toBeInTheDocument();
    expect(approveBtn()).toBeNull();
  });

  it('the app root is inert while the dialog is open and released afterwards', () => {
    const root = document.createElement('div');
    document.body.appendChild(root);
    const view = render(<ConfirmModal {...setupProps({ inertRoot: root })} />);
    expect(root.hasAttribute('inert')).toBe(true);
    view.unmount();
    expect(root.hasAttribute('inert')).toBe(false);
  });
});

function setupProps(over: Partial<ConfirmModalProps>): ConfirmModalProps {
  return {
    confirmation: conf(), screen: screenState(), sessionReadOnly: false, observerOnly: false,
    now: () => 0, onDecide: () => {}, onTimeout: () => {}, onDismiss: () => {}, ...over,
  };
}

describe('focus trap', () => {
  it('Tab and Shift+Tab cycle inside the dialog', async () => {
    const h = setup();
    h.clock.t = 1000;
    h.rerender();
    const user = userEvent.setup();
    const dialog = screen.getByRole('alertdialog');
    expect(denyBtn()).toHaveFocus();
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.tab();
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.tab({ shift: true });
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('returns focus to the element that had it before the dialog opened', () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const view = render(<ConfirmModal {...setupProps({})} />);
    expect(opener).not.toHaveFocus();
    view.unmount();
    expect(opener).toHaveFocus();
  });
});
