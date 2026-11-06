import {
  PROTOCOL_VERSION,
  type AppInfo,
  type AuditEntry,
  type AuditResponse,
  type ClientMessage,
  type EventDataMap,
  type FieldOut,
  type FieldSnap,
  type ScreenOut,
  type ServerEvent,
  type ServerEventType,
  type SessionInfo,
  type SpiritMapView,
  CLIENT_MESSAGE_TYPES,
  SERVER_EVENT_TYPES,
} from './types';

/** Runtime validation of everything that comes from the network. Fail closed: invalid -> rejected. */

type Rec = Record<string, unknown>;

const isRec = (v: unknown): v is Rec => typeof v === 'object' && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === 'string';
const isBool = (v: unknown): v is boolean => typeof v === 'boolean';
const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const nullOr = (f: (v: unknown) => boolean) => (v: unknown) => v === null || f(v);
const isArr = (f: (v: unknown) => boolean) => (v: unknown) => Array.isArray(v) && v.every(f);

type Spec = Record<string, (v: unknown) => boolean>;
const shape =
  (spec: Spec) =>
  (v: unknown): v is Rec =>
    isRec(v) && Object.entries(spec).every(([k, f]) => f(v[k]));

export const GRID_ROWS = 24;
export const GRID_COLS = 80;

const isFieldOut = shape({
  index: isInt,
  row: isInt,
  col: isInt,
  length: isInt,
  protected: isBool,
  numeric: isBool,
  hidden: isBool,
  intensified: isBool,
  label: nullOr(isStr),
  value: nullOr(isStr),
});

const isCursor = (v: unknown): boolean =>
  Array.isArray(v) && v.length === 2 && isInt(v[0]) && isInt(v[1]);

const isScreenShape = shape({
  screen_id: isStr,
  cursor: isCursor,
  rows: (v) => Array.isArray(v) && v.length === GRID_ROWS && v.every(isStr),
  fields: isArr(isFieldOut),
  // optional and advisory: absent on older servers, validated when present
  volatile: (v) => v === undefined || isArr((r) => Array.isArray(r) && r.length === 3 && r.every(isInt))(v),
});

/**
 * Validate a ScreenOut and return a normalised copy in which no hidden field can carry a value.
 * (The server already sends null; this is defence in depth, REQ-022.)
 */
export function toScreenOut(v: unknown): ScreenOut | null {
  if (!isScreenShape(v)) return null;
  const fields = (v.fields as FieldOut[]).map((f) => ({
    index: f.index,
    row: f.row,
    col: f.col,
    length: f.length,
    protected: f.protected,
    numeric: f.numeric,
    hidden: f.hidden,
    intensified: f.intensified,
    label: f.label,
    value: f.hidden ? null : f.value,
  }));
  return {
    trust: 'untrusted-screen-data',
    screen_id: v.screen_id as string,
    cursor: [(v.cursor as number[])[0] as number, (v.cursor as number[])[1] as number],
    rows: [...(v.rows as string[])],
    fields,
    ...(Array.isArray(v.volatile) ? { volatile: (v.volatile as [number, number, number][]).map((r) => [r[0], r[1], r[2]] as [number, number, number]) } : {}),
  };
}

export const isAuditEntry = (v: unknown): v is AuditEntry =>
  shape({
    seq: isInt,
    ts: isStr,
    tool: isStr,
    outcome: isStr,
    screen_id: nullOr(isStr),
    field: nullOr(isStr),
    value: nullOr(isStr),
    key: nullOr(isStr),
    action_id: nullOr(isStr),
    confirmed_by: nullOr(isStr),
    detail: nullOr(isStr),
    prev_hash: isStr,
    hash: isStr,
  })(v);

const isFieldSnap = shape({
  index: isInt,
  row: isInt,
  col: isInt,
  label: nullOr(isStr),
  value: nullOr(isStr),
});
export const isFieldSnapshot = (v: unknown): v is FieldSnap => isFieldSnap(v);

const isLlm = shape({ provider: isStr, model: isStr, available: isBool });
const oneOf = (...xs: string[]) => (v: unknown) => isStr(v) && xs.includes(v);

const DATA_CHECKS: { [K in ServerEventType]: (d: Rec) => boolean } = {
  session_state: shape({
    state: oneOf('disconnected', 'connecting', 'connected', 'session_lost', 'error'),
    app_id: nullOr(isStr),
    read_only: isBool,
    confirm_mode: isStr,
    llm: isLlm,
    tools: shape({ business: isInt, generic: isInt }),
    resync: isBool,
    controller: isBool,
  }),
  ack: shape({ ref: isStr }),
  turn_started: shape({ user_message_id: isStr }),
  thinking: shape({ summary: isStr }),
  assistant_delta: shape({ message_id: isStr, text: isStr }),
  assistant_message: shape({ message_id: isStr, text: isStr }),
  tool_call: shape({
    tool_call_id: isStr,
    tool: isStr,
    kind: oneOf('business', 'generic'),
    arguments: isRec,
    may_commit: nullOr(isBool),
  }),
  screen: (d) =>
    shape({
      phase: oneOf('before', 'after', 'snapshot'),
      tool_call_id: nullOr(isStr),
    })(d) && isScreenShape(d.screen),
  field_focus: shape({
    tool_call_id: isStr,
    step: isInt,
    mode: oneOf('read', 'fill', 'key'),
    screen_id: isStr,
    field_index: nullOr(isInt),
    row: nullOr(isInt),
    col: nullOr(isInt),
    length: nullOr(isInt),
    label: nullOr(isStr),
    key: nullOr(isStr),
  }),
  tool_result: shape({
    tool_call_id: isStr,
    status: oneOf('ok', 'pending', 'error'),
    error_code: nullOr(isStr),
    summary: isStr,
    result: nullOr(isRec),
    truncated: isBool,
  }),
  confirmation_required: shape({
    action_id: isStr,
    tool_call_id: isStr,
    screen_id: isStr,
    key: isStr,
    field_snapshot: isArr(isFieldSnapshot),
    expires_in_s: isNum,
    read_only: isBool,
    agent_summary: nullOr(isStr),
  }),
  confirmation_resolved: shape({
    action_id: isStr,
    outcome: oneOf('approved', 'denied', 'expired', 'superseded', 'blocked_read_only', 'stale', 'error'),
    confirmed_by: nullOr(isStr),
    error_code: nullOr(isStr),
  }),
  audit_entry: (d) => isAuditEntry(d.entry),
  turn_finished: shape({
    reason: oneOf('completed', 'cancelled', 'error', 'max_steps'),
    usage: nullOr(shape({ input_tokens: isInt, output_tokens: isInt })),
  }),
  error: shape({ code: isStr, message: isStr, recoverable: isBool, ref: nullOr(isStr) }),
  pong: isRec,
};

export type ParseResult =
  | { ok: true; event: ServerEvent }
  | { ok: false; reason: 'unknown_type'; type: string }
  | { ok: false; reason: 'invalid'; type: string | null };

const KNOWN = new Set<string>(SERVER_EVENT_TYPES);

/** Parse and validate one server event (already JSON-decoded). Unknown fields are ignored, unknown types reported. */
export function parseServerEvent(raw: unknown): ParseResult {
  if (!isRec(raw)) return { ok: false, reason: 'invalid', type: null };
  const type = isStr(raw.type) ? raw.type : null;
  if (type === null) return { ok: false, reason: 'invalid', type: null };
  if (
    raw.v !== PROTOCOL_VERSION ||
    !isInt(raw.seq) ||
    raw.seq < 1 ||
    !isStr(raw.ts) ||
    !isStr(raw.session_id) ||
    !nullOr(isStr)(raw.turn_id) ||
    !isRec(raw.data)
  ) {
    return { ok: false, reason: 'invalid', type };
  }
  if (!KNOWN.has(type)) return { ok: false, reason: 'unknown_type', type };
  const kind = type as ServerEventType;
  if (!DATA_CHECKS[kind](raw.data)) return { ok: false, reason: 'invalid', type };

  let data = raw.data as unknown as EventDataMap[ServerEventType];
  if (kind === 'screen') {
    const d = raw.data as unknown as EventDataMap['screen'];
    const screen = toScreenOut(d.screen);
    if (!screen) return { ok: false, reason: 'invalid', type };
    data = { phase: d.phase, tool_call_id: d.tool_call_id, screen };
  }
  const event = {
    v: 1,
    type: kind,
    seq: raw.seq,
    ts: raw.ts,
    session_id: raw.session_id,
    turn_id: raw.turn_id as string | null,
    data,
  } as ServerEvent;
  return { ok: true, event };
}

export const isServerEvent = (raw: unknown): raw is ServerEvent => parseServerEvent(raw).ok;

/** Client messages: used by conformance tests and by the transports as a last check before sending. */
export function isClientMessage(raw: unknown): raw is ClientMessage {
  if (!isRec(raw) || !isStr(raw.id) || !isStr(raw.type)) return false;
  if (!(CLIENT_MESSAGE_TYPES as readonly string[]).includes(raw.type)) return false;
  switch (raw.type) {
    case 'hello':
      return raw.v === 1 && isStr(raw.client) && isStr(raw.token) && nullOr(isInt)(raw.resume_from);
    case 'connect_system':
      return isStr(raw.app_id);
    case 'user_message':
      return isStr(raw.text) && raw.text.length <= 4000;
    case 'confirm_decision':
      return isStr(raw.action_id) && (raw.decision === 'approve' || raw.decision === 'deny');
    case 'cancel_turn':
      return isStr(raw.turn_id);
    case 'ping':
      return true;
    default:
      return false;
  }
}

// ---- REST ------------------------------------------------------------------

export const isAppInfo = (v: unknown): v is AppInfo =>
  shape({
    app_id: isStr,
    name: isStr,
    kind: oneOf('fake', 'live'),
    description: isStr,
    reachable: nullOr(isBool),
    has_map: isBool,
    tools: shape({ business: isInt, approved: isInt }),
    read_only: isBool,
  })(v);

export const parseApps = (v: unknown): AppInfo[] | null =>
  isRec(v) && Array.isArray(v.apps) && v.apps.every(isAppInfo) ? (v.apps as AppInfo[]) : null;

export const parseSessionInfo = (v: unknown): SessionInfo | null =>
  shape({ token: isStr, session_id: isStr, v: (x) => x === 1 })(v) ? (v as unknown as SessionInfo) : null;

export const parseAudit = (v: unknown): AuditResponse | null =>
  shape({ entries: isArr(isAuditEntry), chain_ok: isBool, broken_seq: nullOr(isInt) })(v)
    ? (v as unknown as AuditResponse)
    : null;

export function parseSpiritMap(v: unknown): SpiritMapView | null {
  const isNode = shape({
    id: isStr,
    screen_id: isStr,
    name: isStr,
    kind: isStr,
    confidence: isNum,
    needs_review: isBool,
    visits: isInt,
    preview: isArr(isStr),
    fields: isArr(
      shape({
        key: isStr,
        label: isStr,
        row: isInt,
        col: isInt,
        length: isInt,
        protected: isBool,
        hidden: isBool,
      }),
    ),
  });
  const ok = shape({
    app_id: isStr,
    version: isStr,
    generated_at: isStr,
    home: isStr,
    nodes: isArr(isNode),
    edges: isArr(
      shape({ id: isStr, from: isStr, to: isStr, key: isStr, read_only: isBool, status: oneOf('observed', 'declared') }),
    ),
    frontier: isArr(shape({ from: isStr, key: isStr, reason: isStr })),
    tools: isArr(shape({ name: isStr, kind: oneOf('read', 'commit'), approved: isBool, path: isArr(isStr) })),
  })(v);
  if (!ok) return null;
  // Previews never carry hidden values per contract; hidden map fields keep no value property at all.
  return v as unknown as SpiritMapView;
}
