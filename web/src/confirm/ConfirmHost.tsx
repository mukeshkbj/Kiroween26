import { useEffect } from 'react';
import { ConfirmModal } from './ConfirmModal';
import { useStore } from '../state/store';
import { confirmationScreen } from '../state/selectors';
import { useAnnouncer } from '../a11y/Announcer';
import { strings } from '../strings';

/**
 * Connects the store to the modal. `key` is the action id, so a replacing confirmation_required mounts a fresh
 * modal (new focus, new 600 ms delay, new one-decision budget) and the old one is simply gone. Opening is
 * announced assertively; the modal itself carries the details.
 */

export interface ConfirmHostProps {
  now?: () => number;
  inertRoot?: HTMLElement | null;
  /** Test seam passed through to the modal. */
  isTrusted?: (e: Event) => boolean;
}

export function ConfirmHost({ now = () => performance.now(), inertRoot, isTrusted }: ConfirmHostProps) {
  const { state, decide, dispatch } = useStore();
  const { announce } = useAnnouncer();
  const c = state.confirmation;
  const openId = c && c.phase === 'open' ? c.actionId : null;

  useEffect(() => {
    if (openId) announce(strings.confirm.title, 'assertive');
  }, [openId, announce]);

  useEffect(() => {
    if (c?.phase === 'resolved' && c.outcome) announce(strings.confirm.outcome[c.outcome], 'polite');
  }, [c?.phase, c?.outcome, announce]);

  if (!c) return null;
  return (
    <ConfirmModal
      key={c.actionId}
      confirmation={c}
      screen={confirmationScreen(state)}
      sessionReadOnly={state.session.readOnly}
      observerOnly={state.observerOnly}
      now={now}
      inertRoot={inertRoot}
      isTrusted={isTrusted}
      onDecide={(d) => decide(c.actionId, d)}
      onTimeout={() => dispatch({ type: 'confirmation_timeout', actionId: c.actionId })}
      onDismiss={() => dispatch({ type: 'confirmation_dismiss' })}
    />
  );
}
