import { createContext, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from 'react';
import { initialState, reduce, type Action, type AppState, type UiState } from './reducer';
import type { Transport } from '../protocol/transport';
import type { ClientMessage } from '../protocol/types';

/**
 * Owns the reducer and the transport wiring. Server events and connection status flow in; the UI calls the
 * action senders, which produce client messages (never raw keys) and report whether the message reached the
 * wire. On a sequence gap the reducer sets `needsResume`; the store asks the transport to reconnect-and-resume,
 * exactly once per gap. Nothing is ever re-sent automatically (mainframe-safety: no dangerous retries).
 */

export interface StoreApi {
  state: AppState;
  connectSystem: (appId: string) => boolean;
  sendMessage: (text: string) => boolean;
  decide: (actionId: string, decision: 'approve' | 'deny') => boolean;
  cancelTurn: (turnId: string) => boolean;
  dispatch: (action: Action) => void;
}

const Ctx = createContext<StoreApi | null>(null);

export const useStore = (): StoreApi => {
  const s = useContext(Ctx);
  if (!s) throw new Error('useStore outside StoreProvider');
  return s;
};

export interface StoreProviderProps {
  transport: Transport;
  children: ReactNode;
  uiPrefs?: Partial<UiState>;
  /** monotonic clock for confirmation timing; defaults to performance.now. */
  now?: () => number;
  newId?: () => string;
}

let counter = 0;
const defaultId = () => `c${Date.now().toString(36)}_${++counter}`;

export function StoreProvider({ transport, children, uiPrefs, now, newId = defaultId }: StoreProviderProps) {
  const clock = now ?? (() => performance.now());
  const [state, dispatch] = useReducer(reduce, undefined, () => initialState(uiPrefs));
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const unsub = transport.subscribe({
      onEvent: (event) => dispatch({ type: 'server', event, at: clock() }),
      onUnknown: (type) => dispatch({ type: 'unknown_event', eventType: type }),
      onInvalid: () => {
        /* malformed frame: the guard already refused it; nothing to apply */
      },
      onStatus: (status) => dispatch({ type: 'connection', status }),
    });
    transport.start();
    return () => {
      unsub();
      transport.close();
    };
    // one transport per provider instance
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transport]);

  // Honour a resume request the reducer raised after a sequence gap.
  useEffect(() => {
    if (state.needsResume) {
      transport.requestResume();
      dispatch({ type: 'resume_requested' });
    }
  }, [state.needsResume, transport]);

  const api = useMemo<StoreApi>(() => {
    const send = (msg: ClientMessage): boolean => transport.send(msg);
    return {
      state,
      dispatch,
      connectSystem: (appId) => send({ id: newId(), type: 'connect_system', app_id: appId }),
      sendMessage: (text) => {
        const id = newId();
        dispatch({ type: 'user_sent', id, text });
        const ok = send({ id, type: 'user_message', text });
        if (!ok) dispatch({ type: 'send_failed', id });
        return ok;
      },
      decide: (actionId, decision) => {
        const ok = send({ id: newId(), type: 'confirm_decision', action_id: actionId, decision });
        if (ok) dispatch({ type: 'decision_sent', actionId });
        return ok;
      },
      cancelTurn: (turnId) => send({ id: newId(), type: 'cancel_turn', turn_id: turnId }),
    };
    // state is read through the closure; recreate when it changes so `api.state` is fresh
  }, [state, transport, newId, clock]);

  return <Ctx.Provider value={api}>{children}</Ctx.Provider>;
}
