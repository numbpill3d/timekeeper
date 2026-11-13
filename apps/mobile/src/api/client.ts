import axios from "axios";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL ??
  // Android's emulator maps the host machine to 10.0.2.2. Physical devices
  // must set EXPO_PUBLIC_API_URL to a LAN-reachable URL.
  (Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://localhost:8000");

export const api = axios.create({ baseURL: BASE_URL });

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
    if (err.response?.status === 401) {
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

// ── Query ─────────────────────────────────────────────────────────

export interface QueryResponse {
  answer: string;
  clips: string[];
  confidence: number;
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
  event_type: string;
  timestamp: string;
  action_label: string;
  location_label: string | null;
  confidence: number;
  clip_path: string | null;
  person_label: string | null;
  object_label: string | null;
}

export const listEvents = (params?: {
  limit?: number;
  event_type?: string;
  since?: string;
}) => api.get<OmniscientEvent[]>("/events", { params });

// ── WebSocket ─────────────────────────────────────────────────────

export interface EventStream {
  close: () => void;
}

export const openEventStream = async (
  onEvent: (e: OmniscientEvent) => void
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
