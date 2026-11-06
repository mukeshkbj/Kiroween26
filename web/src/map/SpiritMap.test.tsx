import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SpiritMap } from './SpiritMap';
import { MapTable } from './MapTable';
import { MapView } from './MapView';
import { NodePreview } from './NodePreview';
import { initialState, reduce, type AppState } from '../state/reducer';
import { currentNodeId, isUncharted, trailNodeIds } from '../state/selectors';
import { parseSpiritMap } from '../protocol/guards';
import { loadExamples } from '../../test/examples';
import type { ServerEvent, SpiritMapView } from '../protocol/types';

const ex = loadExamples();
const view = parseSpiritMap(ex.spiritMap) as SpiritMapView;
const menu = view.nodes[0]!;
const enquiry = view.nodes[1]!;

describe('SpiritMap SVG (REQ-013)', () => {
  it('draws a node per screen and an edge per key', () => {
    const { container } = render(<SpiritMap view={view} currentNodeId={null} trail={[]} selectedId={null} onSelect={() => {}} />);
    expect(container.querySelectorAll('.map-node')).toHaveLength(view.nodes.length);
    expect(container.querySelectorAll('.map-edge')).toHaveLength(view.edges.length);
  });

  it('highlights the current node with a thick outline and a "you are here" text tag', () => {
    const { container } = render(<SpiritMap view={view} currentNodeId={menu.id} trail={[]} selectedId={null} onSelect={() => {}} />);
    const here = container.querySelector(`[data-node="${menu.id}"]`) as SVGGElement;
    expect(here.classList.contains('node-here')).toBe(true);
    expect(here.querySelector('rect')?.getAttribute('stroke-width')).toBe('4');
    expect(here.textContent).toContain('you are here');
    expect(here.getAttribute('aria-label')).toContain('you are here');
  });

  it('read-only edges are solid; confirmation edges are dashed with a lock AND a text label', () => {
    const edges = [
      { ...view.edges[0]!, id: 'e_ro', read_only: true },
      { ...view.edges[0]!, id: 'e_cf', read_only: false },
    ];
    const { container } = render(<SpiritMap view={{ ...view, edges }} currentNodeId={null} trail={[]} selectedId={null} onSelect={() => {}} />);
    const ro = container.querySelector('[data-edge="e_ro"]') as SVGGElement;
    const cf = container.querySelector('[data-edge="e_cf"]') as SVGGElement;
    expect(ro.classList.contains('edge-solid')).toBe(true);
    expect(ro.querySelector('path')?.getAttribute('stroke-dasharray')).toBeNull();
    expect(cf.classList.contains('edge-dashed')).toBe(true);
    expect(cf.querySelector('path')?.getAttribute('stroke-dasharray')).toBeTruthy();
    expect(cf.textContent).toContain('needs confirmation');
    expect(cf.textContent).toContain('\u{1F512}');
  });

  it('frontier stubs are dashed with a lock and text, never colour alone', () => {
    const { container } = render(<SpiritMap view={view} currentNodeId={null} trail={[]} selectedId={null} onSelect={() => {}} />);
    const stubs = container.querySelectorAll('.map-frontier');
    expect(stubs.length).toBe(view.frontier.length);
    expect(Array.from(stubs).some((s) => s.textContent?.includes('needs confirmation'))).toBe(true);
    for (const s of stubs) {
      expect(s.querySelector('path')?.getAttribute('stroke-dasharray')).toBeTruthy();
      expect(s.textContent).toContain('\u{1F512}');
    }
  });

  it('marks needs_review nodes with a text marker', () => {
    const nodes = view.nodes.map((n, i) => (i === 0 ? { ...n, needs_review: true } : n));
    const { container } = render(<SpiritMap view={{ ...view, nodes }} currentNodeId={null} trail={[]} selectedId={null} onSelect={() => {}} />);
    const g = container.querySelector(`[data-node="${menu.id}"]`) as SVGGElement;
    expect(g.textContent).toContain('needs review');
  });

  it('highlights the path taken in the current tool call', () => {
    const { container } = render(<SpiritMap view={view} currentNodeId={enquiry.id} trail={[menu.id, enquiry.id]} selectedId={null} onSelect={() => {}} />);
    const trailed = container.querySelectorAll('.edge-trail');
    expect(trailed.length).toBeGreaterThan(0);
  });

  it('selecting works by click and by Enter; arrows move focus between nodes', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<SpiritMap view={view} currentNodeId={null} trail={[]} selectedId={null} onSelect={onSelect} />);
    const nodes = Array.from(container.querySelectorAll<SVGGElement>('.map-node'));
    await user.click(nodes[0]!);
    expect(onSelect).toHaveBeenCalledTimes(1);
    nodes[0]!.focus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledTimes(2);
    const first = container.querySelector<SVGGElement>('.map-node')!;
    first.focus();
    await user.keyboard('{ArrowRight}');
    expect(document.activeElement).not.toBe(first);
    expect((document.activeElement as Element).classList.contains('map-node')).toBe(true);
  });
});

describe('MapTable (REQ-014)', () => {
  it('lists each screen with outgoing keys, destinations, confirmation need and tools', () => {
    render(<MapTable view={view} currentNodeId={menu.id} selectedId={null} onSelect={() => {}} />);
    const table = screen.getByRole('table', { name: /Spirit-map as a table/ });
    expect(within(table).getAllByRole('row')).toHaveLength(view.nodes.length + 1);
    expect(table.textContent).toContain('lookup_policy');
    expect(table.textContent).toContain('read-only key');
    expect(table.textContent).toContain('needs confirmation'); // the frontier commit
    const hereRow = table.querySelector(`[data-node-row="${menu.id}"]`);
    expect(hereRow?.getAttribute('aria-current')).toBe('true');
    expect(hereRow?.textContent).toContain('you are here');
  });

  it('Up/Down move between rows and Enter selects', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<MapTable view={view} currentNodeId={null} selectedId={null} onSelect={onSelect} />);
    const buttons = screen.getAllByRole('button');
    buttons[0]!.focus();
    await user.keyboard('{ArrowDown}');
    expect(buttons[1]).toHaveFocus();
    await user.keyboard('{ArrowUp}');
    expect(buttons[0]).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledWith(view.nodes[0]!.id);
  });
});

describe('MapView', () => {
  const base = { currentNodeId: menu.id, uncharted: false, trail: [] as string[] };

  it('shows graph, table (open by default), and a preview of the current node', () => {
    const { container } = render(<MapView view={view} {...base} />);
    expect(container.querySelector('.spirit-map')).not.toBeNull();
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(container.querySelector('.node-preview-screen')?.textContent).toContain('MAIN MENU');
  });

  it('the table is always reachable by a visible toggle', async () => {
    const user = userEvent.setup();
    render(<MapView view={view} {...base} />);
    await user.click(screen.getByRole('button', { name: 'Hide table' }));
    expect(screen.queryByRole('table')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Show table' }));
    expect(screen.getByRole('table')).toBeInTheDocument();
  });

  it('says so when there is no map or it is loading', () => {
    const { rerender } = render(<MapView view={null} {...base} />);
    expect(screen.getByText(/No spirit-map has been generated/)).toBeInTheDocument();
    rerender(<MapView view={null} loading {...base} />);
    expect(screen.getByText(/Loading the spirit-map/)).toBeInTheDocument();
  });

  it('shows the uncharted notice (5.5)', () => {
    render(<MapView view={view} {...base} currentNodeId={null} uncharted />);
    expect(screen.getByRole('status')).toHaveTextContent(/uncharted/);
  });
});

describe('NodePreview', () => {
  it('lists fields by business name and the tools through the node; renders markup as text', () => {
    const node = { ...menu, name: '<b>Menu</b>' };
    render(<NodePreview node={node} tools={view.tools} />);
    expect(screen.getByText('<b>Menu</b>')).toBeInTheDocument();
    expect(document.querySelector('.node-preview b')).toBeNull();
    expect(screen.getByText(/Menu option/)).toBeInTheDocument();
    expect(screen.getAllByText(/lookup_policy/).length).toBeGreaterThan(0);
  });
});

describe('current node tracking, trail and uncharted state (5.4, 5.5)', () => {
  const rows = Array.from({ length: 24 }, () => ' '.repeat(80));
  const screenEv = (seq: number, screenId: string, callId: string | null): ServerEvent => ({
    v: 1, type: 'screen', seq, ts: 't', session_id: 's', turn_id: null,
    data: { phase: callId ? 'after' : 'snapshot', tool_call_id: callId, screen: { trust: 'untrusted-screen-data', screen_id: screenId, cursor: [0, 0], rows, fields: [] } },
  });
  const sessionEv = (): ServerEvent => ({
    v: 1, type: 'session_state', seq: 1, ts: 't', session_id: 's', turn_id: null,
    data: { state: 'connected', app_id: 'fake-insurance', read_only: false, confirm_mode: 'oob', llm: { provider: 'p', model: 'm', available: true }, tools: { business: 1, generic: 1 }, resync: false, controller: true },
  });
  const play = (evs: ServerEvent[]): AppState => {
    let s = reduce(initialState(), { type: 'map_loaded', map: view });
    for (const event of evs) s = reduce(s, { type: 'server', event, at: 0 });
    return s;
  };

  it('current node follows the screen on display', () => {
    const s = play([sessionEv(), screenEv(2, menu.screen_id, null)]);
    expect(currentNodeId(s)).toBe(menu.id);
    const s2 = reduce(s, { type: 'server', at: 0, event: screenEv(3, enquiry.screen_id, 'c1') });
    expect(currentNodeId(s2)).toBe(enquiry.id);
  });

  it('the trail collects distinct consecutive nodes within one tool call and restarts for the next call', () => {
    let s = play([sessionEv(), screenEv(2, menu.screen_id, 'c1'), screenEv(3, menu.screen_id, 'c1'), screenEv(4, enquiry.screen_id, 'c1')]);
    expect(trailNodeIds(s)).toEqual([menu.id, enquiry.id]);
    s = reduce(s, { type: 'server', at: 0, event: screenEv(5, menu.screen_id, 'c2') });
    expect(trailNodeIds(s)).toEqual([menu.id]);
  });

  it('screens missing from the map are skipped in the trail', () => {
    const s = play([sessionEv(), screenEv(2, menu.screen_id, 'c1'), screenEv(3, 'e'.repeat(64), 'c1'), screenEv(4, enquiry.screen_id, 'c1')]);
    expect(trailNodeIds(s)).toEqual([menu.id, enquiry.id]);
  });

  it('a screen id absent from the map is "uncharted": no current node, but the screen still renders', () => {
    const s = play([sessionEv(), screenEv(2, 'd'.repeat(64), null)]);
    expect(currentNodeId(s)).toBeNull();
    expect(isUncharted(s)).toBe(true);
    expect(s.screen?.screenId).toBe('d'.repeat(64));
  });

  it('with no map loaded the screen is not called uncharted', () => {
    let s = initialState();
    s = reduce(s, { type: 'server', at: 0, event: sessionEv() });
    s = reduce(s, { type: 'server', at: 0, event: screenEv(2, 'd'.repeat(64), null) });
    expect(isUncharted(s)).toBe(false);
  });
});
