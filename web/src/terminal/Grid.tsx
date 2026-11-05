import { memo } from 'react';
import type { FieldOut } from '../protocol/types';
import { COLS, ROWS, rowRuns, type Run } from './geometry';
import { strings } from '../strings';

/**
 * The 24x80 phosphor grid (REQ-002). Real DOM text, never a canvas: selectable and readable by assistive tech.
 * Cells are sized in ch / line-height units, the same coordinate space the planchette uses, so a (row, col)
 * lands exactly on its cell at any zoom. Hidden fields are drawn as blank cells with a marker only; their value
 * is never in the DOM (REQ-022).
 */

export interface GridProps {
  rows: string[];
  fields: FieldOut[];
  cursor: [number, number];
  /** Screen name for the region label, or null for "uncharted". */
  screenName: string | null;
}

function fieldClass(f: FieldOut): string {
  const c = ['cell'];
  if (!f.protected) c.push('cell-input');
  if (f.numeric) c.push('cell-numeric');
  if (f.intensified) c.push('cell-intense');
  if (f.hidden) c.push('cell-hidden');
  return c.join(' ');
}

function fieldLabel(f: FieldOut): string {
  const parts: string[] = [];
  parts.push(f.protected ? 'protected' : 'input');
  if (f.numeric) parts.push('numeric');
  if (f.hidden) parts.push('hidden');
  const name = f.label && f.label.trim() !== '' ? f.label.trim().replace(/[=>\s]+$/, '') : null;
  return [name, parts.join(', '), `${f.length} characters`].filter(Boolean).join(', ');
}

const RowView = memo(function RowView({
  text,
  rowIndex,
  fields,
  cursorCol,
}: {
  text: string;
  rowIndex: number;
  fields: FieldOut[];
  cursorCol: number | null;
}) {
  const runs: Run[] = rowRuns(rowIndex, fields);
  const padded = text.padEnd(COLS, ' ').slice(0, COLS);

  return (
    <div className="term-row" aria-hidden={false}>
      {runs.map((run) => {
        const f = run.field !== null ? fields.find((x) => x.index === run.field) ?? null : null;
        // A hidden field's characters are already blanks on the wire; we render spaces and never read value.
        const content = padded.slice(run.col, run.col + run.length);
        const hasCursor = cursorCol !== null && cursorCol >= run.col && cursorCol < run.col + run.length;
        return (
          <span
            key={run.col}
            className={f ? fieldClass(f) : 'cell'}
            data-field={f ? f.index : undefined}
            data-hidden={f?.hidden ? 'true' : undefined}
            aria-label={f && !f.protected ? fieldLabel(f) : undefined}
            role={f && !f.protected ? 'text' : undefined}
          >
            {hasCursor ? (
              <>
                {content.slice(0, cursorCol - run.col)}
                <span className="term-cursor" aria-hidden="true">
                  {content[cursorCol - run.col] ?? ' '}
                </span>
                {content.slice(cursorCol - run.col + 1)}
              </>
            ) : (
              content
            )}
          </span>
        );
      })}
    </div>
  );
});

export const Grid = memo(function Grid({ rows, fields, cursor, screenName }: GridProps) {
  const [curRow, curCol] = cursor;
  const fieldsByRow = new Map<number, FieldOut[]>();
  for (const f of fields) {
    for (let r = f.row; r <= f.row + Math.floor((f.col + f.length - 1) / COLS); r++) {
      if (r >= ROWS) break;
      const arr = fieldsByRow.get(r) ?? [];
      arr.push(f);
      fieldsByRow.set(r, arr);
    }
  }

  return (
    <div
      className="term-grid"
      role="region"
      aria-label={`${strings.screenRegion}, ${screenName ?? strings.uncharted}`}
      style={{ ['--cols' as string]: COLS, ['--rows' as string]: ROWS }}
    >
      {rows.slice(0, ROWS).map((text, i) => (
        <RowView
          key={i}
          text={text}
          rowIndex={i}
          fields={fieldsByRow.get(i) ?? []}
          cursorCol={i === curRow ? curCol : null}
        />
      ))}
    </div>
  );
});
