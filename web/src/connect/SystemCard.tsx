import type { AppInfo } from '../protocol/types';
import { strings } from '../strings';

/**
 * One system in the connect list (REQ-010): name, kind (simulated / live), reachability, spirit-map and tool
 * counts, read-only badge. Reachability and kind are shown as text + icon, never colour alone (REQ-020).
 */

export interface SystemCardProps {
  app: AppInfo;
  onConnect: (appId: string) => void;
  disabled?: boolean;
}

function reachText(app: AppInfo): string {
  if (app.kind === 'fake') return strings.connect.simulated;
  if (app.reachable === true) return strings.connect.reachable;
  if (app.reachable === false) return strings.connect.unreachable;
  return strings.connect.reachUnknown;
}

export function SystemCard({ app, onConnect, disabled }: SystemCardProps) {
  const cannotReach = app.kind === 'live' && app.reachable === false;
  return (
    <li className="system-card" data-kind={app.kind}>
      <div className="system-head">
        <h3 className="system-name">{app.name}</h3>
        <span className={`system-kind system-kind-${app.kind}`}>{app.kind === 'fake' ? strings.connect.simulated : strings.connect.live}</span>
      </div>
      <p className="system-desc">{app.description}</p>
      <ul className="system-meta">
        <li data-reachable={String(app.reachable)}>{reachText(app)}</li>
        <li>{app.has_map ? strings.connect.hasMap : strings.connect.noMap}</li>
        <li>{strings.connect.toolsLabel(app.tools.business, app.tools.approved)}</li>
        {app.read_only && <li className="system-readonly">{strings.readOnly}</li>}
      </ul>
      <button
        type="button"
        className="system-connect"
        onClick={() => onConnect(app.app_id)}
        disabled={disabled || cannotReach}
        aria-describedby={cannotReach ? `reach-${app.app_id}` : undefined}
      >
        {strings.connect.connectBtn}
      </button>
      {cannotReach && (
        <p id={`reach-${app.app_id}`} className="system-reach-note">
          {strings.connect.unreachable}
        </p>
      )}
    </li>
  );
}
