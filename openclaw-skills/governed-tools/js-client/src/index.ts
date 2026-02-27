/**
 * @openclaw/governor-client
 * =========================
 * TypeScript client for the OpenClaw Governor – a runtime governance layer
 * for AI agents.
 *
 * The Governor evaluates every tool invocation against configurable policies
 * and returns an **allow / block / review** decision before the tool executes.
 *
 * Also provides trace observability: ingest agent trace spans, query traces,
 * and correlate governance decisions with the agent's execution timeline.
 *
 * @example
 * ```ts
 * import { GovernorClient } from "@openclaw/governor-client";
 *
 * const gov = new GovernorClient({
 *   baseUrl: "https://openclaw-governor.fly.dev",
 *   apiKey: "ocg_your_key_here",
 * });
 *
 * const decision = await gov.evaluate("shell_exec", { command: "ls -la" });
 * console.log(decision.decision); // "allow" | "block" | "review"
 * ```
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Decision returned by the Governor for a tool evaluation. */
export interface GovernorDecision {
  decision: "allow" | "block" | "review";
  risk_score: number;
  explanation: string;
  policy_ids: string[];
  modified_args: Record<string, unknown> | null;
  /** Additional fields the server may return. */
  [key: string]: unknown;
}

/** Options for constructing a {@link GovernorClient}. */
export interface GovernorClientOptions {
  /**
   * Base URL of the Governor service.
   * @default process.env.GOVERNOR_URL ?? "http://localhost:8000"
   */
  baseUrl?: string;

  /**
   * API key (`ocg_…`) sent as the `X-API-Key` header.
   * @default process.env.GOVERNOR_API_KEY ?? ""
   */
  apiKey?: string;

  /**
   * Request timeout in milliseconds.
   * @default 10_000
   */
  timeoutMs?: number;
}

// ── Trace types ──────────────────────────────────────────────

/** Valid span kinds for agent traces. */
export type SpanKind = "agent" | "llm" | "tool" | "governance" | "retrieval" | "chain" | "custom";

/** A single span to ingest into the trace system. */
export interface SpanInput {
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  kind: SpanKind;
  name: string;
  status?: "ok" | "error";
  start_time: string; // ISO 8601
  end_time?: string | null;
  duration_ms?: number | null;
  agent_id?: string | null;
  session_id?: string | null;
  attributes?: Record<string, unknown> | null;
  input?: string | null;
  output?: string | null;
  events?: Array<Record<string, unknown>> | null;
}

/** Result of a batch ingest call. */
export interface IngestResult {
  inserted: number;
  skipped: number;
}

/** Summary of a trace returned by list. */
export interface TraceListItem {
  trace_id: string;
  agent_id: string | null;
  session_id: string | null;
  span_count: number;
  governance_count: number;
  root_span_name: string | null;
  start_time: string;
  end_time: string | null;
  total_duration_ms: number | null;
  has_errors: boolean;
  has_blocks: boolean;
}

/** Full trace detail with all spans and governance decisions. */
export interface TraceDetail {
  trace_id: string;
  agent_id: string | null;
  session_id: string | null;
  spans: Array<Record<string, unknown>>;
  governance_decisions: Array<Record<string, unknown>>;
  span_count: number;
  governance_count: number;
  start_time: string | null;
  end_time: string | null;
  total_duration_ms: number | null;
  has_errors: boolean;
  has_blocks: boolean;
}

/** Delete result. */
export interface DeleteTraceResult {
  trace_id: string;
  spans_deleted: number;
}

/** Optional filters for listing traces. */
export interface TraceListOptions {
  agent_id?: string;
  session_id?: string;
  has_blocks?: boolean;
  limit?: number;
  offset?: number;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/**
 * Thrown when the Governor blocks a tool invocation.
 */
export class GovernorBlockedError extends Error {
  public readonly decision: GovernorDecision;

  constructor(tool: string, decision: GovernorDecision) {
    super(
      `Governor blocked tool '${tool}': ${decision.explanation ?? "no reason given"}`,
    );
    this.name = "GovernorBlockedError";
    this.decision = decision;
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

/**
 * Stateless HTTP client for the OpenClaw Governor service.
 *
 * Uses the built-in `fetch` API (Node 18+, all modern browsers).
 */
export class GovernorClient {
  public readonly baseUrl: string;
  public readonly apiKey: string;
  private readonly timeoutMs: number;

  constructor(options: GovernorClientOptions = {}) {
    const env = typeof process !== "undefined" ? process.env : ({} as Record<string, string | undefined>);
    this.baseUrl = (options.baseUrl ?? env.GOVERNOR_URL ?? "http://localhost:8000").replace(/\/+$/, "");
    this.apiKey = options.apiKey ?? env.GOVERNOR_API_KEY ?? "";
    this.timeoutMs = options.timeoutMs ?? 10_000;
  }

  // ── Internal helpers ────────────────────────────────────────

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) {
      h["X-API-Key"] = this.apiKey;
    }
    return h;
  }

  private async request<T = unknown>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const res = await fetch(url, {
        method,
        headers: this.headers(),
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`Governor API ${method} ${path} returned ${res.status}: ${text}`);
      }

      return (await res.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  // ── Public API ──────────────────────────────────────────────

  /**
   * Evaluate a tool call against the Governor.
   *
   * @returns The full decision object.
   * @throws {GovernorBlockedError} if the decision is `"block"`.
   */
  async evaluate(
    tool: string,
    args: Record<string, unknown>,
    context?: Record<string, unknown>,
  ): Promise<GovernorDecision> {
    const result = await this.request<GovernorDecision>(
      "POST",
      "/actions/evaluate",
      { tool, args, context: context ?? null },
    );

    if (result.decision === "block") {
      throw new GovernorBlockedError(tool, result);
    }

    return result;
  }

  /**
   * Convenience alias for {@link evaluate}.
   * Identical behaviour — callers should inspect `decision` for `"review"`
   * and handle accordingly.
   */
  async governedCall(
    tool: string,
    args: Record<string, unknown>,
    context?: Record<string, unknown>,
  ): Promise<GovernorDecision> {
    return this.evaluate(tool, args, context);
  }

  /**
   * Fetch the current admin status (kill switch state, etc.).
   */
  async getStatus(): Promise<Record<string, unknown>> {
    return this.request("GET", "/admin/status");
  }

  /**
   * Fetch the governor summary (total actions, block rate, etc.).
   */
  async getSummary(): Promise<Record<string, unknown>> {
    return this.request("GET", "/summary/moltbook");
  }

  // ── Trace observability ─────────────────────────────────────

  /**
   * Batch-ingest agent trace spans.
   *
   * Valid span kinds: agent, llm, tool, governance, retrieval, chain, custom.
   * Duplicate `span_id` values are silently skipped (idempotent).
   *
   * @param spans Array of span objects (up to 500).
   * @returns `{ inserted, skipped }` counts.
   */
  async ingestSpans(spans: SpanInput[]): Promise<IngestResult> {
    return this.request<IngestResult>("POST", "/traces/ingest", { spans });
  }

  /**
   * List traces with optional filters.
   *
   * @returns Array of trace summaries.
   */
  async listTraces(options?: TraceListOptions): Promise<TraceListItem[]> {
    const params = new URLSearchParams();
    if (options?.agent_id) params.set("agent_id", options.agent_id);
    if (options?.session_id) params.set("session_id", options.session_id);
    if (options?.has_blocks !== undefined) params.set("has_blocks", String(options.has_blocks));
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    const qs = params.toString();
    return this.request<TraceListItem[]>("GET", `/traces${qs ? `?${qs}` : ""}`);
  }

  /**
   * Fetch full trace detail — all spans plus correlated governance decisions.
   *
   * @param traceId The trace identifier.
   */
  async getTrace(traceId: string): Promise<TraceDetail> {
    return this.request<TraceDetail>("GET", `/traces/${encodeURIComponent(traceId)}`);
  }

  /**
   * Delete all spans for a trace (action log entries are preserved).
   *
   * @param traceId The trace identifier.
   * @returns `{ trace_id, spans_deleted }`.
   */
  async deleteTrace(traceId: string): Promise<DeleteTraceResult> {
    return this.request<DeleteTraceResult>("DELETE", `/traces/${encodeURIComponent(traceId)}`);
  }
}

// Default export for convenience
export default GovernorClient;
