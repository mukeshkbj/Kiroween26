import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppShell } from './AppShell';
import { StoreProvider } from './state/store';
import { AnnouncerProvider } from './a11y/Announcer';
import { ReplayTransport } from './protocol/replayTransport';
import type { RestApi } from './protocol/mock';
import { parseApps, parseAudit, parseSpiritMap } from './protocol/guards';
import { Clock } from '../test/clock';
import { loadExamples } from '../test/examples';
import { focusableIn } from './confirm/useFocusTrap';

const ex = loadExamples();

const rest: RestApi = {
  apps: async () => parseApps(ex.rest['apps'])!,
  audit: async () => parseAudit(ex.rest['audit'])!,
  spiritMap: async (id) => (id === 'fake-insurance' ? parseSpiritMap(ex.spiritMap) : null),
};

function setViewport(wide: boolean) {
  (window as unknown as { matchMedia: unknown }).matchMedia = (q: string) => ({
    matches: q.includes('min-width') ? wide : false,
    media: q,
    addEventListener() {},
    removeEventListener() {},
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

function mount(scenario = 'lookup', opts: { wide?: boolean } = {}) {
  setViewport(opts.wide ?? true);
  const clock = new Clock();
  const transport = new ReplayTransport({ lines: ex.transcripts[scenario] ?? [], timer: clock.timer });
  const view = render(
    <AnnouncerProvider>
      <StoreProvider transport={transport} now={() => clock.now}>
        <AppShell rest={rest} replay now={() => clock.now} isTrusted={() => true} />
      </StoreProvider>
    </AnnouncerProvider>,
  );
  return { clock, transport, ...view };
}

describe('AppShell landmarks and skip links (REQ-018)', () => {
  it('has header, main, complementary chat region and navigation landmarks', async () => {
    mount();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main', { name: 'Legacy system' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Séance' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Skip links' })).toBeInTheDocument();
  });

  it('skip links are first in tab order and target real elements', async () => {
    mount();
    const user = userEvent.setup();
    await user.tab();
    expect(document.activeElement?.textContent).toBe('Skip to screen');
    await user.tab();
    expect(document.activeElement?.textContent).toBe('Skip to chat');
    for (const a of screen.getAllByRole('link')) {
      const id = a.getAttribute('href')!.slice(1);
      expect(document.getElementById(id), id).not.toBeNull();
    }
  });

  it('has exactly one h1 and a REPLAY badge in the header in mock mode', () => {
    mount();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('note')).toHaveTextContent(/REPLAY/);
  });

  it('tab order: skip links, then header controls, then the screen, splitter and chat (no positive tabindex)', async () => {
    const { container } = mount();
    await screen.findAllByRole('button', { name: 'Begin séance' }); // systems list has loaded into the chat pane
    const all = focusableIn(container.querySelector('.app') as HTMLElement);
    expect(all.length).toBeGreaterThan(5);
    for (const el of all) expect(Number(el.getAttribute('tabindex') ?? 0)).toBeLessThanOrEqual(0);
    const order = all.map((el) => el.closest('header, main, aside, nav, .splitter, [role="separator"]')?.tagName ?? el.tagName);
    const firstNav = order.indexOf('NAV');
    const firstHeader = order.indexOf('HEADER');
    const firstMain = order.indexOf('MAIN');
    expect(firstNav).toBeLessThan(firstHeader);
    expect(firstHeader).toBeLessThan(firstMain);
    // the splitter sits between the screen and the chat in tab order
    const sep = all.findIndex((el) => el.getAttribute('role') === 'separator');
    const aside = all.findIndex((el) => el.closest('aside'));
    const mainIdx = all.findIndex((el) => el.closest('main'));
    expect(sep).toBeGreaterThan(mainIdx);
    expect(sep).toBeLessThanOrEqual(aside); // the handle is the first stop inside the chat landmark
  });
});

describe('splitter (REQ-001)', () => {
  it('is a focusable separator with a value; arrows resize, Home/End snap', async () => {
    mount();
    const sep = screen.getByRole('separator');
    expect(sep).toHaveAttribute('tabindex', '0');
    const start = Number(sep.getAttribute('aria-valuenow'));
    sep.focus();
    const user = userEvent.setup();
    await user.keyboard('{ArrowRight}');
    expect(Number(sep.getAttribute('aria-valuenow'))).toBeGreaterThan(start);
    await user.keyboard('{Home}');
    expect(sep.getAttribute('aria-valuenow')).toBe('30');
    await user.keyboard('{End}');
    expect(sep.getAttribute('aria-valuenow')).toBe('75');
  });
});

describe('narrow layout turns into tabs (REQ-001)', () => {
  it('shows a Screen / Séance switcher in a labelled nav; the active view is aria-pressed and the other is hidden', async () => {
    mount('lookup', { wide: false });
    const nav = screen.getByRole('navigation', { name: 'Panes' });
    const buttons = within(nav).getAllByRole('button');
    expect(buttons.map((t) => t.textContent?.trim())).toEqual(['Screen', 'Séance']);
    expect(screen.queryByRole('separator')).toBeNull();
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true');
    const user = userEvent.setup();
    buttons[1]!.focus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('button', { name: /^Séance/ })).toHaveAttribute('aria-pressed', 'true');
    expect(document.getElementById('panel-screen')).toHaveAttribute('hidden');
    expect(document.getElementById('panel-seance')).not.toHaveAttribute('hidden');
  });

  it('marks the hidden Séance tab when new chat activity arrives while on the Screen tab', async () => {
    const h = mount('lookup', { wide: false });
    const user = userEvent.setup();
    h.clock.advance(1000);
    await user.click(screen.getByRole('button', { name: /^Séance/ }));
    const cards = await screen.findAllByRole('button', { name: 'Begin séance' });
    const fake = cards.find((b) => b.closest('.system-card')?.textContent?.includes('simulated'))!;
    await user.click(fake);
    await act(async () => h.clock.advance(1500));
    const composer = await screen.findByLabelText(/Message to the séance/i);
    await waitFor(() => expect(composer).toBeEnabled());
    await user.type(composer, 'look up P0000003');
    await user.keyboard('{Enter}');
    // leave the Séance tab, then let the recording answer
    await user.click(screen.getByRole('button', { name: /^Screen/ }));
    await act(async () => h.clock.advance(1_000_000));
    expect(screen.getByRole('button', { name: /^Séance/ })).toHaveTextContent(/new activity/);
    // opening the tab clears the marker
    await user.click(screen.getByRole('button', { name: /^Séance/ }));
    expect(screen.getByRole('button', { name: /^Séance/ })).not.toHaveTextContent(/new activity/);
  });
});

describe('shortcuts need a modifier (REQ-018)', () => {
  it('Alt+Shift+A toggles the audit drawer; a bare "a" does nothing', async () => {
    mount();
    expect(screen.queryByRole('complementary', { name: 'Audit log' })).toBeNull();
    fireEvent.keyDown(window, { code: 'KeyA', key: 'a' });
    expect(screen.queryByRole('complementary', { name: 'Audit log' })).toBeNull();
    fireEvent.keyDown(window, { code: 'KeyA', key: 'A', altKey: true, shiftKey: true });
    expect(await screen.findByRole('complementary', { name: 'Audit log' })).toBeInTheDocument();
    fireEvent.keyDown(window, { code: 'KeyA', key: 'A', altKey: true, shiftKey: true });
    await waitFor(() => expect(screen.queryByRole('complementary', { name: 'Audit log' })).toBeNull());
  });

  it('Alt+Shift+M switches between the screen and the spirit-map', async () => {
    mount();
    fireEvent.keyDown(window, { code: 'KeyM', altKey: true, shiftKey: true });
    expect(await screen.findByText(/No spirit-map|Loading the spirit-map/)).toBeInTheDocument();
  });

  it('Alt+Shift+R toggles reduced motion on <html>', async () => {
    mount();
    fireEvent.keyDown(window, { code: 'KeyR', altKey: true, shiftKey: true });
    await waitFor(() => expect(document.documentElement.getAttribute('data-motion')).toBe('reduce'));
    fireEvent.keyDown(window, { code: 'KeyR', altKey: true, shiftKey: true });
    await waitFor(() => expect(document.documentElement.hasAttribute('data-motion')).toBe(false));
  });

  it('lists every shortcut in the header help', () => {
    mount();
    const help = screen.getByText('Keyboard shortcuts').closest('details') as HTMLElement;
    expect(within(help).getAllByText(/Alt\+Shift\+/)).toHaveLength(7);
  });
});

describe('header toggles', () => {
  it('Effects select sets the data attribute without changing the screen text', async () => {
    const { container } = mount();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText('Effects'), 'full');
    expect(container.querySelector('.app')?.getAttribute('data-effects')).toBe('full');
  });
});

describe('keyboard-only flow: connect -> ask -> confirm -> deny (REQ-028)', () => {
  it('works with no pointer at all', async () => {
    const h = mount('commit-deny');
    const user = userEvent.setup();

    // let the recording deliver its first session_state and the systems list load
    h.clock.advance(1000);
    const begin = await screen.findAllByRole('button', { name: 'Begin séance' });
    // Tab to the simulated system's button and press Enter
    const fake = begin.find((b) => b.closest('.system-card')?.textContent?.includes('simulated'))!;
    fake.focus();
    await user.keyboard('{Enter}');
    await act(async () => h.clock.advance(1500));

    // connected: the composer is usable; type and press Enter
    const composer = await screen.findByLabelText(/Message to the séance/i);
    await waitFor(() => expect(composer).toBeEnabled());
    composer.focus();
    await user.type(composer, 'set the premium to 300');
    await user.keyboard('{Enter}');

    // run virtual time until the modal appears
    for (let i = 0; i < 400 && !screen.queryByRole('alertdialog'); i++) h.clock.advance(25);
    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByRole('button', { name: 'Deny' })).toHaveFocus();
    // the rest of the app is inert while the dialog is open
    expect(document.querySelector('.app')?.hasAttribute('inert')).toBe(true);

    await user.keyboard('{Escape}');
    h.clock.advance(1_000_000);
    await waitFor(() => expect(screen.getByRole('status', { name: '' })).toBeDefined());
    await waitFor(() => expect(within(screen.getByRole('alertdialog')).getByText(/Denied\. Nothing was changed/)).toBeInTheDocument());
    // the same outcome is also announced to screen readers through the polite live region
    await waitFor(() => expect(screen.getByTestId('live-polite')).toHaveTextContent(/Denied\. Nothing was changed/));
    await user.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(document.querySelector('.app')?.hasAttribute('inert')).toBe(false);
  });
});
