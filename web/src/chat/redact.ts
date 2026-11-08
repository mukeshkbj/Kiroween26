/**
 * Display helpers for tool-call arguments (REQ-009). The server already redacts arguments "like the audit log",
 * so the UI's job is only to present them safely and never to reconstruct a secret. As defence in depth we also
 * mask any value whose key looks like a credential, and we never render objects as raw HTML.
 */

const SECRET_KEY = /(pass|pwd|secret|token|pin|credential|apikey|api_key)/i;

export interface Arg {
  key: string;
  value: string;
}

function show(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return '[unserialisable]';
  }
}

export function redactArguments(args: Record<string, unknown>): Arg[] {
  return Object.entries(args).map(([key, value]) => ({
    key,
    value: SECRET_KEY.test(key) ? '<redacted>' : show(value),
  }));
}
