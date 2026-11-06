import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { useStore } from './state/store';
import { TerminalPane } from './terminal/TerminalPane';
import { Chat } from './chat/Chat';
import { ConnectScreen, type AppsLoad } from './connect/ConnectScreen';
import { StateBanner } from './connect/StateBanner';
import { ConfirmHost } from './confirm/ConfirmHost';
import { AuditDrawer } from './audit/AuditDrawer';
import { MapView } from './map/MapView';
import { SkipLinks } from './a11y/SkipLinks';
import { useAnnouncer } from './a11y/Announcer';
import { useReducedMotion } from './a11y/useReducedMotion';
import { useMedia } from './a11y/useMedia';
import { SPLIT_DEFAULT, WIDE_BREAKPOINT_PX, resizeSplit, splitFromPointer } from './layout/splitter';
import { SHORTCUTS, matchShortcut, nextEffects } from './layout/shortcuts';
import { currentNodeId, isBusy, isUncharted, trailNodeIds } from './state/selectors';
import type { RestApi } from './protocol/mock';
import type { FieldFocus } from './protocol/types';
import { strings } from './strings';

/**
 * The page: landmarks, skip links, the splitter (wide) or tabs (narrow), header toggles, the audit drawer and
 * the confirmation modal. It owns no domain state; everything comes from the store. REST data is loaded here
 * and put into the store.
 */

export interface AppShellProps {
  rest: RestApi;
  replay: boolean;
  /** Replay only: what the script is waiting for, evaluated each render and shown as a hint. */
  getReplayHint?: () => string | null;
  now?: () => number;
  /** Test seam for the modal's trusted-event check. */
  isTrusted?: (e: Event) => boolean;
  /** Replay only: scenario picker. */
  scenarios?: { current: string; all: string[]; onChange: (s: string) => void };
}

type Tab = 'screen' | 'seance';

function focusLabel(f: FieldFocus): string {
  const name = f.label?.trim().replace(/[=>\s]+$/, '');
  if (f.mode === 'read') return name ? strings.planchette.readingField(name) : strings.planchette.reading;
  if (f.mode === 'fill') return name ? strings.planchette.fillingField(name) : strings.planchette.filling;
  return strings.planchette.pressing(f.key ?? '');
}

export function AppShell({ rest, replay, getReplayHint, now, isTrusted, scenarios }: AppShellProps) {
  const { state, connectSystem, sendMessage, cancelTurn, dispatch } = useStore();
  const { announce } = useAnnouncer();
  const reduceMotion = useReducedMotion(state.ui.reduceMotion);
  const wide = useMedia(`(min-width: ${WIDE_BREAKPOINT_PX}px)`, true);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const auditToggleRef = useRef<HTMLButtonElement | null>(null);
  const [rootEl, setRootEl] = useState<HTMLElement | null>(null);
  useEffect(() => setRootEl(rootRef.current), []);

  const [split, setSplit] = useState(SPLIT_DEFAULT);
  const [tab, setTab] = useState<Tab>('screen');
  const [activity, setActivity] = useState<Tab | null>(null);
  const [apps, setApps] = useState<AppsLoad>({ status: 'loading' });
  const [mapLoading, setMapLoading] = useState(false);
  const dragging = useRef(false);
  const splitHostRef = useRef<HTMLDivElement | null>(null);

  // ---- REST: systems ----
  const loadApps = useCallback(() => {
    setApps({ status: 'loading' });
    rest.apps().then(
      (list) => setApps({ status: 'ready', apps: list }),
      () => setApps({ status: 'error' }),
    );
  }, [rest]);
  useEffect(loadApps, [loadApps]);

  // ---- REST: spirit-map for the connected app ----
  const appId = state.session.appId;
  const connected = state.session.state === 'connected';
  useEffect(() => {
    if (!appId || !connected) return;
    let live = true;
    setMapLoading(true);
    rest.spiritMap(appId).then(
      (m) => live && (dispatch({ type: 'map_loaded', map: m }), setMapLoading(false)),
      () => live && (dispatch({ type: 'map_loaded', map: null }), setMapLoading(false)),
    );
    return () => {
      live = false;
    };
  }, [appId, connected, rest, dispatch]);

  // ---- REST: audit when the drawer opens ----
  const refreshAudit = useCallback(() => {
    rest.audit(500).then(
      (response) => dispatch({ type: 'audit_loaded', response }),
      () => {},
    );
  }, [rest, dispatch]);
  useEffect(() => {
    if (state.ui.drawerOpen) refreshAudit();
  }, [state.ui.drawerOpen, refreshAudit]);

  // ---- announcements: session state and each planchette step ----
  const lastSession = useRef(state.session.state);
  useEffect(() => {
    if (lastSession.current === state.session.state) return;
    lastSession.current = state.session.state;
    if (state.session.state === 'connected') announce(strings.shell.announce.connected);
    else if (state.session.state === 'connecting') announce(strings.shell.announce.connecting);
    else if (state.session.state === 'session_lost') announce(strings.shell.announce.lost, 'assertive');
  }, [state.session.state, announce]);

  const lastFocus = useRef(0);
  useEffect(() => {
    for (const f of state.focusQueue) {
      if (f.seq > lastFocus.current) {
        lastFocus.current = f.seq;
        announce(focusLabel(f));
      }
    }
  }, [state.focusQueue, announce]);

  // ---- activity indicator on the hidden tab (narrow layout) ----
  const msgCount = state.messages.length;
  const screenId = state.screen?.screenId ?? null;
  const prevMsgs = useRef(msgCount);
  const prevScreen = useRef(screenId);
  useEffect(() => {
    if (!wide) {
      if (msgCount !== prevMsgs.current && tab !== 'seance') setActivity('seance');
      if (screenId !== prevScreen.current && tab !== 'screen') setActivity('screen');
    }
    prevMsgs.current = msgCount;
    prevScreen.current = screenId;
  }, [msgCount, screenId, wide, tab]);
  const selectTab = (t: Tab) => {
    setTab(t);
    setActivity((a) => (a === t ? null : a));
  };

  // ---- shortcuts ----
  const focusId = (id: string) => document.getElementById(id)?.focus();
  const onKeyDown = useCallback(
    (e: globalThis.KeyboardEvent) => {
      const id = matchShortcut(e);
      if (!id) return;
      e.preventDefault();
      switch (id) {
        case 'audit':
          dispatch({ type: 'ui', patch: { drawerOpen: !state.ui.drawerOpen } });
          break;
        case 'map':
          dispatch({ type: 'ui', patch: { pane: state.ui.pane === 'map' ? 'terminal' : 'map' } });
          break;
        case 'chat':
          if (!wide) selectTab('seance');
          setTimeout(() => focusId('composer-input') ?? focusId('chat-region'), 0);
          break;
        case 'screen':
          if (!wide) selectTab('screen');
          setTimeout(() => focusId('screen-region'), 0);
          break;
        case 'effects':
          dispatch({ type: 'ui', patch: { effects: nextEffects(state.ui.effects) } });
          break;
        case 'motion':
          dispatch({ type: 'ui', patch: { reduceMotion: !state.ui.reduceMotion } });
          break;
        case 'text':
          dispatch({ type: 'ui', patch: { screenAsText: !state.ui.screenAsText } });
          break;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state.ui, wide, dispatch],
  );
  useEffect(() => {
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onKeyDown]);

  // ---- splitter ----
  const onSplitKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const next = resizeSplit(split, e.key, e.shiftKey);
    if (next !== null) {
      e.preventDefault();
      setSplit(next);
    }
  };
  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    (e.currentTarget as HTMLDivElement).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging.current || !splitHostRef.current) return;
    const r = splitHostRef.current.getBoundingClientRect();
    setSplit(splitFromPointer(e.clientX, r.left, r.width));
  };
  const onPointerUp = () => {
    dragging.current = false;
  };

  const node = currentNodeId(state);
  const screenName = state.map?.nodes.find((n) => n.id === node)?.name ?? null;
  const busy = isBusy(state);
  const replayHint = replay && getReplayHint ? getReplayHint() : null;
  const showConnect = state.session.state !== 'connected' && state.session.state !== 'connecting';

  const screenPanel = (
    <main id="screen-region" className="pane pane-screen" aria-label={strings.shell.mainLabel} tabIndex={-1}>
      <div className="pane-switch" role="group" aria-label={strings.shell.panesSwitch}>
        <button type="button" aria-pressed={state.ui.pane === 'terminal'} onClick={() => dispatch({ type: 'ui', patch: { pane: 'terminal' } })}>
          {strings.shell.paneScreen}
        </button>
        <button type="button" aria-pressed={state.ui.pane === 'map'} onClick={() => dispatch({ type: 'ui', patch: { pane: 'map' } })}>
          {strings.shell.paneMap}
        </button>
      </div>
      {state.ui.pane === 'terminal' ? (
        <TerminalPane
          screen={state.screen}
          screenName={screenName}
          sessionState={state.session.state}
          readOnly={state.session.readOnly}
          busy={busy}
          replay={replay}
          uncharted={isUncharted(state)}
          focusQueue={state.focusQueue}
          reduceMotion={reduceMotion}
          effects={state.ui.effects}
          showAsText={state.ui.screenAsText}
          onFocusConsumed={(seq) => dispatch({ type: 'focus_done', seq })}
          lastFill={state.lastFill}
        />
      ) : (
        <MapView view={state.map} loading={mapLoading} currentNodeId={node} uncharted={isUncharted(state)} trail={trailNodeIds(state)} />
      )}
    </main>
  );

  const chatPanel = (
    <aside id="chat-region" className="pane pane-chat" aria-label={strings.shell.chatLabel} tabIndex={-1}>
      {wide && (
        // The resize handle sits on the chat pane's left edge, inside its landmark, so it is never loose page content.
        <div
          className="splitter"
          role="separator"
          aria-orientation="vertical"
          aria-label={strings.shell.splitter}
          aria-valuemin={30}
          aria-valuemax={75}
          aria-valuenow={split}
          tabIndex={0}
          onKeyDown={onSplitKey}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        />
      )}
      {showConnect && (
        <ConnectScreen load={apps} onConnect={(id) => connectSystem(id)} onRetry={loadApps} connecting={state.session.state === 'connecting'} />
      )}
      <Chat state={state} onSend={sendMessage} onCancel={cancelTurn} />
    </aside>
  );

  return (
    <>
      <div ref={rootRef} className="app" data-effects={state.ui.effects} data-wide={wide ? 'true' : 'false'}>
        <SkipLinks />
        <header className="app-header">
          <h1>{strings.shell.header}</h1>
          <span className="header-state">{strings.sessionState[state.session.state]}</span>
          {replay && (
            <span className="header-replay" role="note">
              {strings.shell.replayHeader}
            </span>
          )}
          <div className="header-controls">
            <label>
              {strings.effects.label}{' '}
              <select value={state.ui.effects} onChange={(e) => dispatch({ type: 'ui', patch: { effects: e.target.value as 'full' | 'low' | 'off' } })}>
                {(['full', 'low', 'off'] as const).map((l) => (
                  <option key={l} value={l}>
                    {strings.effects[l]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <input type="checkbox" checked={state.ui.reduceMotion} onChange={(e) => dispatch({ type: 'ui', patch: { reduceMotion: e.target.checked } })} />{' '}
              {strings.shell.reduceMotion}
            </label>
            <label>
              <input type="checkbox" checked={state.ui.screenAsText} onChange={(e) => dispatch({ type: 'ui', patch: { screenAsText: e.target.checked } })} />{' '}
              {strings.shell.screenAsText}
            </label>
            <button
              ref={auditToggleRef}
              type="button"
              aria-expanded={state.ui.drawerOpen}
              aria-controls="audit-drawer"
              onClick={() => dispatch({ type: 'ui', patch: { drawerOpen: !state.ui.drawerOpen } })}
            >
              {strings.shell.auditToggle}
            </button>
            <details className="shortcuts">
              <summary>{strings.shell.shortcuts}</summary>
              <dl>
                {SHORTCUTS.map((s) => (
                  <div key={s.id}>
                    <dt>
                      <kbd>{s.label}</kbd>
                    </dt>
                    <dd>{s.description}</dd>
                  </div>
                ))}
              </dl>
            </details>
            {scenarios && (
              <label>
                {strings.shell.scenario}{' '}
                <select value={scenarios.current} onChange={(e) => scenarios.onChange(e.target.value)}>
                  {scenarios.all.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        </header>

        <StateBanner state={state} onReconnect={() => window.location.reload()} />
        {replayHint && (
          <p className="replay-hint" role="status">
            {strings.shell.replayHint(replayHint)}
          </p>
        )}

        {wide ? (
          <div className="split" ref={splitHostRef} style={{ gridTemplateColumns: `${split}fr ${100 - split}fr` }}>
            {screenPanel}

            {chatPanel}
          </div>
        ) : (
          <div className="tabs-layout">
            {/* A two-way view switcher rather than ARIA tabs: tab panels wrapped around landmarks trip the
                "content outside landmarks" rule, and the main/aside landmarks must stay top level. */}
            <nav aria-label={strings.shell.panesNav}>
              <div className="tabs">
                {(['screen', 'seance'] as const).map((t) => (
                  <button key={t} type="button" id={`tab-${t}`} aria-pressed={tab === t} aria-controls={`panel-${t}`} onClick={() => selectTab(t)}>
                    {t === 'screen' ? strings.shell.tabScreen : strings.shell.tabSeance}
                    {activity === t && tab !== t && <span className="tab-activity"> ({strings.shell.newActivity})</span>}
                  </button>
                ))}
              </div>
            </nav>
            <div id="panel-screen" hidden={tab !== 'screen'}>
              {screenPanel}
            </div>
            <div id="panel-seance" hidden={tab !== 'seance'}>
              {chatPanel}
            </div>
          </div>
        )}

        <div id="audit-drawer">
          <AuditDrawer
            open={state.ui.drawerOpen}
            entries={state.audit}
            chain={state.auditChain}
            onClose={() => dispatch({ type: 'ui', patch: { drawerOpen: false } })}
            onRefresh={refreshAudit}
            toggleRef={auditToggleRef}
          />
        </div>
      </div>
      <ConfirmHost now={now} inertRoot={rootEl} isTrusted={isTrusted} />
    </>
  );
}
