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
    const requestUrl = String(err.config?.url ?? "");
    const isAuthRequest = /\/auth\/(login|register)(?:$|\?)/.test(requestUrl);
    if (err.response?.status === 401 && !isAuthRequest) {
      localStorage.removeItem("access_token");
      window.location.reload();
    }
    return Promise.reject(err);
  }
);

// ── Types ─────────────────────────────────────────────────────────

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
  camera_id: string | null;
  camera_name: string | null;
  confidence: number | null;
  person_label: string | null;
  object_label: string | null;
  object_category: string | null;
  from_camera_name: string | null;
  to_camera_name: string | null;
  clip_url: string | null;
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
  status: "paused" | "starting" | "online" | "stale" | "error";
  last_frame_at: string | null;
  last_error_at: string | null;
  last_error_code: string | null;
  consecutive_failures: number;
  last_frame_width: number | null;
  last_frame_height: number | null;
  observed_fps: number | null;
  retention_days: number;
  default_retention_days: number;
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

export interface AuditRecord {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface RetentionPreview {
  camera_id: string;
  camera_name: string;
  events_expiring: number;
  detections_expiring: number;
  oldest_event_at: string | null;
}

export const getRetentionPreview = () =>
  api.get<RetentionPreview[]>("/retention/preview");

// ── Auth ──────────────────────────────────────────────────────────

export const login = (email: string, password: string) =>
  api.post<{ access_token: string }>("/auth/login", { email, password });

export const register = (email: string, password: string) =>
  api.post<{ access_token: string }>("/auth/register", { email, password });

export const getProfile = () => api.get<UserProfile>("/auth/me");

export const listAuditLog = (limit = 50) =>
  api.get<AuditRecord[]>("/audit", { params: { limit } });

export const getHealth = () =>
  api.get<{ status: string; database: string; redis: string }>("/health");

export const updateProfile = (data: { fcm_token?: string | null; phone?: string | null }) =>
  api.patch<UserProfile>("/auth/me", data);

// ── Integrations ─────────────────────────────────────────────────

export interface PipedreamConnectToken {
  connect_link_url: string;
  expires_at: string | null;
}

export const createPipedreamConnectToken = () =>
  api.post<PipedreamConnectToken>("/integrations/pipedream/connect-token");

// ── Events ────────────────────────────────────────────────────────

export const listEvents = (params?: Record<string, unknown>) =>
  api.get<OmniscientEvent[]>("/events", { params });

export const countEvents = (params?: Record<string, unknown>) =>
  api.get<{ count: number }>("/events/count", { params });

export const getEvent = (id: string) =>
  api.get<OmniscientEvent>(`/events/${id}`);

export const redactEvent = (id: string) => api.delete(`/events/${id}`);
export const updateEventAnnotation = (id: string, note: string | null) =>
  api.patch<{ note: string | null; updated_at: string | null }>(`/events/${id}/annotation`, { note });

// ── Query ─────────────────────────────────────────────────────────

export const askQuestion = (
  question: string,
  history: { role: string; content: string }[] = []
) =>
  api.post<QueryResponse>("/query", {
    question,
    conversation_history: history,
  });

export function describeQueryError(error: unknown): string {
  if (!axios.isAxiosError(error)) {
    return "query unavailable — check that the API and query engine are running.";
  }
  const detail = error.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (error.response?.status === 429) return "query limit reached — try again next month or upgrade your plan.";
  if (error.response?.status === 504) return "query timed out — try a narrower time range or question.";
  if (error.response?.status && error.response.status >= 500) return "query engine unavailable — check the local services and retry.";
  return "query unavailable — check the API and query engine are running.";
}

// ── Cameras ───────────────────────────────────────────────────────

export const listCameras = () => api.get<Camera[]>("/cameras");

export const addCamera = (data: {
  name: string;
  stream_url: string;
  protocol?: string;
  location_label?: string;
  provider_config?: Record<string, unknown>;
  retention_days?: number;
}) => api.post<Camera>("/cameras", data);

export const updateCamera = (
  id: string,
  data: {
    name?: string;
    stream_url?: string;
    protocol?: string;
    location_label?: string | null;
    is_active?: boolean;
    provider_config?: Record<string, unknown>;
    retention_days?: number;
  },
) => api.patch<Camera>(`/cameras/${id}`, data);

export const deleteCamera = (id: string) => api.delete(`/cameras/${id}`);

// ── Persons ───────────────────────────────────────────────────────

export const listPersons = () => api.get<Person[]>("/persons");

export const updatePerson = (
  id: string,
  data: { label?: string; is_known?: boolean; retention_days?: number }
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
  let retryTimer: number | null = null;

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
    ws.onclose = (event) => {
      onStatus?.(false);
      if (event.code === 4001) {
        localStorage.removeItem("access_token");
        window.location.reload();
        return;
      }
      if (!closed) {
        retryTimer = window.setTimeout(() => {
          retryTimer = null;
          connect();
        }, retryMs);
        retryMs = Math.min(retryMs * 2, 30_000);
      }
    };
  };

  connect();
  return {
    close: () => {
      closed = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      retryTimer = null;
      ws?.close();
    },
  };
};
