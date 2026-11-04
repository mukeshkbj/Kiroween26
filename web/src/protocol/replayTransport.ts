import { isClientMessage } from './guards';
import { Emitter, dispatchRaw, realTimer, type Timer, type Transport, type TransportHandlers, type Unsubscribe } from './transport';
import type { ClientMessage } from './types';
import type { TranscriptLine } from './transcript';

/**
 * Plays a recorded transcript (docs/contracts/examples/transcripts/*.jsonl) through the same Transport interface
 * as the real websocket (REQ-023). Server lines are emitted `delay_ms / speed` after the previous line. Client
 * lines make the player wait until the user does the same kind of action; the first `hello` is satisfied at once.
 */

export interface ReplayOptions {
  lines: TranscriptLine[];
  /** Playback speed multiplier (VITE_REPLAY_SPEED). */
  speed?: number;
  timer?: Timer;
}

export class ReplayTransport implements Transport {
  readonly kind = 'replay' as const;
  private out = new Emitter();
  private i = 0;
  private cancel: (() => void) | null = null;
  private started = false;
  private closed = false;
  private waiting: ClientMessage | null = null;
  private readonly timer: Timer;
  private readonly speed: number;
  /** Messages the script was not waiting for. Kept for the UI hint and for tests. */
  rejected: ClientMessage[] = [];

  constructor(private readonly opts: ReplayOptions) {
    this.timer = opts.timer ?? realTimer;
    this.speed = opts.speed && opts.speed > 0 ? opts.speed : 1;
  }

  subscribe(h: TransportHandlers): Unsubscribe {
    return this.out.subscribe(h);
  }

  /** The user action the replay is waiting for, or null while it is playing. */
  expecting(): ClientMessage | null {
    return this.waiting;
  }

  get finished(): boolean {
    return this.i >= this.opts.lines.length && this.waiting === null;
  }

  start(): void {
    if (this.started || this.closed) return;
    this.started = true;
    this.out.status('open');
    this.step();
  }

  requestResume(): void {
    /* a recording has nothing to resume */
  }

  send(msg: ClientMessage): boolean {
    if (!isClientMessage(msg) || this.closed) return false;
    const want = this.waiting;
    if (want && this.matches(want, msg)) {
      this.waiting = null;
      this.step();
      return true;
    }
    if (msg.type !== 'ping') this.rejected.push(msg);
    return false;
  }

  close(): void {
    this.closed = true;
    this.cancel?.();
    this.cancel = null;
    this.waiting = null;
    this.out.status('closed');
  }

  private matches(want: ClientMessage, got: ClientMessage): boolean {
    if (want.type !== got.type) return false;
    // A scripted "deny" must not play out as the result of the user pressing Approve.
    if (want.type === 'confirm_decision' && got.type === 'confirm_decision') return want.decision === got.decision;
    return true;
  }

  private step(): void {
    this.cancel = null;
    if (this.closed) return;
    const line = this.opts.lines[this.i];
    if (!line) return;
    if (line.dir === 'client') {
      this.i += 1;
      const msg = line.msg as ClientMessage;
      if (msg.type === 'hello') {
        // The transport itself says hello; the recording's hello is already satisfied.
        this.step();
      } else {
        this.waiting = msg;
      }
      return;
    }
    this.cancel = this.timer(() => {
      if (this.closed) return;
      this.i += 1;
      dispatchRaw(line.event, this.out);
      this.step();
    }, Math.max(0, line.delay_ms / this.speed));
  }
}
