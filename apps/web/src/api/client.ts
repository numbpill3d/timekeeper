import axios from "axios";

// Relative API URLs keep the dashboard working when it is opened through a
// LAN hostname, 127.0.0.1, HTTPS, or the Vite development proxy.
const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

export const api = axios.create({ baseURL: BASE_URL, timeout: 15_000 });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// handle 401s globally — clear token and reload
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.reload();
    }
    return Promise.reject(err);
  }
);

// ── Types ─────────────────────────────────────────────────────────

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

export interface QueryResponse {
  answer: string;
  clips: string[];
  confidence: number;
}

export interface Camera {
  id: string;
  name: string;
  stream_url: string;
  protocol: string;
  location_label: string | null;
  is_edge_only: boolean;
  is_active: boolean;
  provider_config: Record<string, unknown>;
}

export interface Person {
  id: string;
  label: string;
  is_known: boolean;
  appearance_tags: string[];
  retention_days: number;
  last_seen_at: string | null;
  created_at: string;
  event_count: number;
}

export interface AlertRule {
  id: string;
  name: string;
  rule_text: string;
  priority: "critical" | "important" | "informational";
  channels: string[];
  is_active: boolean;
  created_at: string;
}

export interface UserProfile {
  user_id: string;
  email: string;
  tier: string;
  fcm_token: string | null;
  phone: string | null;
  created_at: string;
}

// ── Auth ──────────────────────────────────────────────────────────

export const login = (email: string, password: string) =>
  api.post<{ access_token: string }>("/auth/login", { email, password });

export const register = (email: string, password: string) =>
  api.post<{ access_token: string }>("/auth/register", { email, password });

export const getProfile = () => api.get<UserProfile>("/auth/me");

export const updateProfile = (data: { fcm_token?: string; phone?: string }) =>
  api.patch<UserProfile>("/auth/me", data);

// ── Events ────────────────────────────────────────────────────────

export const listEvents = (params?: Record<string, unknown>) =>
  api.get<OmniscientEvent[]>("/events", { params });

export const getEvent = (id: string) =>
  api.get<OmniscientEvent>(`/events/${id}`);

// ── Query ─────────────────────────────────────────────────────────

export const askQuestion = (
  question: string,
  history: { role: string; content: string }[] = []
) =>
  api.post<QueryResponse>("/query", {
    question,
    conversation_history: history,
  });

// ── Cameras ───────────────────────────────────────────────────────

export const listCameras = () => api.get<Camera[]>("/cameras");

export const addCamera = (data: {
  name: string;
  stream_url: string;
  protocol?: string;
  location_label?: string;
  is_edge_only?: boolean;
  provider_config?: Record<string, unknown>;
}) => api.post<Camera>("/cameras", data);

export const deleteCamera = (id: string) => api.delete(`/cameras/${id}`);

// ── Persons ───────────────────────────────────────────────────────

export const listPersons = () => api.get<Person[]>("/persons");

export const updatePerson = (
  id: string,
  data: { label?: string; is_known?: boolean }
) => api.patch<Person>(`/persons/${id}`, data);

export const deletePerson = (id: string) => api.delete(`/persons/${id}`);

// ── Alerts ────────────────────────────────────────────────────────

export const listAlerts = () => api.get<AlertRule[]>("/alerts");

export const createAlert = (data: {
  name: string;
  rule_text: string;
  priority?: string;
  channels?: string[];
}) => api.post<AlertRule>("/alerts", data);

export const toggleAlert = (id: string, is_active: boolean) =>
  api.patch<AlertRule>(`/alerts/${id}`, { is_active });

export const deleteAlert = (id: string) => api.delete(`/alerts/${id}`);

// ── WebSocket live stream ─────────────────────────────────────────

export interface EventStream {
  close: () => void;
}

export const openEventStream = (
  onEvent: (e: OmniscientEvent) => void,
  onStatus?: (connected: boolean) => void,
): EventStream => {
  const token = localStorage.getItem("access_token");
  const wsBase = BASE_URL.startsWith("http")
    ? BASE_URL.replace(/^http/, "ws")
    : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${BASE_URL}`;
  let ws: WebSocket | null = null;
  let closed = false;
  let retryMs = 1_000;

  const connect = () => {
    if (closed) return;
    if (!token) return;
    // Keep the JWT out of the URL so reverse-proxy/access logs cannot retain it.
    ws = new WebSocket(`${wsBase}/ws/events`, ["timekeeper-auth", token]);
    ws.onopen = () => {
      retryMs = 1_000;
      onStatus?.(true);
    };
    ws.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data) as OmniscientEvent);
      } catch {
        // Ignore malformed messages; the connection can continue serving
        // subsequent events without taking down the dashboard.
      }
    };
    ws.onerror = () => {};
    ws.onclose = () => {
      onStatus?.(false);
      if (!closed) {
        setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, 30_000);
      }
    };
  };

  connect();
  return { close: () => { closed = true; ws?.close(); } };
};
