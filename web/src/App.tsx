import { useEffect, useMemo, useState } from 'react';
import { AppShell } from './AppShell';
import { StoreProvider } from './state/store';
import { AnnouncerProvider } from './a11y/Announcer';
import { config } from './config';
import { ReplayTransport } from './protocol/replayTransport';
import { WebSocketTransport } from './protocol/wsTransport';
import { RestClient } from './protocol/rest';
import { SCENARIOS, loadScenario, mockRest } from './protocol/mock';
import type { ClientMessage } from './protocol/types';
import type { Transport } from './protocol/transport';
import { strings } from './strings';

/**
 * Chooses the transport (REQ-023): VITE_MODE=mock plays a recorded transcript through the same Transport interface
 * as the websocket; live talks to the agent. Mock mode always shows the REPLAY badge (header and OIA).
 */

const describeExpected = (m: ClientMessage | null): string | null => {
  if (!m) return null;
  switch (m.type) {
    case 'connect_system':
      return `choose "${m.app_id}"`;
    case 'user_message':
      return `send a message (the recording answers "${m.text}")`;
    case 'confirm_decision':
      return m.decision === 'deny' ? 'press Deny' : 'press Approve';
    default:
      return m.type;
  }
};

function scenarioFromUrl(): string {
  if (typeof window === 'undefined') return 'lookup';
  const s = new URLSearchParams(window.location.search).get('scenario');
  return s && SCENARIOS.includes(s) ? s : 'lookup';
}

function MockApp() {
  const [scenario, setScenario] = useState(scenarioFromUrl);
  const [transport, setTransport] = useState<ReplayTransport | null>(null);

  useEffect(() => {
    let live = true;
    setTransport(null);
    loadScenario(scenario).then((lines) => {
      if (live) setTransport(new ReplayTransport({ lines, speed: config.replaySpeed }));
    });
    return () => {
      live = false;
    };
  }, [scenario]);

  if (!transport) return <p>{strings.dormant}</p>;
  return (
    <AnnouncerProvider>
      <StoreProvider key={scenario} transport={transport}>
        <AppShell
          rest={mockRest}
          replay
          getReplayHint={() => describeExpected(transport.expecting())}
          scenarios={{ current: scenario, all: SCENARIOS, onChange: setScenario }}
        />
      </StoreProvider>
    </AnnouncerProvider>
  );
}

function LiveApp() {
  const rest = useMemo(() => new RestClient(config.agentUrl), []);
  const transport = useMemo<Transport>(() => {
    let lastSeq = 0;
    let sessionId: string | null = null;
    const t = new WebSocketTransport({
      agentUrl: config.agentUrl,
      getResume: () => ({ sessionId, lastSeq }),
    });
    t.subscribe({
      onEvent: (e) => {
        sessionId = e.session_id;
        lastSeq = Math.max(lastSeq, e.seq);
      },
      onUnknown: () => {},
      onInvalid: () => {},
      onStatus: () => {},
    });
    return t;
  }, []);
  return (
    <AnnouncerProvider>
      <StoreProvider transport={transport}>
        <AppShell rest={rest} replay={false} />
      </StoreProvider>
    </AnnouncerProvider>
  );
}

export function App() {
  return config.mode === 'mock' ? <MockApp /> : <LiveApp />;
}
