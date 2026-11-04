/** TypeScript mirror of docs/contracts.md sections 3, 4, 5 and 7.3. All positions are 0-origin. */

export const PROTOCOL_VERSION = 1;

// ---- 3. Shared data shapes -------------------------------------------------

export interface FieldOut {
  index: number;
  row: number;
  col: number;
  length: number;
  protected: boolean;
  numeric: boolean;
  hidden: boolean;
  intensified: boolean;
  label: string | null;
  /** Always null when hidden. */
  value: string | null;
}

export interface ScreenOut {
  trust: 'untrusted-screen-data';
  screen_id: string;
  cursor: [number, number];
  rows: string[];
  fields: FieldOut[];
}

export interface FieldSnap {
  index: number;
  row: number;
  col: number;
  label: string | null;
  value: string | null;
}

export interface AuditEntry {
  seq: number;
  ts: string;
  tool: string;
  outcome: string;
  screen_id: string | null;
  field: string | null;
  value: string | null;
  key: string | null;
  action_id: string | null;
  confirmed_by: string | null;
  detail: string | null;
  prev_hash: string;
  hash: string;
}

// ---- 4.3 Server events -----------------------------------------------------

export type SessionStateName = 'disconnected' | 'connecting' | 'connected' | 'session_lost' | 'error';

export interface LlmInfo {
  provider: string;
  model: string;
  available: boolean;
}

export interface SessionStateData {
  state: SessionStateName;
  app_id: string | null;
  read_only: boolean;
  confirm_mode: 'oob';
  llm: LlmInfo;
  tools: { business: number; generic: number };
  resync: boolean;
  controller: boolean;
}

export type ToolKind = 'business' | 'generic';
export type ToolStatus = 'ok' | 'pending' | 'error';
export type FocusMode = 'read' | 'fill' | 'key';
export type ScreenPhase = 'before' | 'after' | 'snapshot';
export type ResolvedOutcome =
  | 'approved'
  | 'denied'
  | 'expired'
  | 'superseded'
  | 'blocked_read_only'
  | 'stale'
  | 'error';
export type TurnReason = 'completed' | 'cancelled' | 'error' | 'max_steps';

export interface FieldFocus {
  tool_call_id: string;
  step: number;
  mode: FocusMode;
  screen_id: string;
  field_index: number | null;
  row: number | null;
  col: number | null;
  length: number | null;
  label: string | null;
  key: string | null;
}

export interface EventDataMap {
  session_state: SessionStateData;
  ack: { ref: string };
  turn_started: { user_message_id: string };
  thinking: { summary: string };
  assistant_delta: { message_id: string; text: string };
  assistant_message: { message_id: string; text: string };
  tool_call: {
    tool_call_id: string;
    tool: string;
    kind: ToolKind;
    arguments: Record<string, unknown>;
    may_commit: boolean | null;
  };
  screen: { phase: ScreenPhase; tool_call_id: string | null; screen: ScreenOut };
  field_focus: FieldFocus;
  tool_result: {
    tool_call_id: string;
    status: ToolStatus;
    error_code: string | null;
    summary: string;
    result: Record<string, unknown> | null;
    truncated: boolean;
  };
  confirmation_required: {
    action_id: string;
    tool_call_id: string;
    screen_id: string;
    key: string;
    field_snapshot: FieldSnap[];
    expires_in_s: number;
    read_only: boolean;
    agent_summary: string | null;
  };
  confirmation_resolved: {
    action_id: string;
    outcome: ResolvedOutcome;
    confirmed_by: string | null;
    error_code: string | null;
  };
  audit_entry: { entry: AuditEntry };
  turn_finished: {
    reason: TurnReason;
    usage: { input_tokens: number; output_tokens: number } | null;
  };
  error: { code: string; message: string; recoverable: boolean; ref: string | null };
  pong: Record<string, never>;
}

export type ServerEventType = keyof EventDataMap;
export const SERVER_EVENT_TYPES: readonly ServerEventType[] = [
  'session_state',
  'ack',
  'turn_started',
  'thinking',
  'assistant_delta',
  'assistant_message',
  'tool_call',
  'screen',
  'field_focus',
  'tool_result',
  'confirmation_required',
  'confirmation_resolved',
  'audit_entry',
  'turn_finished',
  'error',
  'pong',
];

interface Envelope {
  v: 1;
  seq: number;
  ts: string;
  session_id: string;
  turn_id: string | null;
}

export type ServerEvent = {
  [K in ServerEventType]: Envelope & { type: K; data: EventDataMap[K] };
}[ServerEventType];

export type EventOf<K extends ServerEventType> = Extract<ServerEvent, { type: K }>;

// ---- 4.4 Client messages ---------------------------------------------------

export type ClientMessage =
  | { id: string; type: 'hello'; v: 1; client: string; token: string; resume_from: number | null }
  | { id: string; type: 'connect_system'; app_id: string }
  | { id: string; type: 'user_message'; text: string }
  | { id: string; type: 'confirm_decision'; action_id: string; decision: 'approve' | 'deny' }
  | { id: string; type: 'cancel_turn'; turn_id: string }
  | { id: string; type: 'ping' };

export type ClientMessageType = ClientMessage['type'];
export const CLIENT_MESSAGE_TYPES: readonly ClientMessageType[] = [
  'hello',
  'connect_system',
  'user_message',
  'confirm_decision',
  'cancel_turn',
  'ping',
];

// ---- 5. REST ---------------------------------------------------------------

export interface AppInfo {
  app_id: string;
  name: string;
  kind: 'fake' | 'live';
  description: string;
  reachable: boolean | null;
  has_map: boolean;
  tools: { business: number; approved: number };
  read_only: boolean;
}

export interface SessionInfo {
  token: string;
  session_id: string;
  v: 1;
}

export interface AuditResponse {
  entries: AuditEntry[];
  chain_ok: boolean;
  broken_seq: number | null;
}

export interface HealthResponse {
  ok: boolean;
  version: string;
  live_allowed: boolean;
}

// ---- 7.3 SpiritMapView -----------------------------------------------------

export interface MapField {
  key: string;
  label: string;
  business_name: string | null;
  role: string | null;
  row: number;
  col: number;
  length: number;
  protected: boolean;
  hidden: boolean;
}

export interface MapNode {
  id: string;
  screen_id: string;
  name: string;
  kind: string;
  confidence: number;
  needs_review: boolean;
  visits: number;
  preview: string[];
  fields: MapField[];
}

export interface MapEdge {
  id: string;
  from: string;
  to: string;
  key: string;
  meaning: string | null;
  read_only: boolean;
  status: 'observed' | 'declared';
}

export interface MapFrontier {
  from: string;
  key: string;
  reason: string;
  meaning: string | null;
}

export interface MapTool {
  name: string;
  kind: 'read' | 'commit';
  approved: boolean;
  path: string[];
}

export interface SpiritMapView {
  app_id: string;
  version: string;
  generated_at: string;
  home: string;
  nodes: MapNode[];
  edges: MapEdge[];
  frontier: MapFrontier[];
  tools: MapTool[];
}
