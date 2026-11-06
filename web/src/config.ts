export type Mode = 'live' | 'mock';

export interface Config {
  agentUrl: string;
  mode: Mode;
  replaySpeed: number;
}

export function readConfig(env: Record<string, string | undefined> = import.meta.env): Config {
  const mode: Mode = env.VITE_MODE === 'mock' ? 'mock' : 'live';
  const speed = Number(env.VITE_REPLAY_SPEED ?? '1');
  return {
    agentUrl: (env.VITE_AGENT_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, ''),
    mode,
    replaySpeed: Number.isFinite(speed) && speed > 0 ? speed : 1,
  };
}

export const config: Config = readConfig();
