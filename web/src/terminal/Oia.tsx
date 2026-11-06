import type { SessionStateName } from '../protocol/types';
import { strings } from '../strings';

/**
 * The 25th line: an operator information area (REQ-003). Connection state, read-only badge, short screen id,
 * keyboard-locked/busy while a tool runs, and an unmissable REPLAY badge in mock mode.
 */

export interface OiaProps {
  sessionState: SessionStateName;
  readOnly: boolean;
  screenId: string | null;
  /** A tool is running: the keyboard would be locked on a real terminal. */
  busy: boolean;
  replay: boolean;
  uncharted: boolean;
}

const shortId = (id: string | null): string => (id ? id.slice(0, 10) : '--------');

export function Oia({ sessionState, readOnly, screenId, busy, replay, uncharted }: OiaProps) {
  return (
    <div className="term-oia" role="status" aria-label={strings.oiaLabel}>
      <span className={`oia-state oia-state-${sessionState}`}>{strings.sessionState[sessionState]}</span>
      {busy ? (
        <span className="oia-lock" data-busy="true">
          {strings.oiaBusy}
        </span>
      ) : (
        <span className="oia-lock" data-busy="false">
          {strings.oiaReady}
        </span>
      )}
      {readOnly && <span className="oia-badge oia-readonly">{strings.readOnly}</span>}
      {uncharted && <span className="oia-badge oia-uncharted">{strings.uncharted}</span>}
      <span className="oia-screenid" title={screenId ?? undefined}>
        {strings.oiaScreen} {shortId(screenId)}
      </span>
      {replay && (
        <span className="oia-badge oia-replay" data-replay="true">
          {strings.replayBadge}
        </span>
      )}
    </div>
  );
}
