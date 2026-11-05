import type { FieldOut } from '../protocol/types';
import { strings } from '../strings';

/**
 * A linear alternative to the grid (REQ-019): title line, each input field with its label and value, and the
 * cursor position. Hidden values never appear (they are already null on the wire; we show "hidden"). This is
 * always in the DOM next to the grid, revealed by a visible toggle, so screen-reader users are not forced to
 * parse 24 rows of text.
 */

export interface ScreenAsTextProps {
  rows: string[];
  fields: FieldOut[];
  cursor: [number, number];
  screenName: string | null;
}

function firstNonBlank(rows: string[]): string {
  for (const r of rows) if (r.trim() !== '') return r.trim();
  return '';
}

export function describeScreen(p: ScreenAsTextProps): string[] {
  const lines: string[] = [];
  lines.push(`${strings.screenRegion}: ${p.screenName ?? strings.uncharted}`);
  const title = firstNonBlank(p.rows);
  if (title) lines.push(`${strings.sat.title}: ${title}`);
  const inputs = p.fields.filter((f) => !f.protected);
  if (inputs.length > 0) {
    lines.push(strings.sat.inputs);
    for (const f of inputs) {
      const name = f.label && f.label.trim() !== '' ? f.label.trim().replace(/[=>\s]+$/, '') : `row ${f.row + 1}, col ${f.col + 1}`;
      const value = f.hidden ? strings.sat.hidden : (f.value ?? '').trim() || strings.sat.empty;
      lines.push(`  ${name}: ${value}`);
    }
  }
  lines.push(`${strings.sat.cursor}: ${strings.sat.rowCol(p.cursor[0] + 1, p.cursor[1] + 1)}`);
  return lines;
}

export function ScreenAsText(p: ScreenAsTextProps) {
  const lines = describeScreen(p);
  return (
    <div className="term-as-text" aria-label={strings.sat.region}>
      {lines.map((l, i) => (
        <p key={i} className="sat-line">
          {l}
        </p>
      ))}
    </div>
  );
}
