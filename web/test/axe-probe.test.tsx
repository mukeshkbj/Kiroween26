import { expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { axe } from 'vitest-axe';

it('vitest-axe runs under vitest 5 and finds a real violation', async () => {
  const { container } = render(<img src="x.png" />);
  const results = await axe(container);
  expect(results.violations.map((v) => v.id)).toContain('image-alt');
});
