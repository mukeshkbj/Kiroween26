import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createRef } from 'react';
import { AppShell } from '../AppShell';
import { StoreProvider } from '../state/store';
import { AnnouncerProvider } from './Announcer';
import { ReplayTransport } from '../protocol/replayTransport';
import type { RestApi } from '../protocol/mock';
import { parseApps, parseAudit, parseSpiritMap } from '../protocol/guards';
import { ConnectScreen } from '../connect/ConnectScreen';
import { ConfirmModal } from '../confirm/ConfirmModal';
import { AuditDrawer } from '../audit/AuditDrawer';
import { MapView } from '../map/MapView';
import { Composer } from '../chat/Composer';
import { TerminalPane } from '../terminal/TerminalPane';
import { scrubScreen, type Confirmation, type ScreenState } from '../state/reducer';
import { parseServerEvent } from '../protocol/guards';
import { Clock } from '../../test/clock';
import { loadExamples } from '../../test/examples';
import { expectNoViolations, runAxe } from '../../test/axe';
import type { AppInfo, AuditEntry, SpiritMapView } from '../protocol/types';

/** REQ-028: axe over every view and state, including the modal, empty and error states. */

const ex = loadExamples();
const apps = parseApps(ex.rest['apps']) as AppInfo[];
const audit = parseAudit(ex.rest['audit'])!;
const map = parseSpiritMap(ex.spiritMap) as SpiritMapView;

const rest: RestApi = {
  apps: async () => apps,
  audit: async () => audit,
  spiritMap: async (id) => (id === 'fake-insurance' ? map : null),
};

function setViewport(wide: boolean) {
  (window as unknown as { matchMedia: unknown }).matchMedia = (q: string) => ({
    matches: q.includes('min-width') ? wide : false, media: q, addEventListener() {}, removeEventListener() {},
  });
}

beforeEach(() => {
  (Element.prototype as unknown as { animate: unknown }).animate = () => ({
    addEventListener() {}, removeEventListener() {}, cancel() {}, finish() {},
  });
});
afterEach(() => {
  delete (window as unknown as { matchMedia?: unknown }).matchMedia;
});

function mountShell(scenario: string, wide = true) {
  setViewport(wide);
  const clock = new Clock();
  const transport = new ReplayTransport({ lines: ex.transcripts[scenario] ?? [], timer: clock.timer });
  render(
    <AnnouncerProvider>
      <StoreProvider transport={transport} now={() => clock.now}>
        <AppShell rest={rest} replay now={() => clock.now} isTrusted={() => true} />
      </StoreProvider>
    </AnnouncerProvider>,
  );
  return { clock, transport };
}

/** Perform the scripted user actions until `done()` is true or the script ends, in small virtual steps. */
function drive(h: ReturnType<typeof mountShell>, done: () => boolean, steps = 6000) {
  for (let i = 0; i < steps && !done(); i++) {
    h.clock.advance(25);
    const want = h.transport.expecting();
    if (want && want.type !== 'confirm_decision') {
      act(() => {
        h.transport.send(want);
      });
    }
  }
}

describe('axe: the whole page in each state', () => {
  it('dormant: before connecting, systems listed (wide)', async () => {
    mountShell('lookup');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    await expectNoViolations();
  });

  it('dormant: narrow layout with tabs (each tab selected in turn)', async () => {
    mountShell('lookup', false);
    await screen.findByRole('navigation', { name: 'Panes' });
    await expectNoViolations();
    await userEvent.setup().click(within(screen.getByRole('navigation', { name: 'Panes' })).getByRole('button', { name: /^Séance/ }));
    await screen.findAllByRole('button', { name: 'Begin séance' });
    await expectNoViolations();
  });

  it('connected, screen populated, planchette and step cards shown (lookup finished)', async () => {
    const h = mountShell('lookup');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    drive(h, () => h.transport.finished);
    await waitFor(() => expect(screen.getAllByText(/A\. ROSE/).length).toBeGreaterThan(1)); // grid and step card
    await expectNoViolations();
  });

  it('screen-as-text on', async () => {
    const h = mountShell('lookup');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    drive(h, () => h.transport.finished);
    await userEvent.setup().click(screen.getByLabelText('Screen as text'));
    expect(screen.getByLabelText('Screen as text', { selector: '.term-as-text' })).toBeInTheDocument();
    await expectNoViolations();
  });

  it('confirmation modal open (approve transcript)', async () => {
    const h = mountShell('commit-approve');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    drive(h, () => !!screen.queryByRole('alertdialog'));
    await screen.findByRole('alertdialog');
    await expectNoViolations();
  });

  it('modal after the outcome (denied) and the dismiss state', async () => {
    const h = mountShell('commit-deny');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    drive(h, () => !!screen.queryByRole('alertdialog'));
    await screen.findByRole('alertdialog');
    await userEvent.setup().keyboard('{Escape}');
    h.clock.advance(1_000_000);
    await screen.findByText(/Denied\. Nothing was changed/);
    await expectNoViolations();
  });

  it('read-only session banner and modal without Approve', async () => {
    const h = mountShell('read-only');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    drive(h, () => !!screen.queryByRole('alertdialog'));
    await screen.findByRole('alertdialog');
    expect(screen.queryByRole('button', { name: /^Approve/ })).toBeNull();
    await expectNoViolations();
  });

  it('session lost banner with a reconnect action', async () => {
    const h = mountShell('session-lost');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    drive(h, () => !!screen.queryByText(/lost its connection/), 8000);
    await expectNoViolations();
  });

  it('audit drawer open with REST entries', async () => {
    mountShell('lookup');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Audit log' }));
    await screen.findByRole('complementary', { name: 'Audit log' });
    await waitFor(() => expect(document.querySelectorAll('.audit-table tbody tr').length).toBeGreaterThan(0));
    await expectNoViolations();
  });

  it('spirit-map pane: graph + table', async () => {
    const h = mountShell('lookup');
    await screen.findAllByRole('button', { name: 'Begin séance' });
    drive(h, () => h.transport.finished);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Spirit-map' }));
    await screen.findByRole('table', { name: /Spirit-map as a table/ });
    await expectNoViolations();
  });
});

describe('axe: components in their empty, error and edge states', () => {
  const none = () => {};

  it.each([
    ['loading', { status: 'loading' as const }],
    ['error', { status: 'error' as const }],
    ['empty', { status: 'ready' as const, apps: [] }],
    ['ready', { status: 'ready' as const, apps }],
  ])('connect screen: %s', async (_n, load) => {
    render(<ConnectScreen load={load} onConnect={none} onRetry={none} />);
    await expectNoViolations(document.body, { fragment: true });
  });

  it.each([
    ['observer', 'observer'],
    ['disconnected', 'disconnected'],
    ['no system', 'no_system'],
    ['llm unavailable', 'llm_unavailable'],
    ['confirmation open', 'confirmation_open'],
    ['usable', null],
  ] as const)('composer: %s', async (_n, block) => {
    render(<Composer block={block} canCancel={block === null} onSend={none} onCancel={none} />);
    await expectNoViolations(document.body, { fragment: true });
  });

  it('audit drawer: empty', async () => {
    render(<AuditDrawer open entries={[]} chain={{ status: 'unknown', brokenSeq: null }} onClose={none} />);
    await expectNoViolations(document.body, { fragment: true });
  });

  it('audit drawer: broken chain', async () => {
    const e: AuditEntry[] = audit.entries.slice(0, 3);
    render(<AuditDrawer open entries={e} chain={{ status: 'broken', brokenSeq: 2 }} onClose={none} />);
    await expectNoViolations(document.body, { fragment: true });
  });

  it('audit drawer: toggle ref wiring does not break the tree', async () => {
    const ref = createRef<HTMLElement>();
    render(<AuditDrawer open entries={audit.entries} chain={{ status: 'ok', brokenSeq: null }} onClose={none} toggleRef={ref} />);
    await expectNoViolations(document.body, { fragment: true });
  });

  it('map view: no map, loading, uncharted, and with a map', async () => {
    const base = { currentNodeId: null, uncharted: false, trail: [] as string[] };
    const a = render(<MapView view={null} {...base} />);
    await expectNoViolations(a.container, { fragment: true });
    a.unmount();
    const b = render(<MapView view={null} loading {...base} />);
    await expectNoViolations(b.container, { fragment: true });
    b.unmount();
    const c = render(<MapView view={map} {...base} uncharted />);
    await expectNoViolations(c.container, { fragment: true });
    c.unmount();
    const d = render(<MapView view={map} {...base} currentNodeId={map.nodes[0]!.id} trail={[map.nodes[0]!.id]} />);
    await expectNoViolations(d.container, { fragment: true });
  });

  it('terminal pane: dormant, populated, hidden field present', async () => {
    const r = parseServerEvent(ex.events['screen']);
    if (!r.ok || r.event.type !== 'screen') throw new Error('no screen');
    const populated: ScreenState = scrubScreen(r.event.data.screen);
    const withHidden: ScreenState = scrubScreen({
      ...r.event.data.screen,
      fields: [
        ...r.event.data.screen.fields,
        { index: 99, row: 10, col: 10, length: 8, protected: false, numeric: false, hidden: true, intensified: false, label: 'PIN', value: 'SECRET' },
      ],
    });
    const base = { screenName: 'Main menu', sessionState: 'connected' as const, readOnly: false, busy: false, replay: false, uncharted: false, focusQueue: [], reduceMotion: false, effects: 'low' as const, showAsText: true };
    for (const screenState of [null, populated, withHidden]) {
      const v = render(<TerminalPane {...base} screen={screenState} />);
      await expectNoViolations(v.container, { fragment: true });
      v.unmount();
    }
  });

  it('modal variants: expired, sending, resolved, no screen, agent text with markup', async () => {
    const SID = 'c'.repeat(64);
    const scr: ScreenState = { screenId: SID, cursor: [0, 0], rows: Array.from({ length: 24 }, () => ' '.repeat(80)), fields: [] };
    const conf = (over: Partial<Confirmation>): Confirmation => ({
      actionId: 'a', toolCallId: 'c', turnId: 't', screenId: SID, key: 'Enter', fieldSnapshot: [{ index: 1, row: 2, col: 3, label: 'PREMIUM', value: '300.00' }],
      expiresInS: 300, receivedAt: 0, readOnly: false, agentSummary: '<b>x</b>', phase: 'open', outcome: null, errorCode: null, confirmedBy: null, ...over,
    });
    const variants: [Partial<Confirmation>, ScreenState | null][] = [
      [{ phase: 'expired' }, scr],
      [{ phase: 'sending' }, scr],
      [{ phase: 'resolved', outcome: 'blocked_read_only' }, scr],
      [{ phase: 'open' }, null],
      [{ phase: 'open', readOnly: true }, scr],
    ];
    for (const [over, s] of variants) {
      const v = render(
        <ConfirmModal confirmation={conf(over)} screen={s} sessionReadOnly={false} observerOnly={false} now={() => 0} onDecide={() => {}} onTimeout={() => {}} onDismiss={() => {}} />,
      );
      await expectNoViolations(document.body, { fragment: true });
      v.unmount();
    }
  });
});

describe('axe sanity inside this suite', () => {
  it('actually detects a violation (so the passes above mean something)', async () => {
    const { container } = render(<button />);
    const r = await runAxe(container);
    expect(r.violations.map((v) => v.id)).toContain('button-name');
  });
});
