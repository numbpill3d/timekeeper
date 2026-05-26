import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { ChatPanel } from "../components/ChatPanel";
import { ClipModal } from "../components/ClipModal";
import {
  listEvents,
  listCameras,
  OmniscientEvent,
  openEventStream,
} from "../api/client";

function StatBox({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div
      style={{
        flex: 1,
        padding: "14px 18px",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        gap: 4,
      }}
    >
      <div className="label">{label}</div>
      <div
        className="mono-stat"
        style={{ color: accent ? "var(--accent)" : "var(--text-bright)" }}
      >
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 1 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

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
  const wsRef = useRef<WebSocket | null>(null);

  const { data: recent = [] } = useQuery({
    queryKey: ["events", "dashboard"],
    queryFn: () => listEvents({ limit: 12 }).then((r) => r.data),
    refetchInterval: 30_000,
  });

  const { data: cameras = [] } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => listCameras().then((r) => r.data),
    refetchInterval: 60_000,
  });

  useEffect(() => {
    const ws = openEventStream((e) =>
      setLive((p) => [e, ...p].slice(0, 20))
    );
    ws.onerror = () => {};
    wsRef.current = ws;
    return () => ws.close();
  }, []);

  const events = [...live, ...recent].slice(0, 14);
  const now = new Date();
  const todayCount = events.filter(
    (e) => new Date(e.timestamp).toDateString() === now.toDateString()
  ).length;
  const activeCams = cameras.filter((c) => c.is_active).length;
  const alertCount = events.filter((e) =>
    ["intrusion_detected", "unknown_person"].includes(e.event_type)
  ).length;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Stats bar */}
      <div
        style={{
          borderBottom: "1px solid var(--border)",
          display: "flex",
          flexShrink: 0,
        }}
      >
        <StatBox label="events today" value={todayCount} />
        <StatBox
          label="cameras online"
          value={`${activeCams} / ${cameras.length}`}
          sub={activeCams < cameras.length ? "some offline" : "all nominal"}
        />
        <StatBox
          label="active alerts"
          value={alertCount}
          accent={alertCount > 0}
          sub={alertCount > 0 ? "requires attention" : "clear"}
        />
        <div
          style={{
            flex: 1,
            padding: "14px 18px",
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <div className="label">feed status</div>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span
              style={{
                width: 6,
                height: 6,
                background: "var(--green)",
                display: "inline-block",
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontSize: 11,
                color: "var(--green)",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              streaming
            </span>
          </div>
        </div>
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Activity feed */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "9px 20px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexShrink: 0,
            }}
          >
            <span style={{ color: "var(--accent)", fontSize: 9 }}>◆</span>
            <span className="section-title">live activity</span>
            {live.length > 0 && (
              <span className="badge badge-green" style={{ marginLeft: "auto" }}>
                {live.length} new
              </span>
            )}
          </div>

          <div style={{ flex: 1, overflowY: "auto" }}>
            {events.length === 0 ? (
              <div
                style={{
                  padding: "40px 20px",
                  color: "var(--text-dim)",
                  fontSize: 12,
                }}
              >
                no events. add a camera to begin monitoring.
              </div>
            ) : (
              events.map((e) => (
                <div
                  key={e.id}
                  onClick={() => e.clip_path && setSelected(e)}
                  style={{
                    padding: "9px 20px",
                    borderBottom: "1px solid var(--border)",
                    display: "flex",
                    gap: 10,
                    alignItems: "flex-start",
                    cursor: e.clip_path ? "pointer" : "default",
                    transition: "background 0.08s",
                  }}
                  onMouseEnter={(ev) => {
                    if (e.clip_path)
                      (ev.currentTarget as HTMLElement).style.background =
                        "var(--elevated)";
                  }}
                  onMouseLeave={(ev) => {
                    (ev.currentTarget as HTMLElement).style.background =
                      "transparent";
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      background:
                        EVENT_COLORS[e.event_type] ?? "var(--text-dim)",
                      flexShrink: 0,
                      marginTop: 5,
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 12,
                        color: "var(--text)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {e.action_label}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "var(--text-dim)",
                        marginTop: 1,
                        display: "flex",
                        gap: 8,
                      }}
                    >
                      {e.location_label && <span>{e.location_label}</span>}
                      {e.person_label && (
                        <span style={{ color: "var(--accent)" }}>
                          {e.person_label}
                        </span>
                      )}
                      {e.clip_path && <span>▸ clip</span>}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: 10,
                      color: "var(--text-dim)",
                      flexShrink: 0,
                      paddingTop: 1,
                    }}
                  >
                    {formatDistanceToNow(new Date(e.timestamp), {
                      addSuffix: true,
                    })}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Chat */}
        <div style={{ width: 360, flexShrink: 0 }}>
          <ChatPanel />
        </div>
      </div>

      {selected && (
        <ClipModal event={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
