import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { ChatPanel } from "../components/ChatPanel";
import { ClipModal } from "../components/ClipModal";
import {
  listEvents,
  listCameras,
  OmniscientEvent,
  EventStream,
  openEventStream,
} from "../api/client";

const EVENT_COLORS: Record<string, string> = {
  person_entered:     "var(--green)",
  person_exited:      "var(--text-dim)",
  package_delivered:  "var(--amber)",
  intrusion_detected: "var(--accent)",
  unknown_person:     "var(--accent)",
  object_moved:       "#4488ff",
  object_placed:      "#444",
  object_picked_up:   "#444",
};

export function Dashboard() {
  const [live, setLive] = useState<OmniscientEvent[]>([]);
  const [selected, setSelected] = useState<OmniscientEvent | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<EventStream | null>(null);

  const { data: recent = [] } = useQuery({
    queryKey: ["events", "dashboard"],
    queryFn: () => listEvents({ limit: 12 }).then((r) => r.data),
    refetchInterval: 30_000,
  });

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const { data: todayEvents = [] } = useQuery({
    queryKey: ["events", "today"],
    queryFn: () => listEvents({ limit: 1000, since: today.toISOString() }).then((r) => r.data),
    refetchInterval: 30_000,
  });

  const { data: cameras = [] } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => listCameras().then((r) => r.data),
    refetchInterval: 60_000,
  });

  useEffect(() => {
    const stream = openEventStream(
      (e) => setLive((p) => [e, ...p].slice(0, 20)),
      (connected) => setWsConnected(connected),
    );
    wsRef.current = stream;
    return () => stream.close();
  }, []);

  const events = [...live, ...recent].slice(0, 14);
  const now = new Date();
  const todayCount = todayEvents.length;
  const activeCams = cameras.filter((c) => c.is_active).length;
  const alertCount = events.filter((e) =>
    ["intrusion_detected", "unknown_person"].includes(e.event_type)
  ).length;

  const dateLabel = new Intl.DateTimeFormat(undefined, {
    weekday: "long", month: "long", day: "numeric",
  }).format(now);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      <header className="dashboard-head">
        <div>
          <div className="dashboard-kicker">situational awareness / 01</div>
          <h1 className="dashboard-title">Good evening.</h1>
        </div>
        <div className="dashboard-date">{dateLabel}<br />local system time</div>
      </header>

      <div className="metric-strip">
        <div className="metric"><div className="label">events today</div><div className="metric-value">{todayCount}</div><div className="metric-note">recent detections</div></div>
        <div className="metric"><div className="label">cameras online</div><div className="metric-value">{activeCams}<span style={{ color: "var(--text-dim)", fontSize: 15 }}> / {cameras.length}</span></div><div className="metric-note">{activeCams < cameras.length ? "some offline" : "all nominal"}</div></div>
        <div className="metric"><div className="label">active alerts</div><div className="metric-value" style={{ color: alertCount ? "var(--accent)" : "var(--text-bright)" }}>{alertCount}</div><div className="metric-note">{alertCount ? "requires attention" : "clear"}</div></div>
        <div className="metric"><div className="label">event stream</div><div className="metric-value" style={{ color: wsConnected ? "var(--green)" : "var(--amber)", fontSize: 18, paddingTop: 4 }}>{wsConnected ? "LIVE" : "WAITING"}</div><div className="metric-note">{wsConnected ? "receiving now" : "reconnecting"}</div></div>
      </div>

      <div className="dashboard-grid">
        <div className="feed-panel">
          <div className="panel-heading">
            <span aria-hidden="true" style={{ color: "var(--accent)", fontSize: 9 }}>◆</span>
            <span className="section-title">live activity</span>
            {live.length > 0 && (
              <span className="badge badge-green" style={{ marginLeft: "auto" }}>
                {live.length} new
              </span>
            )}
          </div>

          <div className="activity-list">
            {events.length === 0 ? (
              <div className="empty-state">No activity yet. Connect a camera to begin monitoring your home.</div>
            ) : (
              events.map((e) => (
                <div
                  key={e.id}
                  onClick={() => e.clip_path && setSelected(e)}
                  className={`activity-row${e.clip_path ? " has-clip" : ""}`}
                >
                  <span className="event-marker" style={{ background: EVENT_COLORS[e.event_type] ?? "var(--text-dim)" }} />
                  <div className="event-copy">
                    <div className="event-title">{e.action_label}</div>
                    <div className="event-meta">
                      {e.location_label && <span>{e.location_label}</span>}
                      {e.person_label && <span style={{ color: "var(--accent)" }}>{e.person_label}</span>}
                      {e.clip_path && <span>▸ clip</span>}
                    </div>
                  </div>
                  <span className="event-time">
                    {formatDistanceToNow(new Date(e.timestamp), {
                      addSuffix: true,
                    })}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        <div style={{ minWidth: 0 }}>
          <ChatPanel />
        </div>
      </div>

      {selected && (
        <ClipModal event={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
