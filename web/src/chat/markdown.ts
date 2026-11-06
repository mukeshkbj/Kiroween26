/**
 * A tiny, safe markdown subset (REQ-007, REQ-022). Server/LLM text is UNTRUSTED: it is never HTML, never run,
 * never auto-opened. We parse a small grammar into a tree of nodes that SafeText.tsx renders through React as
 * plain elements. Supported: paragraphs, fenced code blocks, inline code, bold, italic, and links (rendered as
 * text + a non-auto-opening anchor). Everything else is literal text. No images, no raw HTML.
 */

export type Inline =
  | { t: 'text'; value: string }
  | { t: 'code'; value: string }
  | { t: 'strong'; children: Inline[] }
  | { t: 'em'; children: Inline[] }
  | { t: 'link'; href: string; label: string };

export type Block = { t: 'p'; children: Inline[] } | { t: 'pre'; value: string };

const SAFE_SCHEME = /^(https?:|mailto:)/i;

/** A link is kept only if its scheme is safe; otherwise it degrades to plain text (defuses javascript: etc). */
function safeHref(href: string): string | null {
  const h = href.trim();
  if (SAFE_SCHEME.test(h)) return h;
  if (h.startsWith('/') || h.startsWith('#')) return h;
  return null;
}

function parseInline(src: string): Inline[] {
  const out: Inline[] = [];
  let i = 0;
  let text = '';
  const flush = () => {
    if (text) out.push({ t: 'text', value: text });
    text = '';
  };
  while (i < src.length) {
    const rest = src.slice(i);

    // inline code: `...`
    const code = /^`([^`]+)`/.exec(rest);
    if (code) {
      flush();
      out.push({ t: 'code', value: code[1] as string });
      i += code[0].length;
      continue;
    }
    // link: [label](href)
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)/.exec(rest);
    if (link) {
      const href = safeHref(link[2] as string);
      flush();
      if (href) out.push({ t: 'link', href, label: link[1] as string });
      else out.push({ t: 'text', value: link[1] as string });
      i += link[0].length;
      continue;
    }
    // bold: **...**
    const strong = /^\*\*([^*]+)\*\*/.exec(rest);
    if (strong) {
      flush();
      out.push({ t: 'strong', children: parseInline(strong[1] as string) });
      i += strong[0].length;
      continue;
    }
    // italic: *...* (not part of **)
    const em = /^\*([^*]+)\*/.exec(rest);
    if (em) {
      flush();
      out.push({ t: 'em', children: parseInline(em[1] as string) });
      i += em[0].length;
      continue;
    }
    text += src[i];
    i += 1;
  }
  flush();
  return out;
}

export function parseMarkdown(src: string): Block[] {
  const blocks: Block[] = [];
  const lines = src.replace(/\r\n/g, '\n').split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] as string;
    // fenced code block
    if (line.trimStart().startsWith('```')) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !(lines[i] as string).trimStart().startsWith('```')) {
        body.push(lines[i] as string);
        i += 1;
      }
      i += 1; // closing fence (or EOF)
      blocks.push({ t: 'pre', value: body.join('\n') });
      continue;
    }
    if (line.trim() === '') {
      i += 1;
      continue;
    }
    // paragraph: consecutive non-blank, non-fence lines
    const para: string[] = [];
    while (i < lines.length && (lines[i] as string).trim() !== '' && !(lines[i] as string).trimStart().startsWith('```')) {
      para.push(lines[i] as string);
      i += 1;
    }
    blocks.push({ t: 'p', children: parseInline(para.join(' ')) });
  }
  return blocks;
}
