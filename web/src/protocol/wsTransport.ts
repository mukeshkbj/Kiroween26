import { parseSessionInfo } from './guards';
import {
  Emitter,
  dispatchFrame,
  realTimer,
  type Timer,
  type Transport,
  type TransportHandlers,
  type Unsubscribe,
} from './transport';
import { PROTOCOL_VERSION, type ClientMessage, type SessionInfo } from './types';

/**
 * Live transport (contracts 4.1): GET /api/session -> token, open /ws/seance, first message `hello` with the token
 * and `resume_from`. Reconnects with backoff (1s, 2s, 4s, 8s, then 15s) and resumes from the last applied `seq`.
 * The token lives only in this closure's memory.
 */

export interface WebSocketLike {
  readyState: number;
  send(data: string): void;
  close(code?: number): void;
  onopen: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev: { code: number }) => void) | null;
  onerror: ((ev: unknown) => void) | null;
}

export const WS_OPEN = 1;
export const BACKOFF_MS: readonly number[] = [1000, 2000, 4000, 8000, 15000];
/** Origin not allowed (contracts 4.1). Retrying cannot help. */
export const CLOSE_FORBIDDEN_ORIGIN = 4403;

export interface WsOptions {
  agentUrl: string;
  fetchSession?: () => Promise<SessionInfo>;
  /** What the store has applied so far; used for `resume_from`. */
  getResume: () => { sessionId: string | null; lastSeq: number };
  createSocket?: (url: string) => WebSocketLike;
  timer?: Timer;
  backoffMs?: readonly number[];
  newId?: () => string;
  clientName?: string;
}

export function wsUrlFor(agentUrl: string): string {
  const u = new URL('/ws/seance', agentUrl);
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
  return u.toString();
}

export async function fetchSessionInfo(agentUrl: string, f: typeof fetch = fetch): Promise<SessionInfo> {
  const res = await f(new URL('/api/session', agentUrl).toString(), { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`session ${res.status}`);
  const info = parseSessionInfo(await res.json());
  if (!info) throw new Error('session response not understood');
  return info;
}

export class WebSocketTransport implements Transport {
  readonly kind = 'live' as const;
  private out = new Emitter();
  private socket: WebSocketLike | null = null;
  private ready = false;
  private closed = false;
  private started = false;
  private attempt = 0;
  private cancelTimer: (() => void) | null = null;
  private idN = 0;
  private readonly timer: Timer;
  private readonly backoff: readonly number[];

  constructor(private readonly o: WsOptions) {
    this.timer = o.timer ?? realTimer;
    this.backoff = o.backoffMs ?? BACKOFF_MS;
  }

  subscribe(h: TransportHandlers): Unsubscribe {
    return this.out.subscribe(h);
  }

  start(): void {
    if (this.started || this.closed) return;
    this.started = true;
    this.connect();
  }

  send(msg: ClientMessage): boolean {
    // `hello` is the transport's own business; anything else needs an open, greeted socket. No queueing.
    if (msg.type === 'hello' || !this.socket || !this.ready || this.socket.readyState !== WS_OPEN) return false;
    try {
      this.socket.send(JSON.stringify(msg));
      return true;
    } catch {
      return false;
    }
  }

  requestResume(): void {
    if (this.closed || !this.socket) return;
    this.dropSocket();
    this.cancelTimer?.();
    this.cancelTimer = null;
    this.out.status('reconnecting');
    this.connect();
  }

  close(): void {
    this.closed = true;
    this.cancelTimer?.();
    this.cancelTimer = null;
    this.dropSocket();
    this.out.status('closed');
  }

  private nextId(): string {
    return this.o.newId ? this.o.newId() : `h_${++this.idN}`;
  }

  private dropSocket(): void {
    const s = this.socket;
    this.socket = null;
    this.ready = false;
    if (s) {
      s.onopen = s.onmessage = s.onclose = s.onerror = null;
      try {
        s.close(1000);
      } catch {
        /* already closed */
      }
    }
  }

  private connect(): void {
    if (this.closed) return;
    this.out.status(this.attempt === 0 ? 'connecting' : 'reconnecting');
    const getSession = this.o.fetchSession ?? (() => fetchSessionInfo(this.o.agentUrl));
    getSession().then(
      (info) => {
        if (!this.closed) this.open(info);
      },
      () => this.scheduleRetry(),
    );
  }

  private open(info: SessionInfo): void {
    const url = wsUrlFor(this.o.agentUrl);
    const sock = this.o.createSocket ? this.o.createSocket(url) : (new WebSocket(url) as unknown as WebSocketLike);
    this.socket = sock;
    this.ready = false;
    sock.onopen = () => {
      if (this.socket !== sock) return;
      const resume = this.o.getResume();
      // A different session id means the agent restarted: ask for a fresh start rather than a resume.
      const resumeFrom = resume.sessionId === info.session_id && resume.lastSeq > 0 ? resume.lastSeq : null;
      sock.send(
        JSON.stringify({
          id: this.nextId(),
          type: 'hello',
          v: PROTOCOL_VERSION,
          client: this.o.clientName ?? 'seance-web/0.1.0',
          token: info.token,
          resume_from: resumeFrom,
        }),
      );
      this.ready = true;
      this.out.status('open');
    };
    sock.onmessage = (ev) => {
      if (this.socket !== sock) return;
      if (typeof ev.data !== 'string') {
        this.out.invalid(null);
        return;
      }
      if (dispatchFrame(ev.data, this.out)) this.attempt = 0; // a valid event proves the link works
    };
    sock.onclose = (ev) => {
      if (this.socket !== sock) return;
      this.socket = null;
      this.ready = false;
      if (this.closed) return;
      if (ev.code === CLOSE_FORBIDDEN_ORIGIN) {
        this.closed = true;
        this.out.status('closed', 'forbidden_origin');
        return;
      }
      this.scheduleRetry();
    };
    sock.onerror = () => {
      /* a close event follows; nothing to do */
    };
  }

  private scheduleRetry(): void {
    if (this.closed) return;
    this.out.status('reconnecting');
    const ms = this.backoff[Math.min(this.attempt, this.backoff.length - 1)] ?? 15000;
    this.attempt += 1;
    this.cancelTimer = this.timer(() => {
      this.cancelTimer = null;
      this.connect();
    }, ms);
  }
}
