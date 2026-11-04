/** Loads the committed contract examples straight from docs/contracts/ (never copied). */
export type TranscriptLine =
  | { dir: 'server'; delay_ms: number; event: unknown }
  | { dir: 'client'; msg: unknown };

const eventFiles = import.meta.glob('../../docs/contracts/examples/events/*.json', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;
const transcriptFiles = import.meta.glob('../../docs/contracts/examples/transcripts/*.jsonl', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;
const restFiles = import.meta.glob('../../docs/contracts/examples/rest/*.json', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;
const mapFiles = import.meta.glob('../../docs/contracts/examples/spirit-map/*.json', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const baseName = (p: string) => (p.split('/').pop() ?? p).replace(/\.(jsonl?|JSON)$/, '');

export function parseTranscript(text: string): TranscriptLine[] {
  return text
    .split(/\r?\n/)
    .filter((l) => l.trim() !== '')
    .map((l) => JSON.parse(l) as TranscriptLine);
}

export function loadExamples() {
  const events: Record<string, unknown> = {};
  for (const [p, t] of Object.entries(eventFiles)) events[baseName(p)] = JSON.parse(t);
  const transcripts: Record<string, TranscriptLine[]> = {};
  for (const [p, t] of Object.entries(transcriptFiles)) transcripts[baseName(p)] = parseTranscript(t);
  const rest: Record<string, unknown> = {};
  for (const [p, t] of Object.entries(restFiles)) rest[baseName(p)] = JSON.parse(t);
  const mapText = Object.values(mapFiles)[0];
  const spiritMap: unknown = mapText ? JSON.parse(mapText) : null;
  return { events, transcripts, rest, spiritMap };
}
