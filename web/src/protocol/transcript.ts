/** Transcript format of docs/contracts/examples/README.md. */
export type TranscriptLine =
  | { dir: 'server'; delay_ms: number; event: unknown }
  | { dir: 'client'; msg: unknown };

export function parseTranscript(text: string): TranscriptLine[] {
  return text
    .split(/\r?\n/)
    .filter((l) => l.trim() !== '')
    .map((l, i) => {
      const v = JSON.parse(l) as TranscriptLine;
      if (v.dir !== 'server' && v.dir !== 'client') throw new Error(`transcript line ${i + 1}: bad "dir"`);
      return v;
    });
}
