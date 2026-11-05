import type { SessionStateName } from './protocol/types';

/** All user-visible text lives here so it can be localised later (requirements: Non-goals). */
export const strings = {
  appName: 'Green Screen Séance',
  replayBadge: 'REPLAY',
  dormant: 'The screen is dormant. Choose a system to begin.',

  screenRegion: '3270 screen',
  uncharted: 'uncharted',
  readOnly: 'read only',

  oiaLabel: 'Terminal status',
  oiaReady: 'ready',
  oiaBusy: 'keyboard locked',
  oiaScreen: 'screen',

  sessionState: {
    disconnected: 'disconnected',
    connecting: 'connecting',
    connected: 'connected',
    session_lost: 'session lost',
    error: 'error',
  } satisfies Record<SessionStateName, string>,

  effects: {
    label: 'Effects',
    full: 'Full',
    low: 'Low',
    off: 'Off',
  },

  connect: {
    heading: 'Choose a system',
    intro: 'Pick a legacy system to hold a séance with.',
    simulated: 'simulated',
    live: 'live',
    reachable: 'reachable',
    unreachable: 'not reachable',
    reachUnknown: 'reachability unknown',
    toolsLabel: (business: number, approved: number) => `${approved} of ${business} tools approved`,
    hasMap: 'spirit-map',
    noMap: 'no map yet',
    connectBtn: 'Begin séance',
    loading: 'Summoning the list of systems…',
    none: 'No systems are configured.',
    loadError: 'Could not reach the agent to list systems.',
    retry: 'Try again',
  },

  states: {
    sessionLost: 'The séance lost its connection to the system.',
    reconnect: 'Reconnect',
    reconnecting: 'Reconnecting to the agent…',
    unreachable: 'The agent is unreachable.',
    llmUnavailable: 'The language model is unavailable, so the séance cannot answer right now.',
    expired: 'The confirmation expired before anyone decided. Nothing was changed.',
    readOnlyServer: 'This session is read only. Changes are blocked.',
    observerOnly: 'You are observing. Controls are disabled; only the controller can act.',
    toolError: (code: string, message: string) => `Tool error (${code}): ${message}`,
    unchartedTitle: 'Uncharted screen',
    uncharted: 'This screen is not in the spirit-map. It still renders, but there is no map node for it.',
    resync: 'Reconnected. Some activity was missed, so the log may be incomplete.',
  },

  step: {
    thinking: 'Thinking',
    business: 'business',
    generic: 'generic',
    mayCommit: 'may change data',
    running: 'Working…',
    statusLabel: 'Result',
    truncated: 'Result was truncated.',
    untrustedTag: 'legacy screen',
    untrustedTitle: 'Text read from the legacy screen. Untrusted data, not the agent’s words.',
  },

  chat: {
    region: 'Séance chat',
    log: 'Conversation',
    you: 'You',
    seance: 'Séance',
    system: 'System',
    streaming: 'The spirits are speaking…',
    placeholder: 'Ask the séance…',
    send: 'Send',
    cancel: 'Cancel',
    composerLabel: 'Message to the séance',
    blocked: {
      observer: 'You are observing this session. Only the controller can send messages.',
      disconnected: 'Not connected to the agent.',
      no_system: 'Choose a system before asking.',
      llm_unavailable: 'The language model is unavailable right now.',
      confirmation_open: 'Resolve the pending confirmation first.',
    },
    sendFailed: 'That message could not be sent. It was not retried; try again.',
  },

  planchette: {
    reading: 'reading the screen',
    filling: 'filling a field',
    readingField: (name: string) => `reading ${name}`,
    fillingField: (name: string) => `filling ${name}`,
    pressing: (key: string) => `pressing ${key}`,
  },

  sat: {
    region: 'Screen as text',
    title: 'Title',
    inputs: 'Input fields:',
    cursor: 'Cursor',
    hidden: 'hidden',
    empty: '(empty)',
    rowCol: (row: number, col: number) => `row ${row}, column ${col}`,
  },
} as const;
