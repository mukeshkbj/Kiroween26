import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TerminalPane } from './TerminalPane';
import { scrubScreen } from '../state/reducer';
import { parseServerEvent } from '../protocol/guards';
import { loadExamples } from '../../test/examples';
import type { ScreenState } from '../state/reducer';

const ex = loadExamples();

function menu(): ScreenState {
  const r = parseServerEvent(ex.events['screen']);
  if (!r.ok || r.event.type !== 'screen') throw new Error('no screen');
  return scrubScreen(r.event.data.screen);
}

beforeEach(() => {
  (Element.prototype as unknown as { animate: unknown }).animate = () => ({
    addEventListener() {}, removeEventListener() {}, cancel() {}, finish() {},
  });
});

const base = {
  screenName: 'Main menu' as string | null,
  sessionState: 'connected' as const,
  readOnly: false,
  busy: false,
  replay: false,
  uncharted: false,
  focusQueue: [],
  reduceMotion: false,
  effects: 'low' as const,
  showAsText: false,
};

describe('TerminalPane (3.5 composition)', () => {
  it('dormant before a connection: blank grid, dormant message, no screen id', () => {
    render(<TerminalPane {...base} screen={null} screenName={null} sessionState="disconnected" />);
    expect(screen.getByText(/dormant/i)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /uncharted/i })).toBeInTheDocument();
  });

  it('populated: renders the menu text and the effects overlay as a separate layer', () => {
    const { container } = render(<TerminalPane {...base} screen={menu()} />);
    expect(container.textContent).toContain('SEANCE INSURANCE - MAIN MENU');
    const overlay = container.querySelector('.crt-overlay') as HTMLElement;
    expect(overlay.getAttribute('aria-hidden')).toBe('true');
    expect(container.querySelector('.term-screen')?.getAttribute('data-effects')).toBe('low');
  });

  it('effects level is a data attribute only; text is unchanged across levels', () => {
    const s = menu();
    const a = render(<TerminalPane {...base} screen={s} effects="off" />);
    const textOff = a.container.querySelector('.term-grid')?.textContent;
    a.unmount();
    const b = render(<TerminalPane {...base} screen={s} effects="full" />);
    expect(b.container.querySelector('.term-grid')?.textContent).toBe(textOff);
  });

  it('planchette mid-glide: a fill focus event on the screen shown renders the lens; one for another screen does not', () => {
    const shown = menu();
    const other = [{ seq: 2, tool_call_id: 'c', step: 0, mode: 'fill' as const, screen_id: 'not-this-screen', field_index: 1, row: 7, col: 15, length: 1, label: 'OPTION ===>', key: null }];
    const r0 = render(<TerminalPane {...base} screen={shown} focusQueue={other} />);
    expect(r0.container.querySelector('.planchette')).toBeNull();
    r0.unmount();
    const q = [{ seq: 1, tool_call_id: 'c', step: 0, mode: 'fill' as const, screen_id: shown.screenId, field_index: 1, row: 7, col: 15, length: 1, label: 'OPTION ===>', key: null }];
    const { container } = render(<TerminalPane {...base} screen={shown} focusQueue={q} />);
    expect(container.querySelector('.planchette')).not.toBeNull();
  });

  it('shows the screen-as-text alternative when toggled on', () => {
    render(<TerminalPane {...base} screen={menu()} showAsText={true} />);
    expect(screen.getByLabelText(/Screen as text/i)).toBeInTheDocument();
  });
});
