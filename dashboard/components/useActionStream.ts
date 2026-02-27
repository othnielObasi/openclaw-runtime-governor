"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export interface StreamAction {
  event: string;
  tool: string;
  decision: string;
  risk_score: number;
  explanation: string;
  policy_ids: string[];
  agent_id?: string;
  session_id?: string;
  user_id?: string;
  channel?: string;
  chain_pattern?: string;
  timestamp: number;
}

export type StreamStatus = "connecting" | "connected" | "disconnected" | "error";

interface UseActionStreamOptions {
  /** Maximum items to keep in buffer (default 100) */
  maxItems?: number;
  /** Auto-reconnect delay in ms (default 3000) */
  reconnectDelay?: number;
  /** Whether the stream is enabled (default true) */
  enabled?: boolean;
}

/**
 * React hook for real-time governance action streaming via SSE.
 *
 * Connects to `GET /actions/stream` and yields parsed action events
 * as they arrive in real time. Automatically reconnects on disconnect.
 *
 * ```tsx
 * const { events, status, subscriberCount } = useActionStream();
 * ```
 */
export function useActionStream(opts: UseActionStreamOptions = {}) {
  const { maxItems = 100, reconnectDelay = 3000, enabled = true } = opts;

  const [events, setEvents] = useState<StreamAction[]>([]);
  const [status, setStatus] = useState<StreamStatus>("disconnected");
  const [subscriberCount, setSubscriberCount] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const baseUrl = process.env.NEXT_PUBLIC_GOVERNOR_API || "";

  const connect = useCallback(() => {
    if (!enabled || !baseUrl) return;

    // Build URL with auth — EventSource doesn't support custom headers,
    // so we pass the JWT token as a query param (the backend accepts both).
    const token =
      typeof window !== "undefined" ? localStorage.getItem("ocg_token") : null;

    const url = token
      ? `${baseUrl}/actions/stream?token=${encodeURIComponent(token)}`
      : `${baseUrl}/actions/stream`;

    setStatus("connecting");

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.addEventListener("connected", () => {
      setStatus("connected");
    });

    es.addEventListener("action_evaluated", (e: MessageEvent) => {
      try {
        const action: StreamAction = JSON.parse(e.data);
        setEvents((prev) => [action, ...prev].slice(0, maxItems));
      } catch {
        // ignore malformed events
      }
    });

    es.onerror = () => {
      es.close();
      setStatus("disconnected");
      // Auto-reconnect
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, reconnectDelay);
    };
  }, [enabled, baseUrl, maxItems, reconnectDelay]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setStatus("disconnected");
  }, []);

  const clearEvents = useCallback(() => setEvents([]), []);

  // Lifecycle: connect on mount, disconnect on unmount
  useEffect(() => {
    if (enabled) connect();
    return () => disconnect();
  }, [enabled, connect, disconnect]);

  // Poll subscriber count every 30s when connected
  useEffect(() => {
    if (status !== "connected") return;

    const fetchCount = async () => {
      try {
        const token =
          typeof window !== "undefined"
            ? localStorage.getItem("ocg_token")
            : null;
        const res = await fetch(`${baseUrl}/actions/stream/status`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = await res.json();
          setSubscriberCount(data.active_subscribers ?? 0);
        }
      } catch {
        // best-effort
      }
    };

    fetchCount();
    const interval = setInterval(fetchCount, 30_000);
    return () => clearInterval(interval);
  }, [status, baseUrl]);

  return { events, status, subscriberCount, clearEvents, disconnect, connect };
}
