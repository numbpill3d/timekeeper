import axios from "axios";
import * as SecureStore from "expo-secure-store";

const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

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

export const updateProfile = (data: { fcm_token?: string; phone?: string }) =>
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

export const openEventStream = async (
  onEvent: (e: OmniscientEvent) => void
): Promise<WebSocket> => {
  const token = await SecureStore.getItemAsync("access_token");
  const wsBase = BASE_URL.replace(/^http/, "ws");
  const ws = new WebSocket(`${wsBase}/ws/events?token=${token}`);
  ws.onmessage = (msg) => onEvent(JSON.parse(msg.data));
  return ws;
};
