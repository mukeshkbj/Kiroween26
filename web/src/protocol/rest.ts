import { parseApps, parseAudit, parseSpiritMap } from './guards';
import type { AppInfo, AuditResponse, HealthResponse, SpiritMapView } from './types';
import type { RestApi } from './mock';

/**
 * REST client for the agent (contracts section 5). Same-origin rules apply; responses are validated through the
 * guards and never trusted blindly. All text in these responses is data, never instructions.
 */

export class RestError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
    readonly code: string | null = null,
  ) {
    super(message);
    this.name = 'RestError';
  }
}

async function getJson(url: string, f: typeof fetch): Promise<unknown> {
  let res: Response;
  try {
    res = await f(url, { headers: { Accept: 'application/json' } });
  } catch {
    throw new RestError('agent unreachable', null, 'unreachable');
  }
  if (!res.ok) {
    let code: string | null = null;
    try {
      const body = (await res.json()) as { error?: string };
      code = body.error ?? null;
    } catch {
      /* non-json error body */
    }
    throw new RestError(`request failed (${res.status})`, res.status, code);
  }
  return res.json();
}

export class RestClient implements RestApi {
  constructor(
    private readonly baseUrl: string,
    private readonly f: typeof fetch = fetch,
  ) {}

  private url(path: string): string {
    return new URL(path, this.baseUrl.endsWith('/') ? this.baseUrl : this.baseUrl + '/').toString();
  }

  async health(): Promise<HealthResponse> {
    const raw = (await getJson(this.url('api/health'), this.f)) as HealthResponse;
    return raw;
  }

  async apps(): Promise<AppInfo[]> {
    const parsed = parseApps(await getJson(this.url('api/apps'), this.f));
    if (!parsed) throw new RestError('apps response not understood', null, 'bad_response');
    return parsed;
  }

  async audit(limit = 500): Promise<AuditResponse> {
    const parsed = parseAudit(await getJson(this.url(`api/audit?limit=${limit}`), this.f));
    if (!parsed) throw new RestError('audit response not understood', null, 'bad_response');
    return parsed;
  }

  /** null when the agent returns 404 no_map. */
  async spiritMap(appId: string): Promise<SpiritMapView | null> {
    try {
      const parsed = parseSpiritMap(await getJson(this.url(`api/apps/${encodeURIComponent(appId)}/spirit-map`), this.f));
      if (!parsed) throw new RestError('spirit-map response not understood', null, 'bad_response');
      return parsed;
    } catch (e) {
      if (e instanceof RestError && (e.status === 404 || e.code === 'no_map')) return null;
      throw e;
    }
  }
}
