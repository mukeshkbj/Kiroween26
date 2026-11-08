import type { FieldSnap } from '../protocol/types';
import type { ScreenState } from '../state/reducer';
import { COLS, ROWS, fieldRects } from '../terminal/geometry';
import { strings } from '../strings';

/**
 * A miniature of the 24x80 screen for the confirmation modal (REQ-016). Drawn from the latest `screen` event
 * whose screen_id equals the confirmation's, because the gate's field_snapshot lists only unprotected fields and
 * is empty on review screens. Fields from the snapshot are highlighted by position. Everything is text.
 */

export interface MiniScreenProps {
  screen: ScreenState;
  highlights: FieldSnap[];
}

function isHighlighted(row: number, col: number, spans: { row: number; from: number; to: number }[]): boolean {
  return spans.some((s) => s.row === row && col >= s.from && col < s.to);
}

export function MiniScreen({ screen, highlights }: MiniScreenProps) {
  // Highlight spans come from the gate's snapshot positions; length is taken from the screen's field at that
  // position when known, otherwise the value length, otherwise 1.
  const spans = highlights.flatMap((h) => {
    const f = screen.fields.find((x) => x.row === h.row && x.col === h.col);
    const len = f?.length ?? Math.max(1, (h.value ?? '').length);
    return fieldRects({ row: h.row, col: h.col, length: len }).map((r) => ({ row: r.y, from: r.x, to: r.x + r.w }));
  });

  return (
    <div className="mini-screen" role="img" aria-label={strings.confirm.miniLabel} data-screen-id={screen.screenId}>
      {screen.rows.slice(0, ROWS).map((text, r) => {
        const padded = text.padEnd(COLS, ' ').slice(0, COLS);
        // group consecutive highlighted / plain characters
        const parts: { hl: boolean; s: string }[] = [];
        for (let c = 0; c < COLS; c++) {
          const hl = isHighlighted(r, c, spans);
          const last = parts[parts.length - 1];
          if (last && last.hl === hl) last.s += padded[c];
          else parts.push({ hl, s: padded[c] as string });
        }
        return (
          <div key={r} className="mini-row">
            {parts.map((p, i) => (p.hl ? <mark key={i}>{p.s}</mark> : <span key={i}>{p.s}</span>))}
          </div>
        );
      })}
    </div>
  );
}
