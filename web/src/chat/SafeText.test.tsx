import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { SafeText } from './SafeText';
import { parseMarkdown } from './markdown';

describe('SafeText sanitisation (REQ-007, REQ-022)', () => {
  it('renders bold, italic and inline code as elements', () => {
    const { container } = render(<SafeText text="a **bold** and *italic* and `code` here" />);
    expect(container.querySelector('strong')?.textContent).toBe('bold');
    expect(container.querySelector('em')?.textContent).toBe('italic');
    expect(container.querySelector('code.st-code')?.textContent).toBe('code');
  });

  it('never injects raw HTML', () => {
    const { container } = render(<SafeText text={'<img src=x onerror="alert(1)"> <b>hi</b>'} />);
    expect(container.querySelector('img')).toBeNull();
    // the <b> is shown as literal text, not an element
    expect(container.querySelector('b')).toBeNull();
    expect(container.textContent).toContain('<b>hi</b>');
  });

  it('keeps http(s)/mailto links but never auto-opens them; drops dangerous schemes to text', () => {
    const { container } = render(
      <SafeText text="see [docs](https://example.com) and [bad](javascript:alert(1)) and [m](mailto:a@b.co)" />,
    );
    const links = Array.from(container.querySelectorAll('a'));
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['https://example.com', 'mailto:a@b.co']);
    for (const a of links) {
      expect(a.getAttribute('rel')).toContain('noopener');
      expect(a.getAttribute('target')).toBe('_blank');
    }
    // the javascript: link became plain text
    expect(container.textContent).toContain('bad');
    expect(container.innerHTML).not.toContain('javascript:');
  });

  it('renders fenced code blocks verbatim without interpreting their contents', () => {
    const { container } = render(<SafeText text={'before\n```\n**not bold** <script>\n```\nafter'} />);
    const pre = container.querySelector('pre.st-pre code') as HTMLElement;
    expect(pre.textContent).toBe('**not bold** <script>');
    expect(container.querySelector('pre strong')).toBeNull();
  });

  it('splits blank-line-separated text into paragraphs', () => {
    const blocks = parseMarkdown('one\ntwo\n\nthree');
    expect(blocks).toHaveLength(2);
    expect(blocks[0]).toMatchObject({ t: 'p' });
  });

  it('treats a lone asterisk or backtick as literal text, not a crash', () => {
    const { container } = render(<SafeText text="2 * 3 = 6 and a ` tick" />);
    expect(container.textContent).toContain('2 * 3 = 6');
    expect(container.textContent).toContain('` tick');
  });
});
