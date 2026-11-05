import type {
  AuditEntry,
  AuditResponse,
  FieldFocus,
  FieldSnap,
  LlmInfo,
  ResolvedOutcome,
  ScreenOut,
  ServerEvent,
  SessionStateName,
  SpiritMapView,
  ToolKind,
  ToolStatus,
  TurnReason,
} from '../protocol/types';

/**
 * The single source of truth. Pure: (state, action) -> state. No clocks, no randomness, no I/O.
 * Time enters only through `action.at` (a monotonic millisecond reading taken by the store).
 */

export type ConnectionStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';
export type EffectsLevel = 'full' | 'low' | 'off';
export type TabName = 'screen' | 'seance';
export type PaneView = 'terminal' | 'map';

export interface UiState {
  effects: EffectsLevel;
  reduceMotion: boolean;
  drawerOpen: boolean;
  tab: TabName;
  pane: PaneView;
  screenAsText: boolean;
}

export interface SessionState {
  id: string | null;
  lastSeq: number;
  state: SessionStateName;
  readOnly: boolean;
  llm: LlmInfo | null;
  appId: string | null;
  tools: { business: number; generic: number };
  controller: boolean;
  /** True when the server told us events were missed (resync) and the log is incomplete. */
  resynced: boolean;
}

export interface ScreenState {
  screenId: string;
  rows: string[];
  fields: ScreenOut['fields'];
  cursor: [number, number];
}

export type MessageStatus = 'sent' | 'acked' | 'failed';

export type Message =
  | { kind: 'user'; id: string; text: string; status: MessageStatus }
  | { kind: 'assistant'; id: string; turnId: string | null; text: string; final: boolean }
  | { kind: 'system'; id: string; level: 'info' | 'warn' | 'error'; code: string | null; text: string };

export type Step = { kind: 'thinking'; id: string; summary: string } | { kind: 'tool'; id: string; callId: string };

export interface ToolCallState {
  id: string;
  turnId: string | null;
  tool: string;
  toolKind: ToolKind;
  arguments: Record<string, unknown>;
  mayCommit: boolean | null;
  status: 'running' | ToolStatus;
  errorCode: string | null;
  summary: string | null;
  result: Record<string, unknown> | null;
  truncated: boolean;
}

export interface TurnState {
  id: string;
  status: 'running' | 'finished';
  reason: TurnReason | null;
  userMessageId: string | null;
  steps: Step[];
}

export type ConfirmationPhase = 'open' | 'sending' | 'expired' | 'resolved';

export interface Confirmation {
  actionId: string;
  toolCallId: string;
  turnId: string | null;
  screenId: string;
  key: string;
  fieldSnapshot: FieldSnap[];
  expiresInS: number;
  /** Monotonic reading (ms) when the event was received; time left is computed from it. */
  receivedAt: number;
  readOnly: boolean;
  /** Written by the model; never authoritative. */
  agentSummary: string | null;
  phase: ConfirmationPhase;
  outcome: ResolvedOutcome | null;
  errorCode: string | null;
  confirmedBy: string | null;
}

export type ChainStatus = 'ok' | 'broken' | 'unknown';

export interface AppState {
  session: SessionState;
  screen: ScreenState | null;
  /** Latest screen seen for each screen_id (bounded); the confirmation modal draws from here. */
  screensById: Record<string, ScreenState>;
  messages: Message[];
  turns: Record<string, TurnState>;
  turnOrder: string[];
  toolCalls: Record<string, ToolCallState>;
  focusQueue: (FieldFocus & { seq: number })[];
  confirmation: Confirmation | null;
  audit: AuditEntry[];
  auditChain: { status: ChainStatus; brokenSeq: number | null };
  map: SpiritMapView | null;
  connection: ConnectionStatus;
  observerOnly: boolean;
  /** Set when a gap in `seq` was seen: the store should send hello{resume_from: session.lastSeq}. */
  needsResume: boolean;
  unknownTypes: string[];
  ui: UiState;
}

export const MAX_FOCUS_QUEUE = 50;
export const MAX_SCREENS_CACHE = 24;
export const MAX_AUDIT = 5000;

export const defaultUi: UiState = {
  effects: 'low',
  reduceMotion: false,
  drawerOpen: false,
  tab: 'screen',
  pane: 'terminal',
  screenAsText: false,
};

const freshSession = (): SessionState => ({
  id: null,
  lastSeq: 0,
  state: 'disconnected',
  readOnly: false,
  llm: null,
  appId: null,
  tools: { business: 0, generic: 0 },
  controller: false,
  resynced: false,
});

export function initialState(ui: Partial<UiState> = {}): AppState {
  return {
    session: freshSession(),
    screen: null,
    screensById: {},
    messages: [],
    turns: {},
    turnOrder: [],
    toolCalls: {},
    focusQueue: [],
    confirmation: null,
    audit: [],
    auditChain: { status: 'unknown', brokenSeq: null },
    map: null,
    connection: 'connecting',
    observerOnly: false,
    needsResume: false,
    unknownTypes: [],
    ui: { ...defaultUi, ...ui },
  };
}

export type Action =
  | { type: 'server'; event: ServerEvent; at: number }
  | { type: 'unknown_event'; eventType: string }
  | { type: 'user_sent'; id: string; text: string }
  | { type: 'connection'; status: ConnectionStatus }
  | { type: 'resume_requested' }
  | { type: 'focus_done'; seq: number }
  | { type: 'decision_sent'; actionId: string }
  | { type: 'confirmation_timeout'; actionId: string }
  | { type: 'confirmation_dismiss' }
  | { type: 'audit_loaded'; response: AuditResponse }
  | { type: 'map_loaded'; map: SpiritMapView | null }
  | { type: 'send_failed'; id: string }
  | { type: 'ui'; patch: Partial<UiState> };

// ---- helpers ---------------------------------------------------------------

/** REQ-022: nothing hidden is ever stored. The guard already nulls these; the reducer does not rely on it. */
export function scrubScreen(s: ScreenOut): ScreenState {
  return {
    screenId: s.screen_id,
    rows: s.rows,
    cursor: s.cursor,
    fields: s.fields.map((f) => (f.hidden && f.value !== null ? { ...f, value: null } : f)),
  };
}

const sysId = (seq: number, tag: string) => `sys:${seq}:${tag}`;

function addSystem(
  s: AppState,
  seq: number,
  tag: string,
  level: 'info' | 'warn' | 'error',
  code: string | null,
  text: string,
): AppState {
  const id = sysId(seq, tag);
  if (s.messages.some((m) => m.id === id)) return s;
  return { ...s, messages: [...s.messages, { kind: 'system', id, level, code, text }] };
}

function ensureTurn(s: AppState, turnId: string): AppState {
  if (s.turns[turnId]) return s;
  const turn: TurnState = { id: turnId, status: 'running', reason: null, userMessageId: null, steps: [] };
  return { ...s, turns: { ...s.turns, [turnId]: turn }, turnOrder: [...s.turnOrder, turnId] };
}

function withTurn(s: AppState, turnId: string, f: (t: TurnState) => TurnState): AppState {
  const t = s.turns[turnId];
  return t ? { ...s, turns: { ...s.turns, [turnId]: f(t) } } : s;
}

function upsertAssistant(
  s: AppState,
  id: string,
  turnId: string | null,
  f: (m: Extract<Message, { kind: 'assistant' }> | null) => Extract<Message, { kind: 'assistant' }> | null,
): AppState {
  const i = s.messages.findIndex((m) => m.kind === 'assistant' && m.id === id);
  const prev = i >= 0 ? (s.messages[i] as Extract<Message, { kind: 'assistant' }>) : null;
  const next = f(prev ?? null);
  if (next === null || next === prev) return s;
  const messages = s.messages.slice();
  if (i >= 0) messages[i] = next;
  else messages.push({ ...next, turnId: next.turnId ?? turnId });
  return { ...s, messages };
}

function rememberScreen(s: AppState, screen: ScreenState): AppState {
  const rest = { ...s.screensById };
  delete rest[screen.screenId];
  rest[screen.screenId] = screen; // re-insert -> most recent last
  const ids = Object.keys(rest);
  for (const old of ids.slice(0, Math.max(0, ids.length - MAX_SCREENS_CACHE))) delete rest[old];
  return { ...s, screen, screensById: rest };
}

/** Insert into the seq-ordered audit list, de-duplicated by entry.seq. */
export function mergeAudit(list: AuditEntry[], incoming: AuditEntry[]): AuditEntry[] {
  const bySeq = new Map<number, AuditEntry>();
  for (const e of list) bySeq.set(e.seq, e);
  for (const e of incoming) if (!bySeq.has(e.seq)) bySeq.set(e.seq, e);
  const out = [...bySeq.values()].sort((a, b) => a.seq - b.seq);
  return out.length > MAX_AUDIT ? out.slice(out.length - MAX_AUDIT) : out;
}

const closedForDecision = (c: Confirmation): Confirmation =>
  c.phase === 'resolved' || c.phase === 'expired' ? c : { ...c, phase: 'expired' };

// ---- the reducer -----------------------------------------------------------

export function reduce(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'server':
      return reduceServer(state, action.event, action.at);

    case 'unknown_event':
      return state.unknownTypes.includes(action.eventType)
        ? state
        : { ...state, unknownTypes: [...state.unknownTypes, action.eventType] };

    case 'user_sent':
      if (state.messages.some((m) => m.id === action.id)) return state;
      return { ...state, messages: [...state.messages, { kind: 'user', id: action.id, text: action.text, status: 'sent' }] };

    case 'send_failed': {
      // The transport could not send the message. It is NOT retried; mark it so the UI can say so.
      const i = state.messages.findIndex((m) => m.kind === 'user' && m.id === action.id);
      if (i < 0) return state;
      const messages = state.messages.slice();
      messages[i] = { ...(messages[i] as Extract<Message, { kind: 'user' }>), status: 'failed' };
      return { ...state, messages };
    }

    case 'connection':
      return state.connection === action.status ? state : { ...state, connection: action.status };

    case 'resume_requested':
      return state.needsResume ? { ...state, needsResume: false } : state;

    case 'focus_done':
      return state.focusQueue.some((f) => f.seq <= action.seq)
        ? { ...state, focusQueue: state.focusQueue.filter((f) => f.seq > action.seq) }
        : state;

    case 'decision_sent': {
      const c = state.confirmation;
      // Exactly one decision per confirmation: only an open one can move to "sending".
      if (!c || c.actionId !== action.actionId || c.phase !== 'open') return state;
      return { ...state, confirmation: { ...c, phase: 'sending' } };
    }

    case 'confirmation_timeout': {
      const c = state.confirmation;
      if (!c || c.actionId !== action.actionId || c.phase === 'resolved' || c.phase === 'expired') return state;
      return { ...state, confirmation: { ...c, phase: 'expired' } };
    }

    case 'confirmation_dismiss':
      return state.confirmation && state.confirmation.phase !== 'open' && state.confirmation.phase !== 'sending'
        ? { ...state, confirmation: null }
        : state;

    case 'audit_loaded': {
      const audit = mergeAudit(state.audit, action.response.entries);
      return {
        ...state,
        audit,
        auditChain: {
          status: action.response.chain_ok ? 'ok' : 'broken',
          brokenSeq: action.response.broken_seq,
        },
      };
    }

    case 'map_loaded':
      return { ...state, map: action.map };

    case 'ui':
      return { ...state, ui: { ...state.ui, ...action.patch } };
  }
}

function resetForNewSession(s: AppState): AppState {
  return {
    ...initialState(s.ui),
    connection: s.connection,
    map: s.map,
    unknownTypes: s.unknownTypes,
    // Local user messages from the dead session are dropped with the rest of its history.
  };
}

function reduceServer(prev: AppState, ev: ServerEvent, at: number): AppState {
  let s = prev;

  // A different session id means the agent restarted: discard state, keep UI preferences.
  if (s.session.id !== null && s.session.id !== ev.session_id) s = resetForNewSession(s);

  const isResync = ev.type === 'session_state' && ev.data.resync;
  if (ev.seq <= s.session.lastSeq && s.session.id === ev.session_id) return s;

  // A fresh (or just reset) client has no baseline. A session starts at seq 1 or with a resync snapshot;
  // anything else arriving first means we missed the start: do not guess, ask for a resume.
  if (s.session.lastSeq === 0 && !(ev.seq === 1 || isResync)) {
    return s.needsResume ? s : { ...s, needsResume: true };
  }

  // Gap: we missed events. Do not apply out-of-order; ask for a resume. (Resync snapshots are the exception.)
  if (s.session.lastSeq > 0 && ev.seq > s.session.lastSeq + 1 && !isResync) {
    return s.needsResume ? s : { ...s, needsResume: true };
  }

  s = { ...s, needsResume: false, session: { ...s.session, id: ev.session_id, lastSeq: ev.seq } };
  return applyEvent(s, ev, at);
}

function applyEvent(s: AppState, ev: ServerEvent, at: number): AppState {
  switch (ev.type) {
    case 'session_state': {
      const d = ev.data;
      let next: AppState = {
        ...s,
        observerOnly: !d.controller,
        session: {
          ...s.session,
          state: d.state,
          readOnly: d.read_only,
          llm: d.llm,
          appId: d.app_id,
          tools: d.tools,
          controller: d.controller,
          resynced: d.resync ? true : s.session.resynced,
        },
      };
      if (d.resync) {
        // We lost events: what we show may be stale. Say so, drop queued animation, close any decision.
        next = {
          ...next,
          focusQueue: [],
          confirmation: next.confirmation ? closedForDecision(next.confirmation) : null,
        };
        next = addSystem(next, ev.seq, 'resync', 'warn', 'resync', 'Reconnected. Some activity was missed, so the log may be incomplete.');
      }
      if (d.state !== 'connected' && d.state !== 'connecting' && next.confirmation) {
        next = { ...next, confirmation: closedForDecision(next.confirmation) };
      }
      return next;
    }

    case 'ack': {
      const i = s.messages.findIndex((m) => m.kind === 'user' && m.id === ev.data.ref);
      if (i < 0) return s;
      const messages = s.messages.slice();
      messages[i] = { ...(messages[i] as Extract<Message, { kind: 'user' }>), status: 'acked' };
      return { ...s, messages };
    }

    case 'turn_started': {
      if (ev.turn_id === null) return s;
      const known = s.turns[ev.turn_id];
      if (known) return withTurn(s, ev.turn_id, (t) => ({ ...t, userMessageId: ev.data.user_message_id }));
      const turn: TurnState = {
        id: ev.turn_id,
        status: 'running',
        reason: null,
        userMessageId: ev.data.user_message_id,
        steps: [],
      };
      return { ...s, turns: { ...s.turns, [ev.turn_id]: turn }, turnOrder: [...s.turnOrder, ev.turn_id] };
    }

    case 'thinking': {
      if (ev.turn_id === null) return s;
      const t = ensureTurn(s, ev.turn_id);
      return withTurn(t, ev.turn_id, (x) => ({
        ...x,
        steps: [...x.steps, { kind: 'thinking', id: `think:${ev.seq}`, summary: ev.data.summary }],
      }));
    }

    case 'assistant_delta': {
      const { message_id: id, text } = ev.data;
      return upsertAssistant(s, id, ev.turn_id, (m) => {
        if (m === null) return { kind: 'assistant', id, turnId: ev.turn_id, text, final: false };
        if (m.final) return m; // the final text is authoritative; late deltas are ignored
        return { ...m, text: m.text + text };
      });
    }

    case 'assistant_message': {
      const { message_id: id, text } = ev.data;
      return upsertAssistant(s, id, ev.turn_id, (m) =>
        m === null ? { kind: 'assistant', id, turnId: ev.turn_id, text, final: true } : { ...m, text, final: true },
      );
    }

    case 'tool_call': {
      const d = ev.data;
      if (s.toolCalls[d.tool_call_id]) return s; // a call id is used once
      const call: ToolCallState = {
        id: d.tool_call_id,
        turnId: ev.turn_id,
        tool: d.tool,
        toolKind: d.kind,
        arguments: d.arguments,
        mayCommit: d.may_commit,
        status: 'running',
        errorCode: null,
        summary: null,
        result: null,
        truncated: false,
      };
      let next: AppState = { ...s, toolCalls: { ...s.toolCalls, [d.tool_call_id]: call } };
      if (ev.turn_id !== null) {
        next = ensureTurn(next, ev.turn_id);
        next = withTurn(next, ev.turn_id, (t) => ({
          ...t,
          steps: [...t.steps, { kind: 'tool', id: `tool:${d.tool_call_id}`, callId: d.tool_call_id }],
        }));
      }
      return next;
    }

    case 'tool_result': {
      const d = ev.data;
      const call = s.toolCalls[d.tool_call_id];
      if (!call || call.status !== 'running') return s; // unmatched or duplicate result: never invent a call
      return {
        ...s,
        toolCalls: {
          ...s.toolCalls,
          [d.tool_call_id]: {
            ...call,
            status: d.status,
            errorCode: d.error_code,
            summary: d.summary,
            result: d.result,
            truncated: d.truncated,
          },
        },
      };
    }

    case 'screen':
      return rememberScreen(s, scrubScreen(ev.data.screen));

    case 'field_focus': {
      const queue = [...s.focusQueue, { ...ev.data, seq: ev.seq }];
      return { ...s, focusQueue: queue.length > MAX_FOCUS_QUEUE ? queue.slice(queue.length - MAX_FOCUS_QUEUE) : queue };
    }

    case 'confirmation_required': {
      const d = ev.data;
      let next = s;
      const old = s.confirmation;
      if (old && (old.phase === 'open' || old.phase === 'sending')) {
        next = addSystem(next, ev.seq, 'superseded', 'warn', 'superseded', 'An earlier confirmation was replaced by a newer one.');
      }
      const c: Confirmation = {
        actionId: d.action_id,
        toolCallId: d.tool_call_id,
        turnId: ev.turn_id,
        screenId: d.screen_id,
        key: d.key,
        fieldSnapshot: d.field_snapshot,
        expiresInS: d.expires_in_s,
        receivedAt: at,
        readOnly: d.read_only,
        agentSummary: d.agent_summary,
        phase: 'open',
        outcome: null,
        errorCode: null,
        confirmedBy: null,
      };
      return { ...next, confirmation: c };
    }

    case 'confirmation_resolved': {
      const d = ev.data;
      const c = s.confirmation;
      if (!c || c.actionId !== d.action_id) {
        return addSystem(s, ev.seq, 'orphan-resolved', 'info', 'unknown_action', `A confirmation outcome (${d.outcome}) arrived for an action this screen is not showing.`);
      }
      if (c.phase === 'resolved') return s; // exactly one outcome per confirmation
      const next: AppState = {
        ...s,
        confirmation: { ...c, phase: 'resolved', outcome: d.outcome, errorCode: d.error_code, confirmedBy: d.confirmed_by },
      };
      return addSystem(next, ev.seq, 'resolved', d.outcome === 'approved' ? 'info' : 'warn', `confirmation_${d.outcome}`, `Confirmation ${d.outcome.replace(/_/g, ' ')}.`);
    }

    case 'audit_entry': {
      const audit = mergeAudit(s.audit, [ev.data.entry]);
      const grew = audit.length !== s.audit.length || audit[audit.length - 1] !== s.audit[s.audit.length - 1];
      if (!grew) return s;
      // The UI cannot verify hashes. After a live append the chain status is honestly "unknown".
      return { ...s, audit, auditChain: { status: s.auditChain.status === 'broken' ? 'broken' : 'unknown', brokenSeq: s.auditChain.brokenSeq } };
    }

    case 'turn_finished': {
      if (ev.turn_id === null) return s;
      let next = ensureTurn(s, ev.turn_id);
      next = withTurn(next, ev.turn_id, (t) => (t.status === 'finished' ? t : { ...t, status: 'finished', reason: ev.data.reason }));
      // Any assistant text still streaming for this turn is complete now.
      next = {
        ...next,
        messages: next.messages.map((m) =>
          m.kind === 'assistant' && m.turnId === ev.turn_id && !m.final ? { ...m, final: true } : m,
        ),
      };
      return next;
    }

    case 'error': {
      const d = ev.data;
      let next = s;
      if (d.code === 'observer_only') next = { ...next, observerOnly: true };
      if (d.ref !== null) {
        const i = next.messages.findIndex((m) => m.kind === 'user' && m.id === d.ref);
        if (i >= 0) {
          const messages = next.messages.slice();
          messages[i] = { ...(messages[i] as Extract<Message, { kind: 'user' }>), status: 'failed' };
          next = { ...next, messages };
        }
      }
      return addSystem(next, ev.seq, 'error', 'error', d.code, d.message);
    }

    case 'pong':
      return s;
  }
}
