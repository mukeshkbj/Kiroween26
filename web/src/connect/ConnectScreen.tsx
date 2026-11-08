import { SystemCard } from './SystemCard';
import { strings } from '../strings';
import type { AppInfo } from '../protocol/types';

/**
 * The connect screen (REQ-010). Lists systems from GET /api/apps as cards and sends connect_system on choice.
 * Loading, empty, and error states each state what happened and the next action.
 *
 * C-2/C-3 (2026-11-06): it can be reopened while connected ("Change system", with a way back), the buttons stay
 * disabled until the agent has answered this connection's hello (a click before that was silently lost), and a
 * send that fails says so instead of doing nothing.
 */

export type AppsLoad =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; apps: AppInfo[] };

export interface ConnectScreenProps {
  load: AppsLoad;
  onConnect: (appId: string) => void;
  onRetry: () => void;
  connecting?: boolean;
  /** The agent has answered our hello and we are the controller. `undefined` = treat as ready (older callers). */
  ready?: boolean;
  /** Why the buttons are disabled when not ready (waiting for the agent, or this tab is an observer). */
  blockedReason?: string | null;
  /** Why the last attempt did nothing, e.g. "not sent". */
  notice?: string | null;
  /** The system connected now, marked on its card. */
  currentAppId?: string | null;
  /** Present when the screen was reopened over a live session: closes it without changing anything. */
  onBack?: () => void;
}

export function ConnectScreen({ load, onConnect, onRetry, connecting, ready = true, blockedReason, notice, currentAppId, onBack }: ConnectScreenProps) {
  const disabled = connecting || !ready;
  return (
    <section className="connect" aria-label={strings.connect.heading}>
      <h2>{strings.connect.heading}</h2>
      <p>{strings.connect.intro}</p>
      {onBack && (
        <button type="button" className="connect-back" onClick={onBack}>
          {strings.connect.back}
        </button>
      )}

      {!ready && load.status === 'ready' && load.apps.length > 0 && (
        <p className="connect-waiting" role="status">
          {blockedReason ?? strings.states.waitingForAgent}
        </p>
      )}
      {notice && (
        <p className="connect-notice" role="alert" data-testid="connect-not-sent">
          {notice}
        </p>
      )}

      {load.status === 'loading' && <p className="connect-loading">{strings.connect.loading}</p>}

      {load.status === 'error' && (
        <div className="connect-error" role="alert">
          <p>{strings.connect.loadError}</p>
          <button type="button" onClick={onRetry}>
            {strings.connect.retry}
          </button>
        </div>
      )}

      {load.status === 'ready' && load.apps.length === 0 && <p className="connect-empty">{strings.connect.none}</p>}

      {load.status === 'ready' && load.apps.length > 0 && (
        <ul className="system-list">
          {load.apps.map((app) => (
            <SystemCard key={app.app_id} app={app} onConnect={onConnect} disabled={disabled} current={app.app_id === currentAppId} />
          ))}
        </ul>
      )}
    </section>
  );
}
