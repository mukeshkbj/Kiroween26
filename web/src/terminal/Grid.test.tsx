import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { Grid } from './Grid';
import { ScreenAsText, describeScreen } from './ScreenAsText';
import { Oia } from './Oia';
import { scrubScreen } from '../state/reducer';
import { parseServerEvent } from '../protocol/guards';
import { loadExamples } from '../../test/examples';
import type { FieldOut, ScreenOut } from '../protocol/types';

const ex = loadExamples();

function menuScreen(): ScreenOut {
  const r = parseServerEvent(ex.events['screen']);
  if (!r.ok || r.event.type !== 'screen') throw new Error('no menu screen example');
  return r.event.data.screen;
}

const blankRows = () => Array.from({ length: 24 }, () => ' '.repeat(80));

function field(over: Partial<FieldOut>): FieldOut {
  return {
    index: 0, row: 0, col: 1, length: 1, protected: true, numeric: false, hidden: false,
    intensified: false, label: '', value: '', ...over,
  };
}

describe('Grid (REQ-002)', () => {
  it('renders exactly 24 rows of real text in a labelled region', () => {
    const s = scrubScreen(menuScreen());
    render(<Grid rows={s.rows} fields={s.fields} cursor={s.cursor} screenName="Main menu" />);
    const region = screen.getByRole('region', { name: /3270 screen, Main menu/i });
    expect(region.querySelectorAll('.term-row')).toHaveLength(24);
    expect(region.textContent).toContain('SEANCE INSURANCE - MAIN MENU');
    expect(region.textContent).toContain('POLICY ENQUIRY');
  });

  it('marks unprotected fields as input and labels them for assistive tech', () => {
    const fields = [field({ index: 1, row: 7, col: 15, length: 1, protected: false, label: 'OPTION ===>' })];
    const rows = blankRows();
    render(<Grid rows={rows} fields={fields} cursor={[0, 0]} screenName="menu" />);
    const span = document.querySelector('[data-field="1"]') as HTMLElement;
    expect(span).not.toBeNull();
    expect(span.className).toContain('cell-input');
    expect(span.getAttribute('aria-label')).toMatch(/OPTION, input, 1 characters/);
  });

  it('renders a hidden field as blank cells and keeps its value out of the DOM entirely', () => {
    // The scrubber nulls the value; even if it did not, the renderer never prints it.
    const scrubbed = scrubScreen({
      trust: 'untrusted-screen-data', screen_id: 'x', cursor: [0, 0], rows: blankRows(),
      fields: [field({ index: 2, row: 2, col: 10, length: 8, protected: false, hidden: true, label: 'PASSWORD', value: 'TOPSECRET' })],
    });
    render(<Grid rows={scrubbed.rows} fields={scrubbed.fields} cursor={[0, 0]} screenName="logon" />);
    const span = document.querySelector('[data-field="2"]') as HTMLElement;
    expect(span.getAttribute('data-hidden')).toBe('true');
    expect(span.getAttribute('aria-label')).toMatch(/hidden/);
    expect(document.body.innerHTML).not.toContain('TOPSECRET');
    expect(span.textContent).toBe('        '); // eight blanks
  });

  it('marks numeric and intensified fields with classes, not colour alone', () => {
    const fields = [
      field({ index: 1, row: 3, col: 5, length: 7, protected: false, numeric: true, label: 'PREMIUM' }),
      field({ index: 2, row: 4, col: 5, length: 6, intensified: true }),
    ];
    render(<Grid rows={blankRows()} fields={fields} cursor={[0, 0]} screenName="update" />);
    expect((document.querySelector('[data-field="1"]') as HTMLElement).className).toContain('cell-numeric');
    expect((document.querySelector('[data-field="2"]') as HTMLElement).className).toContain('cell-intense');
  });

  it('draws the cursor as a block at the cursor position', () => {
    const rows = blankRows();
    rows[5] = 'HELLO'.padEnd(80, ' ');
    render(<Grid rows={rows} fields={[]} cursor={[5, 2]} screenName="x" />);
    const cur = document.querySelector('.term-cursor') as HTMLElement;
    expect(cur).not.toBeNull();
    expect(cur.textContent).toBe('L'); // column 2 of "HELLO"
    expect(cur.getAttribute('aria-hidden')).toBe('true');
  });

  it('text is selectable DOM text, not a canvas', () => {
    const s = scrubScreen(menuScreen());
    const { container } = render(<Grid rows={s.rows} fields={s.fields} cursor={s.cursor} screenName="menu" />);
    expect(container.querySelector('canvas')).toBeNull();
  });
});

describe('Oia (REQ-003)', () => {
  it('shows connection state, read-only, short screen id and no replay badge when live', () => {
    render(<Oia sessionState="connected" readOnly={true} screenId={'ab12cd34ef56'} busy={false} replay={false} uncharted={false} />);
    const oia = screen.getByRole('status');
    expect(within(oia).getByText('connected')).toBeInTheDocument();
    expect(within(oia).getByText('read only')).toBeInTheDocument();
    expect(oia.textContent).toContain('ab12cd34ef'); // first 10 hex
    expect(within(oia).queryByText('REPLAY')).toBeNull();
  });

  it('shows the busy (keyboard-locked) marker and the REPLAY badge in mock mode', () => {
    render(<Oia sessionState="connected" readOnly={false} screenId={null} busy={true} replay={true} uncharted={true} />);
    const oia = screen.getByRole('status');
    expect(within(oia).getByText('keyboard locked')).toBeInTheDocument();
    expect(within(oia).getByText('REPLAY')).toBeInTheDocument();
    expect(within(oia).getByText('uncharted')).toBeInTheDocument();
  });
});

describe('ScreenAsText (REQ-019)', () => {
  it('summarises title, input fields and cursor, with hidden values shown as "hidden"', () => {
    const scrubbed = scrubScreen({
      trust: 'untrusted-screen-data', screen_id: 'x', cursor: [7, 14],
      rows: (() => { const r = blankRows(); r[0] = 'POLICY ENQUIRY'.padEnd(80, ' '); return r; })(),
      fields: [
        field({ index: 1, row: 3, col: 13, length: 8, protected: false, label: 'POLNO ===>', value: 'P0000003' }),
        field({ index: 2, row: 5, col: 13, length: 8, protected: false, hidden: true, label: 'PIN', value: '9999' }),
      ],
    });
    const lines = describeScreen({ rows: scrubbed.rows, fields: scrubbed.fields, cursor: scrubbed.cursor, screenName: 'Policy enquiry' });
    const text = lines.join('\n');
    expect(text).toContain('Policy enquiry');
    expect(text).toContain('POLICY ENQUIRY');
    expect(text).toContain('POLNO: P0000003');
    expect(text).toContain('PIN: hidden');
    expect(text).not.toContain('9999');
    expect(text).toContain('row 8, column 15');
    render(<ScreenAsText rows={scrubbed.rows} fields={scrubbed.fields} cursor={scrubbed.cursor} screenName="Policy enquiry" />);
    expect(screen.getByText(/POLNO: P0000003/)).toBeInTheDocument();
  });
});
