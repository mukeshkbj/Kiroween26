import { strings } from '../strings';
import type { MapNode, MapTool } from '../protocol/types';

/**
 * Detail for the selected node (REQ-013): its screen preview, fields with business names, and the tools that
 * pass through it. Previews are sanitised by the generator and never contain hidden values; hidden fields are
 * listed by name only. All text is rendered as text.
 */

export interface NodePreviewProps {
  node: MapNode;
  tools: MapTool[];
}

export function NodePreview({ node, tools }: NodePreviewProps) {
  const through = tools.filter((t) => t.path.includes(node.id));
  return (
    <section className="node-preview" aria-label={strings.map.selected}>
      <h3>{node.name}</h3>
      <p>
        {node.kind} · {Math.round(node.confidence * 100)}% · {strings.map.visits(node.visits)}
        {node.needs_review && <strong> · {strings.map.needsReview}</strong>}
      </p>
      <pre className="node-preview-screen" aria-label={strings.map.preview}>
        {node.preview.join('\n')}
      </pre>
      <h4>{strings.map.fields}</h4>
      {node.fields.length === 0 ? (
        <p>{strings.map.none}</p>
      ) : (
        <ul className="node-fields">
          {node.fields.map((f) => (
            <li key={f.key}>
              <strong>{f.business_name ?? f.label ?? f.key}</strong> ({f.key}
              {f.role ? `, ${f.role}` : ''}, {f.protected ? 'protected' : 'input'}
              {f.hidden ? ', hidden' : ''}, row {f.row + 1} col {f.col + 1}, {f.length} chars)
            </li>
          ))}
        </ul>
      )}
      <h4>{strings.map.toolsThrough}</h4>
      {through.length === 0 ? (
        <p>{strings.map.none}</p>
      ) : (
        <ul>
          {through.map((t) => (
            <li key={t.name}>
              {t.name} ({t.kind}
              {t.approved ? '' : ', unapproved'})
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
