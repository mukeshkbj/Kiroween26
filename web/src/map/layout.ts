import dagre from 'dagre';
import type { MapEdge, MapFrontier, MapNode, SpiritMapView } from '../protocol/types';

/**
 * Deterministic graph layout (REQ-013). dagre does the ranking; we make it reproducible by feeding nodes and
 * edges in sorted order, using fixed node sizes, and rounding every coordinate. The same SpiritMapView always
 * gives the same output, whatever order the arrays arrived in.
 */

export const NODE_W = 168;
export const NODE_H = 60;
export const FRONTIER_LEN = 56;

export interface Pt {
  x: number;
  y: number;
}

export interface PlacedNode {
  id: string;
  /** centre */
  x: number;
  y: number;
  w: number;
  h: number;
  node: MapNode;
}

export interface PlacedEdge {
  id: string;
  from: string;
  to: string;
  key: string;
  label: string;
  readOnly: boolean;
  points: Pt[];
  labelAt: Pt;
}

export interface PlacedFrontier {
  id: string;
  from: string;
  key: string;
  reason: string;
  /** "needs confirmation" or "not explored": text, so meaning never rests on colour (REQ-013). */
  label: string;
  points: Pt[];
  labelAt: Pt;
}

export interface Layout {
  nodes: PlacedNode[];
  edges: PlacedEdge[];
  frontier: PlacedFrontier[];
  width: number;
  height: number;
}

const r = (n: number) => Math.round(n * 100) / 100;
const byId = <T extends { id: string }>(a: T, b: T) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);

export const edgeLabel = (e: Pick<MapEdge, 'key' | 'meaning'>): string => (e.meaning ? `${e.key}: ${e.meaning}` : e.key);

export function frontierLabel(f: Pick<MapFrontier, 'reason'>): string {
  return f.reason === 'denied_commit' ? 'needs confirmation' : 'not explored';
}

export function layoutMap(view: SpiritMapView): Layout {
  const g = new dagre.graphlib.Graph({ multigraph: true });
  g.setGraph({ rankdir: 'TB', nodesep: 44, ranksep: 64, marginx: 24, marginy: 24, ranker: 'network-simplex' });
  g.setDefaultEdgeLabel(() => ({}));

  const nodes = [...view.nodes].sort(byId);
  for (const n of nodes) g.setNode(n.id, { width: NODE_W, height: NODE_H });

  const known = new Set(nodes.map((n) => n.id));
  const edges = [...view.edges].filter((e) => known.has(e.from) && known.has(e.to)).sort(byId);
  for (const e of edges) g.setEdge(e.from, e.to, { label: edgeLabel(e), width: 90, height: 14 }, e.id);

  dagre.layout(g);

  const placed: PlacedNode[] = nodes.map((n) => {
    const p = g.node(n.id) as { x: number; y: number };
    return { id: n.id, x: r(p.x), y: r(p.y), w: NODE_W, h: NODE_H, node: n };
  });
  const pos = new Map(placed.map((p) => [p.id, p]));

  const placedEdges: PlacedEdge[] = edges.map((e) => {
    const d = g.edge({ v: e.from, w: e.to, name: e.id }) as { points: Pt[]; x?: number; y?: number };
    const points = d.points.map((p) => ({ x: r(p.x), y: r(p.y) }));
    const mid = points[Math.floor(points.length / 2)] ?? { x: 0, y: 0 };
    return {
      id: e.id, from: e.from, to: e.to, key: e.key, label: edgeLabel(e), readOnly: e.read_only,
      points, labelAt: d.x !== undefined && d.y !== undefined ? { x: r(d.x), y: r(d.y) } : mid,
    };
  });

  // Frontier items are stubs leaving their node to the right. Several on one node fan out vertically.
  const perNode = new Map<string, number>();
  const frontier = [...view.frontier]
    .filter((f) => known.has(f.from))
    .sort((a, b) => (a.from + a.key + a.reason < b.from + b.key + b.reason ? -1 : 1))
    .map<PlacedFrontier>((f, i) => {
      const n = pos.get(f.from) as PlacedNode;
      const k = perNode.get(f.from) ?? 0;
      perNode.set(f.from, k + 1);
      const y = n.y + (k - 0) * 18 - 0;
      const x0 = n.x + n.w / 2;
      const points = [{ x: r(x0), y: r(y) }, { x: r(x0 + FRONTIER_LEN), y: r(y) }];
      return {
        id: `f_${i}_${f.from}_${f.key}_${f.reason}`, from: f.from, key: f.key, reason: f.reason,
        label: `${f.key}: ${frontierLabel(f)}`, points, labelAt: { x: r(x0 + FRONTIER_LEN + 4), y: r(y) },
      };
    });

  const gr = g.graph() as { width?: number; height?: number };
  const maxFrontierX = frontier.reduce((m, f) => Math.max(m, f.labelAt.x + 150), 0);
  return {
    nodes: placed,
    edges: placedEdges,
    frontier,
    width: Math.ceil(Math.max(gr.width ?? 0, maxFrontierX)),
    height: Math.ceil(gr.height ?? 0),
  };
}
