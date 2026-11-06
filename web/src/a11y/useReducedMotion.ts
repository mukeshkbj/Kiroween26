import { useEffect, useState } from 'react';

/**
 * Reduced motion = the OS media query OR the in-app toggle (REQ-021). Every animation reads this one value so a
 * single switch turns all of them off. The in-app flag also sets data-motion="reduce" on <html> for the CSS.
 */

export function osReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function useOsReducedMotion(): boolean {
  const [reduce, setReduce] = useState(osReducedMotion);
  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setReduce(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduce;
}

/** Combine the OS query with an in-app preference; either one on means reduced. */
export function useReducedMotion(inAppReduce: boolean): boolean {
  const os = useOsReducedMotion();
  const reduce = os || inAppReduce;
  useEffect(() => {
    const el = document.documentElement;
    if (reduce) el.setAttribute('data-motion', 'reduce');
    else el.removeAttribute('data-motion');
  }, [reduce]);
  return reduce;
}
