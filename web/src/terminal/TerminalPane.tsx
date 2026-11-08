import { Grid } from './Grid';
import { Oia } from './Oia';
import { ScreenAsText } from './ScreenAsText';
import { Planchette } from '../planchette/Planchette';
import { useRevealedRows, type FillHint } from './useRevealedRows';
import { strings } from '../strings';
import type { FieldFocus, SessionStateName } from '../protocol/types';
import type { ScreenState } from '../state/reducer';

/**
 * Composes the terminal: the CRT screen (grid + effects overlay + planchette), the OIA status line, and the
 * linear screen-as-text alternative. The effects overlay and planchette are separate layers over the grid, so
 * turning effects off or reducing motion never changes the text or layout.
 */

export interface TerminalPaneProps {
  screen: ScreenState | null;
  screenName: string | null;
  sessionState: SessionStateName;
  readOnly: boolean;
  busy: boolean;
  replay: boolean;
  uncharted: boolean;
  focusQueue: (FieldFocus & { seq: number })[];
  reduceMotion: boolean;
  effects: 'full' | 'low' | 'off';
  showAsText: boolean;
  onFocusConsumed?: (seq: number) => void;
  /** The latest fill position (no value) for the typing reveal. */
  lastFill?: FillHint | null;
}

const blankRows = () => Array.from({ length: 24 }, () => ' '.repeat(80));

export function TerminalPane(p: TerminalPaneProps) {
  const rawRows = p.screen?.rows ?? blankRows();
  const rows = useRevealedRows(rawRows, p.lastFill ?? null, { reduceMotion: p.reduceMotion, skip: p.focusQueue.length > 0 });
  const fields = p.screen?.fields ?? [];
  const cursor = p.screen?.cursor ?? [0, 0];
  const dormant = p.screen === null;

  return (
    <div className="term-frame">
    <div className="term-screen" data-effects={p.effects} data-dormant={dormant ? 'true' : 'false'}>
      <div className="term-stage">
        <Grid rows={rows} fields={fields} cursor={cursor} screenName={p.screenName} />
        <Planchette queue={p.focusQueue} reduceMotion={p.reduceMotion} onConsumed={p.onFocusConsumed} />
        <div className="crt-overlay" aria-hidden="true" />
      </div>
      {dormant && <p className="term-dormant">{strings.dormant}</p>}
      <Oia
        sessionState={p.sessionState}
        readOnly={p.readOnly}
        screenId={p.screen?.screenId ?? null}
        busy={p.busy}
        replay={p.replay}
        uncharted={p.uncharted}
      />
      {p.showAsText && (
        <ScreenAsText rows={rows} fields={fields} cursor={cursor} screenName={p.screenName} />
      )}
    </div>
    </div>
  );
}
