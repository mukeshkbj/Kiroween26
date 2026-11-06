import { useMemo, type KeyboardEvent } from 'react';
import { layoutMap, type Layout, type Pt } from './layout';
import { strings } from '../strings';
import type { SpiritMapView } from '../protocol/types';

/**
 * The spirit-map as SVG (REQ-013). Nodes are screens, edges are keys. Read-only edges are solid; confirmation or
 * unexplored edges are dashed with a lock glyph AND a text label, never colour alone. The current node has a
 * thick outline plus a "you are here" tag; nodes needing review carry a text marker. The path taken in the
 * current tool call is highlighted. The table (MapTable) is the accessible equivalent; this graph is also
 * keyboard-navigable: Arrow keys move between nodes in layout order, Enter selects.
 */

export interface SpiritMapProps {
  view: SpiritMapView;
  currentNodeId: string | null;
  trail: string[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  layout?: Layout;
}

const path = (pts: Pt[]) => pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');

export function SpiritMap({ view, currentNodeId, trail, selectedId, onSelect, layout }: SpiritMapProps) {
  const l = useMemo(() => layout ?? layoutMap(view), [layout, view]);
  // Keyboard order: left-to-right, then top-to-bottom, i.e. the way the graph reads.
  const order = useMemo(
    () => [...l.nodes].sort((a, b) => a.x - b.x || a.y - b.y).map((n) => n.id),
    [l.nodes],
  );

  const trailEdges = new Set<string>();
  for (let i = 1; i < trail.length; i++) {
    const a = trail[i - 1];
    const b = trail[i];
    for (const e of l.edges) if (e.from === a && e.to === b) trailEdges.add(e.id);
  }

  const onKey = (e: KeyboardEvent<SVGGElement>, id: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect(id);
      return;
    }
    const idx = order.indexOf(id);
    let next: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = Math.min(order.length - 1, idx + 1);
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = Math.max(0, idx - 1);
    if (e.key === 'Home') next = 0;
    if (e.key === 'End') next = order.length - 1;
    if (next !== null) {
      e.preventDefault();
      const el = (e.currentTarget.ownerSVGElement ?? e.currentTarget).querySelector<SVGGElement>(`[data-node="${order[next]}"]`);
      el?.focus();
    }
  };

  return (
    <svg
      className="spirit-map"
      width={l.width}
      height={l.height}
      viewBox={`0 0 ${l.width} ${l.height}`}
      role="group"
      aria-label={strings.map.graphLabel}
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
        </marker>
      </defs>

      {l.edges.map((e) => (
        <g key={e.id} className={`map-edge ${e.readOnly ? 'edge-solid' : 'edge-dashed'}${trailEdges.has(e.id) ? ' edge-trail' : ''}`} data-edge={e.id}>
          <path d={path(e.points)} fill="none" strokeDasharray={e.readOnly ? undefined : '6 4'} markerEnd="url(#arrow)" />
          <text x={e.labelAt.x} y={e.labelAt.y - 4} textAnchor="middle" className="edge-label">
            {e.readOnly ? e.label : `\u{1F512} ${e.label} (${strings.map.needsConfirmation})`}
          </text>
        </g>
      ))}

      {l.frontier.map((f) => (
        <g key={f.id} className="map-frontier" data-frontier={f.reason}>
          <path d={path(f.points)} fill="none" strokeDasharray="3 4" />
          <text x={f.labelAt.x} y={f.labelAt.y + 4} className="edge-label">
            {`\u{1F512} ${f.label}`}
          </text>
        </g>
      ))}

      {l.nodes.map((n) => {
        const here = n.id === currentNodeId;
        const sel = n.id === selectedId;
        return (
          <g
            key={n.id}
            data-node={n.id}
            className={`map-node${here ? ' node-here' : ''}${sel ? ' node-selected' : ''}${n.node.needs_review ? ' node-review' : ''}`}
            tabIndex={0}
            role="button"
            aria-pressed={sel}
            aria-label={strings.map.nodeLabel(n.node.name, n.node.kind, here, n.node.needs_review)}
            onClick={() => onSelect(n.id)}
            onKeyDown={(e) => onKey(e, n.id)}
          >
            <rect x={n.x - n.w / 2} y={n.y - n.h / 2} width={n.w} height={n.h} rx={8} strokeWidth={here ? 4 : 1.5} />
            <text x={n.x} y={n.y - 6} textAnchor="middle" className="node-name">
              {n.node.name}
            </text>
            <text x={n.x} y={n.y + 12} textAnchor="middle" className="node-sub">
              {n.node.kind} · {Math.round(n.node.confidence * 100)}%
            </text>
            {here && (
              <text x={n.x} y={n.y - n.h / 2 - 6} textAnchor="middle" className="node-tag">
                {strings.map.youAreHere}
              </text>
            )}
            {n.node.needs_review && (
              <text x={n.x} y={n.y + n.h / 2 + 12} textAnchor="middle" className="node-tag node-tag-review">
                {strings.map.needsReview}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
