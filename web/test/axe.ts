import { axe } from 'vitest-axe';
import type { AxeResults } from 'axe-core';

/**
 * Automated accessibility check (REQ-028). vitest-axe 0.1.0 works with vitest 5 here (probe in axe-probe.test.tsx),
 * so no fallback to calling axe-core directly is needed.
 *
 * `color-contrast` is disabled because jsdom has no layout or computed colours to measure; contrast is covered by
 * the arithmetic over the design tokens in src/terminal/contrast.test.ts and by the manual pass in web/A11Y.md.
 * Automated checks find only some problems and prove nothing about WCAG conformance.
 */

export interface AxeOptions {
  /** A fragment rendered on its own has no page landmarks around it; that rule only applies to whole pages. */
  fragment?: boolean;
}

export async function runAxe(root: Element | Document = document.body, o: AxeOptions = {}): Promise<AxeResults> {
  return axe(root as Element, {
    rules: { 'color-contrast': { enabled: false }, ...(o.fragment ? { region: { enabled: false } } : {}) },
  });
}

export function describeViolations(r: AxeResults): string {
  return r.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help}\n${v.nodes.slice(0, 3).map((n) => '  ' + n.html.slice(0, 140)).join('\n')}`)
    .join('\n');
}

export async function expectNoViolations(root: Element | Document = document.body, o: AxeOptions = {}): Promise<void> {
  const r = await runAxe(root, o);
  if (r.violations.length > 0) throw new Error(`axe found ${r.violations.length} violation(s):\n${describeViolations(r)}`);
}
