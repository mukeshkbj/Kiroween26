import { strings } from '../strings';
import type { AppState } from '../state/reducer';
import type { Message } from '../state/reducer';

/**
 * Empty / error banners (REQ-012). Each state gives a plain-language message and its next action. Derived from
 * AppState so there is one source of truth; the banner is non-intrusive (a status region) except session loss
 * and the agent being unreachable, which offer a reconnect button.
 */

export interface StateBannerProps {
  state: AppState;
  onReconnect: () => void;
}

interface Banner {
  level: 'info' | 'warn' | 'error';
  text: string;
  action?: { label: string; onClick: () => void };
}

function lastToolError(messages: Message[]): Message | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m && m.kind === 'system' && m.level === 'error' && m.code && m.code !== 'resync') return m;
  }
  return null;
}

export function bannerFor(state: AppState, onReconnect: () => void): Banner | null {
  if (state.connection === 'closed') return { level: 'error', text: strings.states.unreachable, action: { label: strings.states.reconnect, onClick: onReconnect } };
  if (state.connection === 'reconnecting') return { level: 'warn', text: strings.states.reconnecting };
  if (state.session.state === 'session_lost')
    return { level: 'error', text: strings.states.sessionLost, action: { label: strings.states.reconnect, onClick: onReconnect } };
  if (state.observerOnly) return { level: 'info', text: strings.states.observerOnly };
  if (state.session.readOnly) return { level: 'warn', text: strings.states.readOnlyServer };
  if (state.session.llm && !state.session.llm.available) return { level: 'warn', text: strings.states.llmUnavailable };
  const err = lastToolError(state.messages);
  if (err && err.kind === 'system' && err.code) return { level: 'error', text: strings.states.toolError(err.code, err.text) };
  return null;
}

export function StateBanner({ state, onReconnect }: StateBannerProps) {
  const banner = bannerFor(state, onReconnect);
  if (!banner) return null;
  return (
    <div className={`state-banner state-banner-${banner.level}`} role={banner.level === 'error' ? 'alert' : 'status'}>
      <span className="state-banner-text">{banner.text}</span>
      {banner.action && (
        <button type="button" className="state-banner-action" onClick={banner.action.onClick}>
          {banner.action.label}
        </button>
      )}
    </div>
  );
}
