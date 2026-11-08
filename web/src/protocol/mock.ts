import { parseApps, parseAudit, parseSpiritMap } from './guards';
import { parseTranscript, type TranscriptLine } from './transcript';
import type { AppInfo, AuditResponse, SpiritMapView } from './types';

/**
 * Mock mode data (REQ-023): the committed contract examples, read by relative path from docs/contracts (never
 * copied). Transcripts are loaded lazily so a live build does not carry them.
 */

export interface RestApi {
  apps(): Promise<AppInfo[]>;
  audit(limit?: number): Promise<AuditResponse>;
  spiritMap(appId: string): Promise<SpiritMapView | null>;
}

const transcriptLoaders = import.meta.glob('../../../docs/contracts/examples/transcripts/*.jsonl', {
  query: '?raw',
  import: 'default',
}) as Record<string, () => Promise<string>>;

const jsonLoaders = import.meta.glob(
  ['../../../docs/contracts/examples/rest/*.json', '../../../docs/contracts/examples/spirit-map/*.json'],
  { query: '?raw', import: 'default' },
) as Record<string, () => Promise<string>>;

const baseName = (p: string) => (p.split('/').pop() ?? p).replace(/\.(jsonl?)$/, '');

export const SCENARIOS = Object.keys(transcriptLoaders).map(baseName).sort();

export async function loadScenario(name: string): Promise<TranscriptLine[]> {
  const key = Object.keys(transcriptLoaders).find((k) => baseName(k) === name);
  if (!key) throw new Error(`unknown scenario "${name}"`);
  return parseTranscript(await (transcriptLoaders[key] as () => Promise<string>)());
}

async function loadJson(name: string, dir: string): Promise<unknown> {
  const key = Object.keys(jsonLoaders).find((k) => k.includes(`/${dir}/`) && baseName(k) === name);
  if (!key) throw new Error(`missing example ${dir}/${name}`);
  return JSON.parse(await (jsonLoaders[key] as () => Promise<string>)());
}

export const mockRest: RestApi = {
  async apps() {
    const apps = parseApps(await loadJson('apps', 'rest'));
    if (!apps) throw new Error('bad apps example');
    return apps;
  },
  async audit() {
    const a = parseAudit(await loadJson('audit', 'rest'));
    if (!a) throw new Error('bad audit example');
    return a;
  },
  async spiritMap(appId) {
    if (appId !== 'fake-insurance') return null;
    return parseSpiritMap(await loadJson('spirit-map-view', 'spirit-map'));
  },
};
