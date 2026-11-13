import axios from "axios";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  // Android's emulator maps the host machine to 10.0.2.2. Physical devices
  // must set EXPO_PUBLIC_API_URL to a LAN-reachable URL.
  (Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://localhost:8000");

// Keep offline or unreachable cameras from leaving screens in a perpetual
// loading state. Individual calls can still override this when needed.
export const api = axios.create({ baseURL: BASE_URL, timeout: 15_000 });

let _onUnauthorized: (() => void) | null = null;
export function setUnauthorizedCallback(cb: () => void) {
  _onUnauthorized = cb;
}

api.interceptors.request.use(async (config) => {
  const token = await SecureStore.getItemAsync("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const requestUrl = String(err.config?.url ?? "");
    const isAuthRequest = /\/auth\/(login|register)(?:$|\?)/.test(requestUrl);
    if (err.response?.status === 401 && !isAuthRequest) {
      await SecureStore.deleteItemAsync("access_token");
      _onUnauthorized?.();
    }
    return Promise.reject(err);
  }
);

// ── Auth ──────────────────────────────────────────────────────────

export const login = (email: string, password: string) =>
  api.post<{ access_token: string }>("/auth/login", { email, password });

export const register = (email: string, password: string) =>
  api.post<{ access_token: string }>("/auth/register", { email, password });

export const updateProfile = (data: { fcm_token?: string | null; phone?: string | null }) =>
  api.patch("/auth/me", data);

export interface AuditRecord {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export const listAuditLog = (limit = 50) =>
  api.get<AuditRecord[]>("/audit", { params: { limit } });

// ── Query ─────────────────────────────────────────────────────────

export interface QueryResponse {
  answer: string;
  clips: string[];
  confidence: number;
  evidence: QueryEvidence[];
}

export interface QueryEvidence {
  event_id: string | null;
  timestamp: string | null;
  event_type: string | null;
  action_label: string | null;
  location_label: string | null;
  camera_name: string | null;
  confidence: number | null;
  person_label: string | null;
  object_label: string | null;
  object_category: string | null;
  from_camera_name: string | null;
  to_camera_name: string | null;
  clip_url: string | null;
}

export const askQuestion = (
  question: string,
  history: { role: string; content: string }[] = []
) =>
  api.post<QueryResponse>("/query", {
    question,
    conversation_history: history,
  });

// ── Events ────────────────────────────────────────────────────────

export interface OmniscientEvent {
  id: string;
  camera_id: string;
  camera_name: string;
  event_type: string;
  timestamp: string;
  action_label: string;
  location_label: string | null;
  confidence: number;
  clip_path: string | null;
  person_label: string | null;
  object_label: string | null;
  annotation: string | null;
}

export const listEvents = (params?: {
  limit?: number;
  event_type?: string;
  since?: string;
  search?: string;
}) => api.get<OmniscientEvent[]>("/events", { params });

export const redactEvent = (id: string) => api.delete(`/events/${id}`);
export const updateEventAnnotation = (id: string, note: string | null) =>
  api.patch<{ note: string | null; updated_at: string | null }>(`/events/${id}/annotation`, { note });

export interface Camera {
  id: string;
  name: string;
  protocol: string;
  location_label: string | null;
  is_active: boolean;
  status: "paused" | "starting" | "online" | "stale" | "error";
  last_frame_at: string | null;
  last_error_at: string | null;
  last_error_code: string | null;
  consecutive_failures: number;
  last_frame_width: number | null;
  last_frame_height: number | null;
  observed_fps: number | null;
  default_retention_days: number;
}

export const updateCamera = (id: string, is_active: boolean) =>
  api.patch<Camera>(`/cameras/${id}`, { is_active });

// ── WebSocket ─────────────────────────────────────────────────────

export interface EventStream {
  close: () => void;
}

export const openEventStream = async (
  onEvent: (e: OmniscientEvent) => void,
  onStatus?: (connected: boolean) => void,
): Promise<EventStream> => {
  const token = await SecureStore.getItemAsync("access_token");
  if (!token) throw new Error("not authenticated");
  const wsBase = BASE_URL.replace(/^http/, "ws");
  let ws: WebSocket | null = null;
  let closed = false;
  let retryMs = 1_000;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    if (closed) return;
    ws = new WebSocket(`${wsBase}/ws/events`, ["timekeeper-auth", token]);
    ws.onopen = () => {
      retryMs = 1_000;
      onStatus?.(true);
    };
    ws.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data) as OmniscientEvent);
      } catch {
        // Ignore malformed messages so one bad event does not kill the stream.
      }
    };
    ws.onerror = () => {};
    ws.onclose = (event) => {
      ws = null;
      onStatus?.(false);
      if (closed) return;
      if (event.code === 4001) {
        closed = true;
        void SecureStore.deleteItemAsync("access_token").finally(() => {
          _onUnauthorized?.();
        });
        return;
      }
      retryTimer = setTimeout(connect, retryMs);
      retryMs = Math.min(retryMs * 2, 30_000);
    };
  };

  connect();
  return {
    close: () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
      ws = null;
    },
  };
};
