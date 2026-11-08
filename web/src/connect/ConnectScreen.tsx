import { SystemCard } from './SystemCard';
import { strings } from '../strings';
import type { AppInfo } from '../protocol/types';

/**
 * The connect screen (REQ-010). Lists systems from GET /api/apps as cards and sends connect_system on choice.
 * Loading, empty, and error states each state what happened and the next action.
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
}

export function ConnectScreen({ load, onConnect, onRetry, connecting }: ConnectScreenProps) {
  return (
    <section className="connect" aria-label={strings.connect.heading}>
      <h2>{strings.connect.heading}</h2>
      <p>{strings.connect.intro}</p>

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
            <SystemCard key={app.app_id} app={app} onConnect={onConnect} disabled={connecting} />
          ))}
        </ul>
      )}
    </section>
  );
}
