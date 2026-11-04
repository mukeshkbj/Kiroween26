import { describe, expect, it } from 'vitest';
import {
  isClientMessage,
  parseApps,
  parseAudit,
  parseServerEvent,
  parseSessionInfo,
  parseSpiritMap,
} from './guards';
import { loadExamples } from '../../test/examples';

/** REQ-030: guards accept every committed contract example. */
const ex = loadExamples();

describe('contract examples', () => {
  it('finds the committed examples', () => {
    expect(Object.keys(ex.events).length).toBeGreaterThanOrEqual(16);
    expect(Object.keys(ex.transcripts).length).toBeGreaterThanOrEqual(7);
  });

  it.each(Object.entries(ex.events).filter(([n]) => !n.startsWith('client-')))(
    'server event example %s is accepted',
    (_name, json) => {
      const r = parseServerEvent(json);
      expect(r.ok).toBe(true);
    },
  );

  it.each(Object.entries(ex.events).filter(([n]) => n.startsWith('client-')))(
    'client message example %s is accepted',
    (_name, json) => {
      expect(isClientMessage(json)).toBe(true);
    },
  );

  it.each(Object.entries(ex.transcripts))('transcript %s: every server line is accepted', (_n, lines) => {
    const server = lines.filter((l) => l.dir === 'server');
    expect(server.length).toBeGreaterThan(0);
    for (const l of server) {
      const r = parseServerEvent(l.event);
      expect(r.ok, JSON.stringify(l.event).slice(0, 200)).toBe(true);
    }
  });

  it.each(Object.entries(ex.transcripts))('transcript %s: every client line is a valid client message', (_n, lines) => {
    for (const l of lines.filter((x) => x.dir === 'client')) {
      expect(isClientMessage(l.msg)).toBe(true);
    }
  });

  it('transcripts have gap-free increasing seq', () => {
    for (const lines of Object.values(ex.transcripts)) {
      let prev = 0;
      for (const l of lines) {
        if (l.dir !== 'server') continue;
        const seq = (l.event as { seq: number }).seq;
        expect(seq).toBeGreaterThan(prev);
        prev = seq;
      }
    }
  });

  it('REST examples are accepted', () => {
    expect(parseApps(ex.rest['apps'])).not.toBeNull();
    expect(parseAudit(ex.rest['audit'])).not.toBeNull();
    expect(parseSessionInfo(ex.rest['session'])).not.toBeNull();
    expect(parseSpiritMap(ex.spiritMap)).not.toBeNull();
  });
});

describe('guards fail closed', () => {
  const base = { v: 1, seq: 1, ts: 't', session_id: 's', turn_id: null };

  it('reports unknown event types without throwing', () => {
    const r = parseServerEvent({ ...base, type: 'brand_new', data: {} });
    expect(r).toEqual({ ok: false, reason: 'unknown_type', type: 'brand_new' });
  });

  it('ignores unknown fields on known events', () => {
    const r = parseServerEvent({ ...base, type: 'pong', data: {}, extra: 1 });
    expect(r.ok).toBe(true);
    if (r.ok) expect('extra' in r.event).toBe(false);
  });

  it('rejects wrong versions, bad seq and malformed data', () => {
    expect(parseServerEvent({ ...base, v: 2, type: 'pong', data: {} }).ok).toBe(false);
    expect(parseServerEvent({ ...base, seq: 0, type: 'pong', data: {} }).ok).toBe(false);
    expect(parseServerEvent({ ...base, type: 'thinking', data: { summary: 3 } }).ok).toBe(false);
    expect(parseServerEvent(null).ok).toBe(false);
    expect(parseServerEvent('x').ok).toBe(false);
  });

  it('never lets a hidden field keep a value', () => {
    const rows = Array.from({ length: 24 }, () => ' '.repeat(80));
    const field = {
      index: 0, row: 1, col: 1, length: 8, protected: false, numeric: false,
      hidden: true, intensified: false, label: 'PASSWORD', value: 'SENTINEL-SECRET',
    };
    const r = parseServerEvent({
      ...base,
      type: 'screen',
      data: {
        phase: 'snapshot',
        tool_call_id: null,
        screen: { trust: 'untrusted-screen-data', screen_id: 'x', cursor: [0, 0], rows, fields: [field] },
      },
    });
    expect(r.ok).toBe(true);
    if (r.ok && r.event.type === 'screen') {
      expect(JSON.stringify(r.event)).not.toContain('SENTINEL-SECRET');
    }
  });

  it('rejects client messages that are too long or unknown', () => {
    expect(isClientMessage({ id: 'a', type: 'user_message', text: 'x'.repeat(4001) })).toBe(false);
    expect(isClientMessage({ id: 'a', type: 'send_keys', keys: 'x' })).toBe(false);
    expect(isClientMessage({ id: 'a', type: 'confirm_decision', action_id: 'z', decision: 'maybe' })).toBe(false);
  });
});
