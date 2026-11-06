import { useState } from 'react';
import { SpiritMap } from './SpiritMap';
import { MapTable } from './MapTable';
import { NodePreview } from './NodePreview';
import { strings } from '../strings';
import type { SpiritMapView } from '../protocol/types';

/**
 * The spirit-map tab: graph, an always-reachable table toggle (open by default via `tableOpenByDefault`, which
 * the settings flag for screen-reader users sets), and the selected node's preview. The "uncharted" notice shows
 * when the screen on display has no node (REQ-012).
 */

export interface MapViewProps {
  view: SpiritMapView | null;
  loading?: boolean;
  currentNodeId: string | null;
  uncharted: boolean;
  trail: string[];
  tableOpenByDefault?: boolean;
}

export function MapView({ view, loading, currentNodeId, uncharted, trail, tableOpenByDefault = true }: MapViewProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [tableOpen, setTableOpen] = useState(tableOpenByDefault);

  if (loading) return <p className="map-loading">{strings.map.loadingMap}</p>;
  if (!view) return <p className="map-none">{strings.map.noMap}</p>;

  const selNode = view.nodes.find((n) => n.id === (selected ?? currentNodeId)) ?? null;

  return (
    <section className="map-view" aria-label={strings.map.region}>
      {uncharted && (
        <p className="map-uncharted" role="status">
          {strings.map.uncharted}
        </p>
      )}
      <div className="map-graph-scroll">
        <SpiritMap view={view} currentNodeId={currentNodeId} trail={trail} selectedId={selected} onSelect={setSelected} />
      </div>
      <button type="button" className="map-table-toggle" aria-expanded={tableOpen} onClick={() => setTableOpen((o) => !o)}>
        {tableOpen ? strings.map.tableToggleHide : strings.map.tableToggleShow}
      </button>
      {tableOpen && <MapTable view={view} currentNodeId={currentNodeId} selectedId={selected} onSelect={setSelected} />}
      {selNode && <NodePreview node={selNode} tools={view.tools} />}
    </section>
  );
}
