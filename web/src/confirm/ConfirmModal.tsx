import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { createPortal } from 'react-dom';
import { useFocusTrap } from './useFocusTrap';
import { MiniScreen } from './MiniScreen';
import { strings } from '../strings';
import type { Confirmation, ScreenState } from '../state/reducer';
import { APPROVE_DELAY_MS, secondsLeft } from '../state/selectors';

/**
 * The confirmation modal (REQ-016, REQ-017, REQ-029). It is a safety control first and a design piece second.
 *
 *  - Authoritative block: key, screen miniature, fields, time left, read-only banner. All from the gate's fields
 *    and the screen, never from the agent.
 *  - "The agent says (unverified)" is a separate block; its text is never mixed into the authoritative one.
 *  - Deny is the initial focus; Esc means Deny. Approve is disabled for 600 ms and only a trusted user event
 *    (isTrusted) can trigger it. Enter on the dialog does not approve unless Approve itself has focus.
 *  - Exactly one decision: after a click the buttons are gone until the outcome arrives.
 *  - Time left comes from the monotonic receipt time, not server wall-clock.
 */

export interface ConfirmModalProps {
  confirmation: Confirmation;
  /** The screen to draw, or null when none with the gate's screen_id is known (Approve stays disabled). */
  screen: ScreenState | null;
  /** The session is read only (also true when the confirmation itself says so). */
  sessionReadOnly: boolean;
  observerOnly: boolean;
  /** Monotonic ms source. */
  now: () => number;
  onDecide: (decision: 'approve' | 'deny') => void;
  /** The local clock hit zero. */
  onTimeout: () => void;
  onDismiss: () => void;
  /** The element to inert while the dialog is open (the app root). */
  inertRoot?: HTMLElement | null;
  /**
   * Test seam only. Production always uses the browser's `event.isTrusted`. jsdom marks every event untrusted
   * (even element.click() and user-event), so tests inject a predicate to simulate a real user activation.
   */
  isTrusted?: (e: Event) => boolean;
}

const browserIsTrusted = (e: Event): boolean => e.isTrusted === true;

export function ConfirmModal(p: ConfirmModalProps) {
  const c = p.confirmation;
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const denyRef = useRef<HTMLButtonElement | null>(null);
  const [tick, setTick] = useState(0);
  const openedAt = useRef<number>(p.now());
  const decidedRef = useRef(false);

  const active = c.phase === 'open' || c.phase === 'sending';
  useFocusTrap(dialogRef, active, denyRef);

  // Re-render periodically for the countdown and the approve delay. Cheap and independent of the server.
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick((t) => t + 1), 100);
    return () => clearInterval(id);
  }, [active]);

  const nowMs = p.now();
  void tick;
  const left = secondsLeft(c, nowMs);
  const sinceOpen = nowMs - openedAt.current;
  const waitMs = Math.max(0, APPROVE_DELAY_MS - sinceOpen);

  // Expiry: tell the store once; the modal cannot approve after this.
  const timedOut = useRef(false);
  useEffect(() => {
    if (active && left <= 0 && !timedOut.current) {
      timedOut.current = true;
      p.onTimeout();
    }
  });

  // Inert the rest of the app while open.
  useEffect(() => {
    const root = p.inertRoot;
    if (!root || !active) return;
    root.setAttribute('inert', '');
    return () => root.removeAttribute('inert');
  }, [p.inertRoot, active]);

  const decide = (d: 'approve' | 'deny') => {
    if (decidedRef.current) return; // exactly one decision per modal
    decidedRef.current = true;
    p.onDecide(d);
  };

  const readOnly = c.readOnly || p.sessionReadOnly;
  const hasScreen = p.screen !== null;
  const canApprove =
    c.phase === 'open' && !readOnly && !p.observerOnly && hasScreen && left > 0 && waitMs === 0 && !decidedRef.current;

  const onApproveClick = (e: MouseEvent<HTMLButtonElement>) => {
    // A script-dispatched click is not a user. Only trusted events can approve.
    if (!(p.isTrusted ?? browserIsTrusted)(e.nativeEvent)) return;
    if (!canApprove) return;
    decide('approve');
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      if (c.phase === 'open') decide('deny');
    }
  };

  const resolved = c.phase === 'resolved' ? c.outcome : null;

  const body = (
    <div className="modal-backdrop">
      <div
        ref={dialogRef}
        className="modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-desc"
        data-phase={c.phase}
        onKeyDown={onKeyDown}
      >
        <h2 id="confirm-title">{strings.confirm.title}</h2>

        <div id="confirm-desc" className="confirm-authoritative">
          {readOnly && (
            <p className="confirm-readonly" role="note">
              {strings.confirm.readOnlyBanner}
            </p>
          )}

          <p className="confirm-key">
            {strings.confirm.keyLabel}: <kbd className="keycap">{c.key}</kbd>
          </p>

          {hasScreen ? (
            <MiniScreen screen={p.screen as ScreenState} highlights={c.fieldSnapshot} />
          ) : (
            <p className="confirm-noscreen">{strings.confirm.noScreen}</p>
          )}

          <h3 className="confirm-sub">{strings.confirm.fieldsLabel}</h3>
          {c.fieldSnapshot.length === 0 ? (
            <p className="confirm-nofields">{strings.confirm.noFields}</p>
          ) : (
            <ul className="confirm-fields">
              {c.fieldSnapshot.map((f) => (
                <li key={f.index}>
                  <span className="confirm-field-label">{f.label ?? `row ${f.row + 1}, col ${f.col + 1}`}</span>:{' '}
                  <span className="confirm-field-value">
                    {f.value === '<hidden>' || f.value === '<redacted>' || f.value === null ? strings.confirm.hiddenValue : f.value}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {active && (
            <p className="confirm-time" data-seconds={Math.ceil(left)}>
              {strings.confirm.expiresLabel}: {strings.confirm.timeLeft(left)}
            </p>
          )}
        </div>

        {/* Separate, clearly labelled, never mixed with the facts above. */}
        {c.agentSummary && (
          <div className="confirm-agent" data-testid="agent-block">
            <h3 className="confirm-sub">{strings.confirm.agentSays}</h3>
            <p className="confirm-agent-note">{strings.confirm.agentNote}</p>
            <blockquote className="confirm-agent-text">{c.agentSummary}</blockquote>
          </div>
        )}

        <div className="modal-status" role="status" aria-live="polite">
          {c.phase === 'sending' && strings.confirm.sending}
          {c.phase === 'expired' && strings.confirm.expired}
          {resolved && strings.confirm.outcome[resolved]}
        </div>

        <div className="modal-actions">
          {active && c.phase === 'open' && (
            <>
              <button ref={denyRef} type="button" className="btn-deny" onClick={() => decide('deny')}>
                {strings.confirm.deny}
              </button>
              {!readOnly && (
                <button type="button" className="btn-approve" disabled={!canApprove} onClick={onApproveClick} aria-disabled={!canApprove}>
                  {waitMs > 0 ? strings.confirm.approveWait(waitMs) : strings.confirm.approve}
                </button>
              )}
            </>
          )}
          {(c.phase === 'resolved' || c.phase === 'expired') && (
            <button type="button" className="btn-dismiss" onClick={p.onDismiss} autoFocus>
              {strings.confirm.dismiss}
            </button>
          )}
        </div>
        {c.phase === 'open' && <p className="confirm-hint">{strings.confirm.denyHint}</p>}
      </div>
    </div>
  );

  return createPortal(body, document.body);
}
