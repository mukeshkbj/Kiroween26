import fc from 'fast-check';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createRef } from 'react';
import { AuditDrawer } from './AuditDrawer';
import { FILTERS, exportAudit, filterEntries, outcomeGroup, shortTime, windowSlice, VIRTUALISE_ABOVE } from './filter';
import { initialState, reduce } from '../state/reducer';
import { parseAudit } from '../protocol/guards';
import { loadExamples } from '../../test/examples';
import type { AuditEntry } from '../protocol/types';

const ex = loadExamples();
const restAudit = parseAudit(ex.rest['audit']);

const entry = (seq: number, outcome: string, over: Partial<AuditEntry> = {}): AuditEntry => ({
  seq, ts: `2026-11-24T10:15:30.${String(seq).padStart(6, '0')}+00:00`, tool: 'press_key', outcome,
  screen_id: 'a'.repeat(64), field: null, value: null, key: 'Enter', action_id: null, confirmed_by: 'n/a',
  detail: null, prev_hash: '0'.repeat(64), hash: String(seq).padStart(64, '0'), ...over,
});

const base = {
  open: true,
  chain: { status: 'ok' as const, brokenSeq: null },
  onClose: () => {},
};

describe('audit filter (pure)', () => {
  it('every known outcome belongs to exactly one group; unknown outcomes appear only under "all"', () => {
    const known = ['ok','error','proposed','superseded','rejected','expired','stale_screen','blocked_read_only','needs_resync','ambiguous_ack','session_lost','field_invalid','not_connected','confirmation_unavailable','awaiting_oob','unknown_action'];
    for (const o of known) expect(outcomeGroup(o), o).not.toBeNull();
    expect(outcomeGroup('something_new')).toBeNull();
    const entries = [entry(1, 'something_new'), entry(2, 'ok')];
    expect(filterEntries(entries, 'all')).toHaveLength(2);
    for (const f of FILTERS.filter((x) => x !== 'all')) {
      expect(filterEntries(entries, f).every((e) => e.outcome !== 'something_new')).toBe(true);
    }
  });

  it('the groups partition any list of known outcomes', () => {
    const outcomes = ['ok', 'proposed', 'blocked_read_only', 'rejected', 'expired', 'awaiting_oob'];
    fc.assert(
      fc.property(fc.array(fc.constantFrom(...outcomes), { maxLength: 40 }), (os) => {
        const entries = os.map((o, i) => entry(i + 1, o));
        const parts = FILTERS.filter((f) => f !== 'all').flatMap((f) => filterEntries(entries, f));
        expect(parts.length).toBe(entries.length);
        expect(new Set(parts.map((e) => e.seq)).size).toBe(entries.length);
      }),
    );
  });

  it('export keeps entries exactly as received', () => {
    const e = [entry(1, 'ok', { ts: '2026-11-24T10:15:30.123000+00:00' })];
    expect(JSON.parse(exportAudit(e))).toEqual(e);
    expect(exportAudit(e)).toContain('2026-11-24T10:15:30.123000+00:00');
  });

  it('shortTime is display-only', () => {
    expect(shortTime('2026-11-24T10:15:30.123000+00:00')).toBe('10:15:30.123');
    expect(shortTime('garbage')).toBe('garbage');
  });

  it('windowSlice renders everything at or below the threshold and a bounded slice above it', () => {
    expect(windowSlice(VIRTUALISE_ABOVE, 0, 400, 28)).toMatchObject({ start: 0, end: VIRTUALISE_ABOVE, padTop: 0 });
    fc.assert(
      fc.property(fc.integer({ min: 501, max: 20000 }), fc.integer({ min: 0, max: 600000 }), (total, top) => {
        const w = windowSlice(total, top, 400, 28);
        expect(w.start).toBeGreaterThanOrEqual(0);
        expect(w.end).toBeLessThanOrEqual(total);
        expect(w.end - w.start).toBeLessThan(60);
        expect(w.padTop).toBe(w.start * 28);
        expect(w.padBottom).toBe((total - w.end) * 28);
      }),
    );
  });
});

describe('AuditDrawer (REQ-015)', () => {
  it('is a labelled complementary region listing time, seq, tool, short screen, key, outcome and confirmer', () => {
    const entries = [entry(1, 'ok'), entry(2, 'proposed', { tool: 'press_key', confirmed_by: 'oob:web-ui:s_01' })];
    render(<AuditDrawer {...base} entries={entries} />);
    const region = screen.getByRole('complementary', { name: 'Audit log' });
    const rows = within(region).getAllByRole('row');
    expect(rows).toHaveLength(3); // header + 2
    expect(region.textContent).toContain('aaaaaaaa'); // short screen id
    expect(region.textContent).toContain('oob:web-ui:s_01');
    expect(region.textContent).toContain('10:15:30.000');
  });

  it('shows REST entries as given, including already-redacted values', () => {
    const entries = restAudit?.entries ?? [];
    expect(entries.length).toBeGreaterThan(0);
    render(<AuditDrawer {...base} entries={entries} />);
    expect(screen.getAllByRole('row').length).toBe(entries.length + 1);
  });

  it('filters by outcome', async () => {
    const entries = [entry(1, 'ok'), entry(2, 'blocked_read_only'), entry(3, 'rejected'), entry(4, 'proposed')];
    render(<AuditDrawer {...base} entries={entries} />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText(/Show outcomes/), 'blocked');
    expect(screen.getAllByRole('row')).toHaveLength(2);
    expect(screen.getByText('blocked_read_only')).toBeInTheDocument();
    expect(screen.getByText('1 of 4 entries')).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/Show outcomes/), 'pending');
    expect(screen.getByText('proposed')).toBeInTheDocument();
  });

  it('exports JSON through the export seam', async () => {
    const onExport = vi.fn();
    const entries = [entry(1, 'ok')];
    render(<AuditDrawer {...base} entries={entries} onExport={onExport} />);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Export JSON' }));
    expect(onExport).toHaveBeenCalledOnce();
    expect(JSON.parse(onExport.mock.calls[0]?.[0] as string)).toEqual(entries);
  });

  it('export is the whole log, not the filtered view (found by the 8.2 vibe-coding experiment)', async () => {
    const onExport = vi.fn();
    const entries = [entry(1, 'ok'), entry(2, 'rejected'), entry(3, 'blocked_read_only')];
    render(<AuditDrawer {...base} entries={entries} onExport={onExport} />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText(/Show outcomes/), 'rejected');
    expect(screen.getByText('1 of 3 entries')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Export JSON' }));
    expect(JSON.parse(onExport.mock.calls[0]?.[0] as string)).toEqual(entries);
  });

  it('shows the time of day exactly as the server wrote it, whatever the viewer\'s timezone', () => {
    expect(shortTime('2026-11-24T10:15:30.123000+00:00')).toBe('10:15:30.123');
    expect(shortTime('2026-11-24T23:59:59.000000+00:00')).toBe('23:59:59.000'); // no day rollover from a zone shift
  });
  it('shows chain status honestly: ok / broken at N / unknown', () => {
    const { rerender } = render(<AuditDrawer {...base} entries={[entry(1, 'ok')]} />);
    expect(screen.getByTestId('chain-status')).toHaveTextContent('verified by the server');
    rerender(<AuditDrawer {...base} entries={[entry(1, 'ok')]} chain={{ status: 'broken', brokenSeq: 7 }} />);
    expect(screen.getByTestId('chain-status')).toHaveTextContent('broken at entry 7');
    rerender(<AuditDrawer {...base} entries={[entry(1, 'ok')]} chain={{ status: 'unknown', brokenSeq: null }} />);
    expect(screen.getByTestId('chain-status')).toHaveTextContent('unknown until refreshed');
  });

  it('chain turns "unknown" in state after a live audit_entry append (the UI cannot verify hashes)', () => {
    let s = initialState();
    s = reduce(s, { type: 'audit_loaded', response: { entries: [entry(1, 'ok')], chain_ok: true, broken_seq: null } });
    expect(s.auditChain.status).toBe('ok');
    s = reduce(s, {
      type: 'server', at: 0,
      event: { v: 1, type: 'session_state', seq: 1, ts: 't', session_id: 's', turn_id: null, data: { state: 'connected', app_id: 'x', read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true }, tools: { business: 1, generic: 1 }, resync: false, controller: true } },
    });
    s = reduce(s, { type: 'server', at: 0, event: { v: 1, type: 'audit_entry', seq: 2, ts: 't', session_id: 's', turn_id: null, data: { entry: entry(2, 'ok') } } });
    expect(s.audit).toHaveLength(2);
    expect(s.auditChain.status).toBe('unknown');
    // a broken chain never silently becomes "unknown"
    let b = reduce(initialState(), { type: 'audit_loaded', response: { entries: [entry(1, 'ok')], chain_ok: false, broken_seq: 1 } });
    b = reduce(b, { type: 'server', at: 0, event: { v: 1, type: 'session_state', seq: 1, ts: 't', session_id: 's', turn_id: null, data: { state: 'connected', app_id: 'x', read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true }, tools: { business: 1, generic: 1 }, resync: false, controller: true } } });
    b = reduce(b, { type: 'server', at: 0, event: { v: 1, type: 'audit_entry', seq: 2, ts: 't', session_id: 's', turn_id: null, data: { entry: entry(2, 'ok') } } });
    expect(b.auditChain.status).toBe('broken');
  });

  it('Esc closes and focus returns to the toggle; focus moves in on open', () => {
    const toggle = document.createElement('button');
    document.body.appendChild(toggle);
    const toggleRef = createRef<HTMLElement>();
    (toggleRef as { current: HTMLElement | null }).current = toggle;
    const onClose = vi.fn();
    const { rerender } = render(<AuditDrawer {...base} open={false} entries={[]} onClose={onClose} toggleRef={toggleRef} />);
    rerender(<AuditDrawer {...base} open={true} entries={[]} onClose={onClose} toggleRef={toggleRef} />);
    expect(screen.getByRole('button', { name: 'Close audit log' })).toHaveFocus();
    return userEvent.setup().keyboard('{Escape}').then(() => {
      expect(onClose).toHaveBeenCalledOnce();
      rerender(<AuditDrawer {...base} open={false} entries={[]} onClose={onClose} toggleRef={toggleRef} />);
      expect(toggle).toHaveFocus();
    });
  });

  it('empty states say what happened', () => {
    const { rerender } = render(<AuditDrawer {...base} entries={[]} />);
    expect(screen.getByText('No audit entries yet.')).toBeInTheDocument();
    rerender(<AuditDrawer {...base} entries={[entry(1, 'ok')]} />);
    expect(screen.queryByText('No audit entries yet.')).toBeNull();
  });

  it('with more than 500 entries only a window of rows is in the DOM', () => {
    const many = Array.from({ length: 2000 }, (_, i) => entry(i + 1, 'ok'));
    render(<AuditDrawer {...base} entries={many} />);
    const rows = screen.getAllByRole('row');
    expect(rows.length).toBeLessThan(80);
    expect(screen.getByText('2000 entries')).toBeInTheDocument();
  });

  it('renders server text as text only', () => {
    render(<AuditDrawer {...base} entries={[entry(1, 'ok', { value: '<img src=x onerror=alert(1)>' })]} />);
    expect(document.querySelector('.audit-table img')).toBeNull();
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
  });
});
