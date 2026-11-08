import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createContext, useContext } from 'react';

/**
 * A single owner of the two live regions (REQ-019): one polite (rate-limited to 1/s), one assertive. All
 * announcements go through `useAnnouncer()` so step cards, connection changes and confirmations do not fight
 * each other. The regions hold text only; nothing here renders server HTML.
 */

export type Politeness = 'polite' | 'assertive';

interface AnnouncerApi {
  announce: (text: string, politeness?: Politeness) => void;
}

const Ctx = createContext<AnnouncerApi>({ announce: () => {} });

export const useAnnouncer = (): AnnouncerApi => useContext(Ctx);

export const POLITE_INTERVAL_MS = 1000;

export function AnnouncerProvider({ children, now = () => Date.now() }: { children: ReactNode; now?: () => number }) {
  const [polite, setPolite] = useState('');
  const [assertive, setAssertive] = useState('');
  const lastPolite = useRef(Number.NEGATIVE_INFINITY);
  const queued = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const flushPolite = () => {
    if (queued.current === null) return;
    setPolite(queued.current);
    lastPolite.current = now();
    queued.current = null;
  };

  const api: AnnouncerApi = {
    announce(text, politeness = 'polite') {
      if (politeness === 'assertive') {
        // Toggle through empty so repeated identical text is still read.
        setAssertive('');
        setAssertive(text);
        return;
      }
      const since = now() - lastPolite.current;
      queued.current = text;
      if (since >= POLITE_INTERVAL_MS) {
        if (timer.current) {
          clearTimeout(timer.current);
          timer.current = null;
        }
        flushPolite();
      } else if (!timer.current) {
        timer.current = setTimeout(() => {
          timer.current = null;
          flushPolite();
        }, POLITE_INTERVAL_MS - since);
      }
    },
  };

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="sr-only" aria-live="polite" aria-atomic="true" data-testid="live-polite">
        {polite}
      </div>
      <div className="sr-only" aria-live="assertive" aria-atomic="true" role="alert" data-testid="live-assertive">
        {assertive}
      </div>
    </Ctx.Provider>
  );
}
