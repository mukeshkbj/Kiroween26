import { useRef, type KeyboardEvent } from 'react';
import { strings } from '../strings';
import { frontierLabel } from './layout';
import type { SpiritMapView } from '../protocol/types';

/**
 * The accessible equivalent of the graph (REQ-014): the same data as a table. Each screen lists its outgoing
 * keys with destination and whether the key is read-only or needs confirmation, and the tools passing through.
 * It is not hidden behind the graph: Up/Down move between rows, Enter selects.
 */

export interface MapTableProps {
  view: SpiritMapView;
  currentNodeId: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function MapTable({ view, currentNodeId, selectedId, onSelect }: MapTableProps) {
  const bodyRef = useRef<HTMLTableSectionElement | null>(null);
  const nameOf = new Map(view.nodes.map((n) => [n.id, n.name]));

  const onKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const rows = bodyRef.current?.querySelectorAll<HTMLButtonElement>('button[data-row]');
    if (!rows) return;
    let n: number | null = null;
    if (e.key === 'ArrowDown') n = Math.min(rows.length - 1, i + 1);
    if (e.key === 'ArrowUp') n = Math.max(0, i - 1);
    if (e.key === 'Home') n = 0;
    if (e.key === 'End') n = rows.length - 1;
    if (n !== null) {
      e.preventDefault();
      rows[n]?.focus();
    }
  };

  return (
    <table className="map-table" aria-label={strings.map.tableLabel}>
      <thead>
        <tr>
          {(['screen', 'kind', 'confidence', 'keys', 'tools'] as const).map((c) => (
            <th key={c} scope="col">
              {strings.map.cols[c]}
            </th>
          ))}
        </tr>
      </thead>
      <tbody ref={bodyRef}>
        {view.nodes.map((n, i) => {
          const out = view.edges.filter((e) => e.from === n.id);
          const front = view.frontier.filter((f) => f.from === n.id);
          const tools = view.tools.filter((t) => t.path.includes(n.id));
          const here = n.id === currentNodeId;
          return (
            <tr key={n.id} data-node-row={n.id} aria-current={here ? 'true' : undefined} className={n.id === selectedId ? 'row-selected' : undefined}>
              <th scope="row">
                <button type="button" data-row onClick={() => onSelect(n.id)} onKeyDown={(e) => onKey(e, i)} aria-pressed={n.id === selectedId}>
                  {n.name}
                </button>
                {here && <span className="here-tag"> ({strings.map.youAreHere})</span>}
                {n.needs_review && <span className="review-tag"> ({strings.map.needsReview})</span>}
              </th>
              <td>{n.kind}</td>
              <td>{Math.round(n.confidence * 100)}%</td>
              <td>
                {out.length === 0 && front.length === 0 ? (
                  strings.map.none
                ) : (
                  <ul className="map-keys">
                    {out.map((e) => (
                      <li key={e.id}>
                        <kbd>{e.key}</kbd> → {nameOf.get(e.to) ?? e.to}
                        {e.meaning ? ` (${e.meaning})` : ''}{' '}
                        <em>{e.read_only ? strings.map.readOnlyKey : strings.map.needsConfirmation}</em>
                      </li>
                    ))}
                    {front.map((f, k) => (
                      <li key={`f${k}`}>
                        <kbd>{f.key}</kbd> <em>{frontierLabel(f)}</em>
                        {f.meaning ? ` (${f.meaning})` : ''}
                      </li>
                    ))}
                  </ul>
                )}
              </td>
              <td>{tools.length === 0 ? strings.map.none : tools.map((t) => `${t.name} (${t.kind}${t.approved ? '' : ', unapproved'})`).join(', ')}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
