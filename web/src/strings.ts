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
