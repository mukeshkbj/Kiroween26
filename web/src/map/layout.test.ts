import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { NODE_H, NODE_W, layoutMap, frontierLabel } from './layout';
import { parseSpiritMap } from '../protocol/guards';
import { loadExamples } from '../../test/examples';
import type { MapNode, SpiritMapView } from '../protocol/types';

const ex = loadExamples();
const example = parseSpiritMap(ex.spiritMap) as SpiritMapView;

const node = (id: string): MapNode => ({
  id, screen_id: id.padEnd(64, '0'), name: id, kind: 'menu', confidence: 0.9, needs_review: false, visits: 1,
  preview: Array.from({ length: 24 }, () => ' '.repeat(80)), fields: [],
});

const graphArb = fc
  .integer({ min: 1, max: 12 })
  .chain((n) => {
    const ids = Array.from({ length: n }, (_, i) => `n_${String(i).padStart(2, '0')}`);
    return fc
      .array(fc.tuple(fc.constantFrom(...ids), fc.constantFrom(...ids), fc.constantFrom('ENTER', 'PF3', 'PF8'), fc.boolean()), { maxLength: 25 })
      .map((es) => ({
        app_id: 'x', version: 'v', generated_at: 't', home: ids[0] as string,
        nodes: ids.map(node),
        edges: es.map(([from, to, key, ro], i) => ({ id: `e_${String(i).padStart(3, '0')}`, from, to, key, meaning: null, read_only: ro, status: 'observed' as const })),
        frontier: [], tools: [],
      } satisfies SpiritMapView));
  });

describe('layoutMap (REQ-013)', () => {
  it('lays out the committed example: every node placed, edges have points', () => {
    const l = layoutMap(example);
    expect(l.nodes).toHaveLength(example.nodes.length);
    expect(l.edges.length).toBe(example.edges.length);
    for (const e of l.edges) expect(e.points.length).toBeGreaterThanOrEqual(2);
    expect(l.width).toBeGreaterThan(0);
    expect(l.height).toBeGreaterThan(0);
  });

  it('is deterministic: the same input always gives byte-identical output', () => {
    const a = JSON.stringify(layoutMap(example));
    for (let i = 0; i < 5; i++) expect(JSON.stringify(layoutMap(example))).toBe(a);
  });

  it('does not depend on the order of the input arrays', () => {
    const shuffled: SpiritMapView = { ...example, nodes: [...example.nodes].reverse(), edges: [...example.edges].reverse(), frontier: [...example.frontier].reverse() };
    expect(JSON.stringify(layoutMap(shuffled))).toBe(JSON.stringify(layoutMap(example)));
  });

  it('property: deterministic, order-independent, and nodes never overlap', () => {
    fc.assert(
      fc.property(graphArb, (view) => {
        const a = layoutMap(view);
        const b = layoutMap({ ...view, nodes: [...view.nodes].reverse(), edges: [...view.edges].reverse() });
        expect(JSON.stringify(a)).toBe(JSON.stringify(b));
        expect(JSON.stringify(layoutMap(view))).toBe(JSON.stringify(a));
        for (let i = 0; i < a.nodes.length; i++) {
          for (let j = i + 1; j < a.nodes.length; j++) {
            const p = a.nodes[i]!;
            const q = a.nodes[j]!;
            const overlap = Math.abs(p.x - q.x) < NODE_W && Math.abs(p.y - q.y) < NODE_H;
            expect(overlap, `${p.id} overlaps ${q.id}`).toBe(false);
          }
        }
        for (const n of a.nodes) {
          expect(Number.isFinite(n.x) && Number.isFinite(n.y)).toBe(true);
        }
      }),
      { numRuns: 60 },
    );
  });

  it('drops edges whose endpoints are not nodes instead of crashing', () => {
    const bad: SpiritMapView = { ...example, edges: [...example.edges, { id: 'e_zz', from: 'n_ghost', to: example.nodes[0]!.id, key: 'ENTER', meaning: null, read_only: true, status: 'observed' }] };
    expect(layoutMap(bad).edges.some((e) => e.id === 'e_zz')).toBe(false);
  });

  it('frontier stubs say "needs confirmation" for denied commits and "not explored" otherwise (text, not colour)', () => {
    expect(frontierLabel({ reason: 'denied_commit' })).toBe('needs confirmation');
    expect(frontierLabel({ reason: 'budget' })).toBe('not explored');
    const l = layoutMap(example);
    expect(l.frontier.length).toBe(example.frontier.length);
    expect(l.frontier.some((f) => f.label.includes('needs confirmation'))).toBe(true);
  });

  it('handles an empty map', () => {
    const l = layoutMap({ ...example, nodes: [], edges: [], frontier: [] });
    expect(l.nodes).toEqual([]);
  });
});
