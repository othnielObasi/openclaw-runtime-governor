export interface ClientOptions {
  baseUrl?: string;
  apiKey?: string;
}

export class GovernorClient {
  baseUrl: string;
  apiKey?: string;

  constructor(opts: ClientOptions = {}) {
    this.baseUrl = opts.baseUrl || (process.env.GOVERNOR_URL as string) || '';
    this.apiKey = opts.apiKey || (process.env.GOVERNOR_API_KEY as string) || undefined;
    if (!this.baseUrl) throw new Error('Governor baseUrl required (env GOVERNOR_URL or option)');
  }

  private headers() {
    const h: Record<string,string> = { 'Accept': 'application/json' };
    if (this.apiKey) h['X-API-Key'] = this.apiKey;
    return h;
  }

  async request(path: string, init: RequestInit = {}) {
    const url = this.baseUrl.replace(/\/$/, '') + '/' + path.replace(/^\//, '');
    const headers = { ...(init.headers || {}), ...this.headers() } as Record<string,string>;
    const res = await fetch(url, { ...init, headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    const ct = res.headers.get('content-type') || '';
    if (ct.startsWith('application/json')) return res.json();
    return res.text();
  }

  ping() {
    return this.request('/health').catch(() => this.request('/'));
  }
}

export default GovernorClient;
