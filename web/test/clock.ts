import { act } from '@testing-library/react';
import type { Timer } from '../src/protocol/transport';

/** A manual clock for transports: time only moves when the test says so. Tasks fire inside act(). */
export class Clock {
  now = 0;
  private tasks: { at: number; fn: () => void; id: number }[] = [];
  private n = 0;
  timer: Timer = (fn, ms) => {
    const id = ++this.n;
    this.tasks.push({ at: this.now + ms, fn, id });
    return () => {
      this.tasks = this.tasks.filter((t) => t.id !== id);
    };
  };
  advance(ms: number) {
    const end = this.now + ms;
    for (;;) {
      const due = this.tasks.filter((t) => t.at <= end).sort((a, b) => a.at - b.at || a.id - b.id)[0];
      if (!due) break;
      this.tasks = this.tasks.filter((t) => t !== due);
      this.now = due.at;
      act(() => due.fn());
    }
    this.now = end;
  }
}
