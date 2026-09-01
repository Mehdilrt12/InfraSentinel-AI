import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { API_BASE_URL, api, hasAccessToken } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { RealtimeEvent } from "../types/api";
import { useToast } from "../components/common";

export type RealtimeStatus = "connecting" | "live" | "polling" | "offline";
interface RealtimeContextValue {
  status: RealtimeStatus;
  lastEventAt: string | null;
  lastSequence: number;
  events: RealtimeEvent[];
  reconnect: () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);
export function resolvePollInterval(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(10_000, parsed) : 30_000;
}
const POLL_INTERVAL = resolvePollInterval(
  import.meta.env.VITE_POLL_INTERVAL_MS || 30_000,
);

export function shouldAcceptRealtimeEvent(
  lastSequence: number,
  event: RealtimeEvent,
) {
  return Number.isFinite(event.sequence) && event.sequence > lastSequence;
}

export function nextReconnectDelay(attempt: number, random = Math.random()) {
  const base = Math.min(30_000, 1_000 * 2 ** Math.max(0, attempt));
  return Math.round(base * (0.8 + random * 0.4));
}

function websocketUrl() {
  if (import.meta.env.VITE_WS_URL)
    return new URL(import.meta.env.VITE_WS_URL, window.location.origin);
  const apiUrl = new URL(API_BASE_URL, window.location.origin);
  apiUrl.protocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  apiUrl.pathname = "/ws/events/";
  apiUrl.search = "";
  return apiUrl;
}

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const tenantKey = user?.customer || "platform";
  const storageKey = `infrasentinel.realtime.${tenantKey}.sequence`;
  const [status, setStatus] = useState<RealtimeStatus>(
    navigator.onLine ? "connecting" : "offline",
  );
  const [events, setEvents] = useState<RealtimeEvent[]>([]);
  const [lastEventAt, setLastEventAt] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<number | null>(null);
  const reconnectAttempt = useRef(0);
  const sequenceRef = useRef(Number(sessionStorage.getItem(storageKey) || 0));
  const mountedRef = useRef(true);

  const invalidateForEvent = useCallback(
    (eventType: string) => {
      const roots: Record<string, string[]> = {
        "machine.online": ["dashboard", "machines", "agents"],
        "machine.offline": ["dashboard", "machines", "alerts"],
        "metric.update": ["dashboard", "metrics", "predictions"],
        "alert.created": ["dashboard", "alerts"],
        "alert.updated": ["dashboard", "alerts"],
        "anomaly.detected": ["dashboard", "anomalies", "alerts", "ml-models"],
      };
      const affected = roots[eventType] || ["dashboard"];
      void queryClient.invalidateQueries({
        predicate: (query) => affected.includes(String(query.queryKey[0])),
      });
    },
    [queryClient],
  );

  const consume = useCallback(
    (event: RealtimeEvent, announce = false) => {
      if (!shouldAcceptRealtimeEvent(sequenceRef.current, event)) return false;
      sequenceRef.current = event.sequence;
      sessionStorage.setItem(storageKey, String(event.sequence));
      setEvents((current) =>
        [
          event,
          ...current.filter((item) => item.sequence !== event.sequence),
        ].slice(0, 50),
      );
      setLastEventAt(event.created_at || new Date().toISOString());
      invalidateForEvent(event.event_type);
      if (announce) {
        const entity = String(
          event.payload.hostname ||
            event.payload.machine_name ||
            event.payload.machine_id ||
            event.aggregate_id ||
            "Infrastructure",
        );
        if (event.event_type === "machine.offline")
          notify({
            tone: "error",
            title: "Machine hors ligne",
            detail: entity,
          });
        if (event.event_type === "machine.online")
          notify({
            tone: "success",
            title: "Machine reconnectée",
            detail: entity,
          });
        if (event.event_type === "anomaly.detected")
          notify({
            tone: "warning",
            title: "Nouvelle anomalie ML",
            detail: entity,
          });
        if (
          event.event_type === "alert.created" &&
          String(event.payload.severity || "").toUpperCase() === "CRITICAL"
        )
          notify({
            tone: "error",
            title: "Nouvelle alerte critique",
            detail: String(event.payload.message || entity),
          });
      }
      return true;
    },
    [invalidateForEvent, notify, storageKey],
  );

  const replay = useCallback(async () => {
    if (!hasAccessToken() || !user?.customer) return;
    let loops = 0;
    while (loops < 5) {
      const { data } = await api.get<
        RealtimeEvent[] | { results?: RealtimeEvent[] }
      >("/realtime/replay/", { params: { since: sequenceRef.current } });
      const batch = Array.isArray(data) ? data : data.results || [];
      batch.forEach((event) => consume(event));
      loops += 1;
      if (batch.length < 500) break;
    }
  }, [consume, user?.customer]);

  useEffect(() => {
    mountedRef.current = true;
    sequenceRef.current = Number(sessionStorage.getItem(storageKey) || 0);
    setEvents([]);
    setLastEventAt(null);

    const clearReconnect = () => {
      if (reconnectTimer.current !== null)
        window.clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    };
    const closeSocket = () => {
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.close();
      }
    };

    const connect = async () => {
      clearReconnect();
      if (
        !mountedRef.current ||
        !navigator.onLine ||
        !hasAccessToken() ||
        !user?.customer
      ) {
        setStatus(navigator.onLine ? "polling" : "offline");
        return;
      }
      if (
        socketRef.current?.readyState === WebSocket.CONNECTING ||
        socketRef.current?.readyState === WebSocket.OPEN
      )
        return;
      setStatus("connecting");
      try {
        await replay();
        const { data } = await api.post<{ ticket: string; expires_in: number }>(
          "/realtime/ticket/",
        );
        const url = websocketUrl();
        url.searchParams.set("ticket", data.ticket);
        url.searchParams.set("since", String(sequenceRef.current));
        const socket = new WebSocket(url);
        socketRef.current = socket;
        socket.onopen = () => {
          if (!mountedRef.current || socketRef.current !== socket) return;
          reconnectAttempt.current = 0;
          setStatus("live");
        };
        socket.onmessage = (message) => {
          try {
            consume(JSON.parse(String(message.data)) as RealtimeEvent, true);
          } catch {
            /* Malformed frames are ignored without exposing payloads. */
          }
        };
        socket.onerror = () => socket.close();
        socket.onclose = () => {
          if (!mountedRef.current || socketRef.current !== socket) return;
          socketRef.current = null;
          setStatus(navigator.onLine ? "polling" : "offline");
          reconnectTimer.current = window.setTimeout(
            connect,
            nextReconnectDelay(reconnectAttempt.current++),
          );
        };
      } catch {
        if (!mountedRef.current) return;
        setStatus(navigator.onLine ? "polling" : "offline");
        reconnectTimer.current = window.setTimeout(
          connect,
          nextReconnectDelay(reconnectAttempt.current++),
        );
      }
    };

    void connect();
    const pollTimer = window.setInterval(() => {
      if (!navigator.onLine) return;
      if (socketRef.current?.readyState !== WebSocket.OPEN) {
        void replay().catch(() => undefined);
        void queryClient.invalidateQueries({
          predicate: (query) =>
            ["dashboard", "machines", "alerts", "anomalies"].includes(
              String(query.queryKey[0]),
            ),
        });
      }
    }, POLL_INTERVAL);
    const online = () => {
      setStatus("connecting");
      void connect();
    };
    const offline = () => {
      closeSocket();
      setStatus("offline");
    };
    window.addEventListener("online", online);
    window.addEventListener("offline", offline);

    return () => {
      mountedRef.current = false;
      window.clearInterval(pollTimer);
      clearReconnect();
      closeSocket();
      window.removeEventListener("online", online);
      window.removeEventListener("offline", offline);
    };
  }, [consume, generation, queryClient, replay, storageKey, user?.customer]);

  const value = useMemo(
    () => ({
      status,
      lastEventAt,
      lastSequence: sequenceRef.current,
      events,
      reconnect: () => setGeneration((value) => value + 1),
    }),
    [status, lastEventAt, events],
  );
  return (
    <RealtimeContext.Provider value={value}>
      {children}
    </RealtimeContext.Provider>
  );
}

export function useRealtime() {
  const context = useContext(RealtimeContext);
  if (!context)
    throw new Error("useRealtime doit être utilisé dans RealtimeProvider");
  return context;
}
