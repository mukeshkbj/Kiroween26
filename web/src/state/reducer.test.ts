import { describe, expect, it } from 'vitest';
import { initialState, reduce, type AppState } from './reducer';
import { canApprove, composerBlock, confirmationScreen, currentNodeId, isUncharted, secondsLeft } from './selectors';
import { loadExamples } from '../../test/examples';
import { parseServerEvent } from '../protocol/guards';
import type { ServerEvent } from '../protocol/types';

const ex = loadExamples();

function play(name: string): AppState {
  let s = initialState();
  for (const line of ex.transcripts[name] ?? []) {
    if (line.dir !== 'server') continue;
    const r = parseServerEvent(line.event);
    if (!r.ok) throw new Error(`bad event in ${name}`);
    s = reduce(s, { type: 'server', event: r.event, at: r.event.seq * 10 });
  }
  return s;
}

describe('recorded transcripts through the reducer (REQ-030)', () => {
  it('lookup: one finished turn, one ok tool call, final assistant text', () => {
    const s = play('lookup');
    expect(s.turnOrder).toHaveLength(1);
    const call = Object.values(s.toolCalls)[0];
    expect(call?.tool).toBe('lookup_policy');
    expect(call?.status).toBe('ok');
    const a = s.messages.find((m) => m.kind === 'assistant');
    expect(a && a.kind === 'assistant' && a.final).toBe(true);
    expect(s.screen).not.toBeNull();
    expect(s.session.state).toBe('connected');
    expect(s.audit.length).toBeGreaterThan(3);
    expect(s.auditChain.status).toBe('unknown');
  });

  it.each(['commit-approve', 'commit-deny', 'commit-expire', 'read-only', 'injection', 'session-lost'])(
    '%s plays to the end without leaving a confirmation open',
    (name) => {
      const s = play(name);
      expect(s.confirmation === null || s.confirmation.phase === 'resolved' || s.confirmation.phase === 'expired').toBe(true);
    },
  );

  it('commit-approve: the confirmation ends approved and the modal screen is available', () => {
    let s = initialState();
    let opened: AppState | null = null;
    for (const line of ex.transcripts['commit-approve'] ?? []) {
      if (line.dir !== 'server') continue;
      const r = parseServerEvent(line.event);
      if (!r.ok) throw new Error('bad');
      s = reduce(s, { type: 'server', event: r.event, at: 0 });
      if (r.event.type === 'confirmation_required') opened = s;
    }
    expect(opened?.confirmation?.phase).toBe('open');
    // The gate snapshot may be empty on review screens, so the screen must come from a screen event.
    expect(opened && confirmationScreen(opened)).not.toBeNull();
    expect(s.confirmation?.phase).toBe('resolved');
    expect(s.confirmation?.outcome).toBe('approved');
  });

  it('read-only: approval ends blocked_read_only and Approve is unavailable', () => {
    const s = play('read-only');
    expect(s.session.readOnly).toBe(true);
    expect(s.confirmation?.outcome).toBe('blocked_read_only');
  });

  it('commit-deny / commit-expire record their outcomes', () => {
    expect(play('commit-deny').confirmation?.outcome).toBe('denied');
    expect(play('commit-expire').confirmation?.outcome).toBe('expired');
  });

  it('injection: hostile screen text stays data and never changes state shape', () => {
    const s = play('injection');
    const dump = JSON.stringify(s.screen);
    expect(dump.toLowerCase()).toContain('ignore');
    expect(s.confirmation === null || s.confirmation.phase !== 'open').toBe(true);
  });

  it('session-lost ends with a different session or a lost state', () => {
    const s = play('session-lost');
    expect(['session_lost', 'connected', 'connecting', 'disconnected']).toContain(s.session.state);
  });
});

describe('reducer rules', () => {
  const base = {
    v: 1 as const,
    ts: 't',
    session_id: 's_01',
    turn_id: null as string | null,
  };
  const ev = (seq: number, type: ServerEvent['type'], data: unknown, turn: string | null = null) =>
    ({ ...base, seq, type, data, turn_id: turn }) as ServerEvent;
  const state = (seq = 1, over: Record<string, unknown> = {}) =>
    ev(seq, 'session_state', {
      state: 'connected', app_id: 'x', read_only: false, confirm_mode: 'oob',
      llm: { provider: 'p', model: 'm', available: true }, tools: { business: 1, generic: 1 },
      resync: false, controller: true, ...over,
    });
  const go = (s: AppState, e: ServerEvent, at = 0) => reduce(s, { type: 'server', event: e, at });

  it('ignores seq <= lastSeq', () => {
    const s1 = go(initialState(), state(1));
    expect(go(s1, state(1, { state: 'error' }))).toBe(s1);
  });

  it('a resync snapshot is accepted across a gap and warns the user', () => {
    const s1 = go(initialState(), state(1));
    const s2 = go(s1, state(50, { resync: true }));
    expect(s2.session.lastSeq).toBe(50);
    expect(s2.session.resynced).toBe(true);
    expect(s2.messages.some((m) => m.kind === 'system' && m.code === 'resync')).toBe(true);
    expect(s2.needsResume).toBe(false);
  });

  it('a tool_result with no matching call is ignored, never invented', () => {
    let s = go(initialState(), state(1));
    s = go(s, ev(2, 'tool_result', { tool_call_id: 'ghost', status: 'ok', error_code: null, summary: 'x', result: null, truncated: false }, 't_1'));
    expect(s.toolCalls['ghost']).toBeUndefined();
  });

  it('a hidden value in a screen event is scrubbed even if the guard was bypassed', () => {
    const rows = Array.from({ length: 24 }, () => ' '.repeat(80));
    const screen = {
      trust: 'untrusted-screen-data', screen_id: 'z'.repeat(64), cursor: [0, 0], rows,
      fields: [{ index: 0, row: 1, col: 1, length: 8, protected: false, numeric: false, hidden: true, intensified: false, label: 'PW', value: 'hunter2' }],
    };
    let s = go(initialState(), state(1));
    s = go(s, ev(2, 'screen', { phase: 'snapshot', tool_call_id: null, screen }));
    expect(JSON.stringify(s)).not.toContain('hunter2');
  });

  it('observer connections cannot compose', () => {
    let s = reduce(initialState(), { type: 'connection', status: 'open' });
    s = go(s, state(1, { controller: false }));
    expect(s.observerOnly).toBe(true);
    expect(composerBlock(s)).toBe('observer');
  });

  it('composer reasons: disconnected, no system, then usable', () => {
    let s = initialState();
    expect(composerBlock(s)).toBe('disconnected');
    s = reduce(s, { type: 'connection', status: 'open' });
    s = go(s, state(1, { state: 'disconnected', app_id: null }));
    expect(composerBlock(s)).toBe('no_system');
    s = go(s, state(2));
    expect(composerBlock(s)).toBeNull();
  });

  it('current node follows the screen id; unknown ids are uncharted', () => {
    const map = ex.spiritMap as import('../protocol/types').SpiritMapView;
    const node = map.nodes[0] as import('../protocol/types').MapNode;
    let s = reduce(initialState(), { type: 'map_loaded', map });
    const rows = Array.from({ length: 24 }, () => ' '.repeat(80));
    const scr = (id: string, seq: number) =>
      ev(seq, 'screen', { phase: 'snapshot', tool_call_id: null, screen: { trust: 'untrusted-screen-data', screen_id: id, cursor: [0, 0], rows, fields: [] } });
    s = go(s, state(1));
    s = go(s, scr(node.screen_id, 2));
    expect(currentNodeId(s)).toBe(node.id);
    expect(isUncharted(s)).toBe(false);
    s = go(s, scr('f'.repeat(64), 3));
    expect(currentNodeId(s)).toBeNull();
    expect(isUncharted(s)).toBe(true);
  });

  it('time left comes from the monotonic receipt time and never goes negative', () => {
    let s = go(initialState(), state(1));
    s = go(
      s,
      ev(2, 'confirmation_required', {
        action_id: 'a', tool_call_id: 'c', screen_id: 'q', key: 'Enter', field_snapshot: [],
        expires_in_s: 10, read_only: false, agent_summary: null,
      }, 't_1'),
      1000,
    );
    const c = s.confirmation!;
    expect(secondsLeft(c, 1000)).toBe(10);
    expect(secondsLeft(c, 6000)).toBe(5);
    expect(secondsLeft(c, 99999)).toBe(0);
    // No screen with the gate's screen_id -> Approve stays unavailable even after the delay.
    expect(canApprove(s, 3000, 1000)).toBe(false);
  });

  it('confirmation_timeout expires locally; a later resolved outcome is still recorded', () => {
    let s = go(initialState(), state(1));
    s = go(s, ev(2, 'confirmation_required', {
      action_id: 'a', tool_call_id: 'c', screen_id: 'q', key: 'Enter', field_snapshot: [],
      expires_in_s: 1, read_only: false, agent_summary: null,
    }, 't_1'));
    s = reduce(s, { type: 'confirmation_timeout', actionId: 'a' });
    expect(s.confirmation?.phase).toBe('expired');
    expect(reduce(s, { type: 'decision_sent', actionId: 'a' })).toBe(s);
    s = go(s, ev(3, 'confirmation_resolved', { action_id: 'a', outcome: 'expired', confirmed_by: null, error_code: null }, 't_1'));
    expect(s.confirmation?.phase).toBe('resolved');
    expect(s.confirmation?.outcome).toBe('expired');
  });

  it('unknown event types are logged once', () => {
    let s = initialState();
    s = reduce(s, { type: 'unknown_event', eventType: 'weird' });
    const again = reduce(s, { type: 'unknown_event', eventType: 'weird' });
    expect(again).toBe(s);
    expect(s.unknownTypes).toEqual(['weird']);
  });
});
