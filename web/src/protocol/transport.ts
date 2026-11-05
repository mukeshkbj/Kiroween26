import { parseServerEvent } from './guards';
import type { ClientMessage, ServerEvent } from './types';
import type { ConnectionStatus } from '../state/reducer';

/**
 * What the app talks to. Two implementations: WebSocketTransport (live) and ReplayTransport (mock mode).
 * Neither ever re-sends a message on its own: a user message or a decision that may or may not have arrived is
 * reported as not sent, never retried (mainframe-safety: no dangerous retries).
 */

export interface TransportHandlers {
  /** A validated server event. */
  onEvent(event: ServerEvent): void;
  /** A well-formed envelope with a type this client does not know. */
  onUnknown(type: string): void;
  /** Frame that was not valid JSON or failed validation. The payload is not passed on. */
  onInvalid(type: string | null): void;
  onStatus(status: ConnectionStatus, detail?: string): void;
}

export type Unsubscribe = () => void;

export interface Transport {
  /** Subscribe to events and status; returns an unsubscribe. */
  subscribe(h: TransportHandlers): Unsubscribe;
  /** Begin connecting / playing. Idempotent. */
  start(): void;
  /** Returns true if the message was handed to the wire (or script). Never queues, never retries. */
  send(msg: ClientMessage): boolean;
  /** Ask for a reconnect-and-resume (used after a sequence gap). No-op for replay. */
  requestResume(): void;
  close(): void;
  readonly kind: 'live' | 'replay';
}

export class Emitter {
  private handlers: TransportHandlers[] = [];
  subscribe(h: TransportHandlers): Unsubscribe {
    this.handlers.push(h);
    return () => {
      this.handlers = this.handlers.filter((x) => x !== h);
    };
  }
  event(e: ServerEvent) {
    for (const h of this.handlers) h.onEvent(e);
  }
  unknown(t: string) {
    for (const h of this.handlers) h.onUnknown(t);
  }
  invalid(t: string | null) {
    for (const h of this.handlers) h.onInvalid(t);
  }
  status(s: ConnectionStatus, detail?: string) {
    for (const h of this.handlers) h.onStatus(s, detail);
  }
}

/** Decode one frame / one transcript event through the guards and route the outcome. */
export function dispatchRaw(raw: unknown, out: Emitter): boolean {
  const r = parseServerEvent(raw);
  if (r.ok) {
    out.event(r.event);
    return true;
  }
  if (r.reason === 'unknown_type') out.unknown(r.type);
  else out.invalid(r.type);
  return false;
}

export function dispatchFrame(text: string, out: Emitter): boolean {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    out.invalid(null);
    return false;
  }
  return dispatchRaw(raw, out);
}

export type Timer = (fn: () => void, ms: number) => () => void;

export const realTimer: Timer = (fn, ms) => {
  const id = setTimeout(fn, ms);
  return () => clearTimeout(id);
};
