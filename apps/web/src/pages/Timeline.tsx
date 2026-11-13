import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { ClipModal } from "../components/ClipModal";
import { listEvents, OmniscientEvent } from "../api/client";

const EVENT_TYPE_OPTIONS = [
  "person_entered",
  "person_exited",
  "person_detected",
  "object_placed",
  "object_picked_up",
  "object_moved",
  "door_opened",
  "door_closed",
  "package_delivered",
  "intrusion_detected",
  "unknown_person",
  "fall_detected",
];

const CONF_COLOR = (c: number) => {
  if (c >= 0.9) return "var(--green)";
  if (c >= 0.7) return "var(--amber)";
  return "var(--accent)";
};

export function Timeline() {
  const [eventType, setEventType] = useState("");
  const [sinceDate, setSinceDate] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<OmniscientEvent | null>(null);
  const [offset, setOffset] = useState(0);
  const PAGE = 50;
  const closeSelected = useCallback(() => setSelected(null), []);

  const params: Record<string, unknown> = { limit: PAGE, offset };
  if (eventType) params.event_type = eventType;
  if (sinceDate) params.since = new Date(sinceDate).toISOString();
  if (search) params.search = search;

  const { data = [], isLoading, isError, refetch } = useQuery({
    queryKey: ["events", "timeline", eventType, sinceDate, search, offset],
    queryFn: () => listEvents(params).then((r) => r.data),
  });

  function reset() {
    setEventType("");
    setSinceDate("");
    setSearchDraft("");
    setSearch("");
    setOffset(0);
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Header + filters */}
      <div
        style={{
          padding: "12px 20px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          gap: 10,
          alignItems: "flex-end",
          flexShrink: 0,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div className="label" style={{ marginBottom: 4 }}>
            search evidence
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchDraft.trim());
              setOffset(0);
            }}
            style={{ display: "flex", gap: 4 }}
          >
            <input
              aria-label="Search event evidence"
              value={searchDraft}
              maxLength={120}
              onChange={(event) => setSearchDraft(event.target.value)}
              placeholder="person, item, location"
              style={{
                width: 180,
                padding: "5px 10px",
                background: "var(--elevated)",
                color: "var(--text)",
                border: "1px solid var(--border-hi)",
                fontSize: 12,
              }}
            />
            <button className="btn btn-ghost" type="submit" style={{ padding: "4px 9px" }}>
              find
            </button>
          </form>
        </div>

        <div>
          <div className="label" style={{ marginBottom: 4 }}>
            event type
          </div>
          <select
            aria-label="Filter by event type"
            value={eventType}
            onChange={(e) => {
              setEventType(e.target.value);
              setOffset(0);
            }}
            style={{
              padding: "5px 10px",
              background: "var(--elevated)",
              color: "var(--text)",
              border: "1px solid var(--border-hi)",
              fontSize: 12,
              minWidth: 160,
            }}
          >
            <option value="">all types</option>
            {EVENT_TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        <div>
          <div className="label" style={{ marginBottom: 4 }}>
            since
          </div>
          <input
            aria-label="Show events since"
            type="datetime-local"
            value={sinceDate}
            onChange={(e) => {
              setSinceDate(e.target.value);
              setOffset(0);
            }}
            style={{
              padding: "5px 10px",
              background: "var(--elevated)",
              color: "var(--text)",
              border: "1px solid var(--border-hi)",
              fontSize: 12,
            }}
          />
        </div>

        {(eventType || sinceDate || search) && (
          <button
            className="btn btn-ghost"
            style={{ marginBottom: 1 }}
            onClick={reset}
          >
            clear
          </button>
        )}

        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          <span
            style={{ fontSize: 11, color: "var(--text-dim)", alignSelf: "center" }}
          >
            {data.length} results
          </span>
        </div>
      </div>

      {/* Table */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          <div
            style={{ padding: "32px 20px", color: "var(--text-dim)", fontSize: 12 }}
          >
            loading...
          </div>
        ) : (
          isError ? (
          <div
            role="alert"
            style={{
              padding: "32px 20px",
              color: "var(--accent-hi)",
              fontSize: 12,
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <span>couldn't load the timeline.</span>
            <button className="btn btn-ghost" onClick={() => void refetch()}>
              retry
            </button>
          </div>
        ) : (
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: 12,
            }}
          >
            <thead>
              <tr
                style={{
                  position: "sticky",
                  top: 0,
                  background: "var(--bg)",
                  zIndex: 1,
                  borderBottom: "1px solid var(--border-hi)",
                }}
              >
                {["timestamp", "event", "location", "person", "item", "conf", "clip"].map(
                  (h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: "left",
                        padding: "8px 12px",
                        fontSize: 10,
                        color: "var(--text-dim)",
                        textTransform: "uppercase",
                        letterSpacing: "0.12em",
                        fontWeight: "normal",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {data.map((e) => (
                <tr
                  key={e.id}
                  onClick={() => e.clip_path && setSelected(e)}
                  tabIndex={e.clip_path ? 0 : undefined}
                  onKeyDown={(event) => {
                    if (e.clip_path && (event.key === "Enter" || event.key === " ")) {
                      event.preventDefault();
                      setSelected(e);
                    }
                  }}
                  aria-label={e.clip_path ? `View evidence for ${e.action_label}` : undefined}
                  style={{
                    borderBottom: "1px solid var(--border)",
                    cursor: e.clip_path ? "pointer" : "default",
                    transition: "background 0.08s",
                  }}
                  onMouseEnter={(ev) =>
                    ((ev.currentTarget as HTMLElement).style.background =
                      "var(--surface)")
                  }
                  onMouseLeave={(ev) =>
                    ((ev.currentTarget as HTMLElement).style.background =
                      "transparent")
                  }
                >
                  <td
                    style={{
                      padding: "8px 12px",
                      color: "var(--text-dim)",
                      whiteSpace: "nowrap",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {format(new Date(e.timestamp), "MMM d HH:mm:ss")}
                  </td>
                  <td style={{ padding: "8px 12px", color: "var(--text)" }}>
                    {e.action_label}
                  </td>
                  <td
                    style={{
                      padding: "8px 12px",
                      color: "var(--text-dim)",
                    }}
                  >
                    {e.location_label ?? "—"}
                  </td>
                  <td
                    style={{
                      padding: "8px 12px",
                      color: e.person_label ? "var(--accent)" : "var(--text-dim)",
                    }}
                  >
                    {e.person_label ?? "—"}
                  </td>
                  <td
                    style={{
                      padding: "8px 12px",
                      color: e.object_label ? "var(--amber)" : "var(--text-dim)",
                    }}
                  >
                    {e.object_label ?? "—"}
                  </td>
                  <td
                    style={{
                      padding: "8px 12px",
                      color: CONF_COLOR(e.confidence),
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {Math.round(e.confidence * 100)}%
                  </td>
                  <td style={{ padding: "8px 12px" }}>
                    {e.clip_path && (
                      <span
                        style={{
                          fontSize: 10,
                          color: "var(--accent)",
                          textTransform: "uppercase",
                          letterSpacing: "0.08em",
                        }}
                      >
                        ▸ view
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
        )}
      </div>

      {/* Pagination */}
      <div
        style={{
          borderTop: "1px solid var(--border)",
          padding: "8px 16px",
          display: "flex",
          gap: 8,
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <button
          className="btn btn-ghost"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE))}
          style={{ padding: "4px 12px" }}
        >
          ← prev
        </button>
        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
          {offset}–{offset + data.length}
        </span>
        <button
          className="btn btn-ghost"
          disabled={data.length < PAGE}
          onClick={() => setOffset(offset + PAGE)}
          style={{ padding: "4px 12px" }}
        >
          next →
        </button>
      </div>

      {selected && (
        <ClipModal event={selected} onClose={closeSelected} />
      )}
    </div>
  );
}
