import { Fragment, type ReactNode } from 'react';
import { parseMarkdown, type Block, type Inline } from './markdown';

/**
 * Renders the safe markdown subset through React (never dangerouslySetInnerHTML). Links open in a new tab with
 * rel="noopener noreferrer nofollow" and are NOT auto-opened; the href is shown so a user sees where it goes.
 */

function renderInline(nodes: Inline[]): ReactNode {
  return nodes.map((n, i) => {
    switch (n.t) {
      case 'text':
        return <Fragment key={i}>{n.value}</Fragment>;
      case 'code':
        return (
          <code key={i} className="st-code">
            {n.value}
          </code>
        );
      case 'strong':
        return <strong key={i}>{renderInline(n.children)}</strong>;
      case 'em':
        return <em key={i}>{renderInline(n.children)}</em>;
      case 'link':
        return (
          <a key={i} href={n.href} target="_blank" rel="noopener noreferrer nofollow" className="st-link">
            {n.label}
          </a>
        );
    }
  });
}

function renderBlock(b: Block, i: number): ReactNode {
  if (b.t === 'pre') {
    return (
      <pre key={i} className="st-pre">
        <code>{b.value}</code>
      </pre>
    );
  }
  return <p key={i}>{renderInline(b.children)}</p>;
}

export function SafeText({ text }: { text: string }) {
  const blocks = parseMarkdown(text);
  return <div className="safe-text">{blocks.map(renderBlock)}</div>;
}
