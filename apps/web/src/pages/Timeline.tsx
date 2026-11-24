import { Fragment, useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { useSearchParams } from "react-router-dom";
import { ClipModal } from "../components/ClipModal";
import { countEvents, listCameras, listEvents, OmniscientEvent, redactEvent } from "../api/client";

const EVENT_TYPE_OPTIONS = [
  "person_entered",
  "person_exited",
  "person_detected",
  "object_placed",
  "object_picked_up",
  "object_last_seen",
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

function localDateTimeValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function csvCell(value: string | number | null): string {
  const text = value == null ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export function Timeline() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const eventType = searchParams.get("event_type") ?? "";
  const cameraId = searchParams.get("camera_id") ?? "";
  const sinceDate = searchParams.get("since") ?? "";
  const untilDate = searchParams.get("until") ?? "";
  const search = searchParams.get("search") ?? "";
  const [searchDraft, setSearchDraft] = useState("");
  const [selected, setSelected] = useState<OmniscientEvent | null>(null);
  const [redactError, setRedactError] = useState("");
  const [offset, setOffset] = useState(0);
  const PAGE = 50;
  const closeSelected = useCallback(() => setSelected(null), []);
  function handleAnnotationSaved(note: string | null) {
    setSelected((event) => event ? { ...event, annotation: note } : event);
    void queryClient.invalidateQueries({ queryKey: ["events", "timeline"] });
  }
  const redact = useMutation({
    mutationFn: redactEvent,
    onSuccess: async () => {
      setRedactError("");
      setSelected(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["events", "timeline"] }),
        queryClient.invalidateQueries({ queryKey: ["events", "timeline-count"] }),
      ]);
    },
    onError: () => setRedactError("couldn't redact that event; it was left unchanged"),
  });

  function confirmRedaction(event: OmniscientEvent) {
    if (redact.isPending) return;
    if (!window.confirm(`Permanently remove this ${event.action_label} event and its clip?`)) return;
    setRedactError("");
    redact.mutate(event.id);
  }

  useEffect(() => {
    setSearchDraft(search);
  }, [search]);

  function updateFilter(key: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
    setOffset(0);
  }

  function applySincePreset(preset: "today" | "24h" | "7d") {
    const date = new Date();
    if (preset === "today") {
      date.setHours(0, 0, 0, 0);
    } else {
      date.setHours(date.getHours() - (preset === "24h" ? 24 : 24 * 7));
    }
    updateFilter("since", localDateTimeValue(date));
  }

  const params: Record<string, unknown> = { limit: PAGE, offset };
  if (eventType) params.event_type = eventType;
  if (cameraId) params.camera_id = cameraId;
  if (sinceDate) params.since = new Date(sinceDate).toISOString();
  if (untilDate) params.until = new Date(untilDate).toISOString();
  if (search) params.search = search;
  const countParams: Record<string, unknown> = {};
  if (eventType) countParams.event_type = eventType;
  if (cameraId) countParams.camera_id = cameraId;
  if (sinceDate) countParams.since = new Date(sinceDate).toISOString();
  if (untilDate) countParams.until = new Date(untilDate).toISOString();
  if (search) countParams.search = search;

  const { data = [], isLoading, isError, refetch } = useQuery({
    queryKey: ["events", "timeline", eventType, cameraId, sinceDate, untilDate, search, offset],
    queryFn: () => listEvents(params).then((r) => r.data),
  });
  const {
    data: countData,
    isError: isCountError,
  } = useQuery({
    queryKey: ["events", "timeline-count", eventType, cameraId, sinceDate, untilDate, search],
    queryFn: () => countEvents(countParams).then((r) => r.data.count),
  });
  const { data: cameras = [] } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => listCameras().then((r) => r.data),
  });
  const total = countData ?? 0;
  const firstResult = data.length === 0 ? 0 : offset + 1;
  const lastResult = offset + data.length;
  const hasNextPage = isCountError
    ? data.length === PAGE
    : countData !== undefined && offset + data.length < total;
  useEffect(() => {
    function handlePagingShortcut(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (
        target?.isContentEditable
        || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(target?.tagName ?? "")
      ) {
        return;
      }
      if (event.key === "j" && hasNextPage) {
        event.preventDefault();
        setOffset((current) => current + PAGE);
      } else if (event.key === "k" && offset > 0) {
        event.preventDefault();
        setOffset((current) => Math.max(0, current - PAGE));
      }
    }
    window.addEventListener("keydown", handlePagingShortcut);
    return () => window.removeEventListener("keydown", handlePagingShortcut);
  }, [hasNextPage, offset]);
  const groupedEvents = data.reduce<Array<{ key: string; label: string; events: OmniscientEvent[] }>>(
    (groups, event) => {
      const date = new Date(event.timestamp);
      const key = Number.isNaN(date.getTime()) ? "unknown" : format(date, "yyyy-MM-dd-HH");
      const current = groups[groups.length - 1];
      if (current?.key === key) {
        current.events.push(event);
      } else {
        groups.push({
          key,
          label: Number.isNaN(date.getTime()) ? "unknown time" : format(date, "MMM d · HH:00"),
          events: [event],
        });
      }
      return groups;
    },
    [],
  );

  function reset() {
    setSearchDraft("");
    setSearchParams(new URLSearchParams());
    setOffset(0);
  }

  function exportVisiblePage() {
    if (!data.length) return;
    const headers = [
      "timestamp",
      "camera",
      "event_type",
      "action",
      "location",
      "person",
      "item",
      "annotation",
      "confidence",
      "clip_path",
    ];
    const rows = data.map((event) => [
      event.timestamp,
      event.camera_name,
      event.event_type,
      event.action_label,
      event.location_label,
      event.person_label,
      event.object_label,
      event.annotation,
      `${Math.round(event.confidence * 100)}%`,
      event.clip_path,
    ]);
    const csv = [headers, ...rows]
      .map((row) => row.map((value) => csvCell(value)).join(","))
      .join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `timekeeper-timeline-page-${Math.floor(offset / PAGE) + 1}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
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
        {redactError && (
          <div role="alert" style={{ color: "var(--accent)", fontSize: 11 }}>
            {redactError}
          </div>
        )}
        <div>
          <div className="label" style={{ marginBottom: 4 }}>
            search evidence
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              updateFilter("search", searchDraft.trim());
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
              updateFilter("event_type", e.target.value);
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
            camera source
          </div>
          <select
            aria-label="Filter by camera source"
            value={cameraId}
            onChange={(e) => updateFilter("camera_id", e.target.value)}
            style={{
              padding: "5px 10px",
              background: "var(--elevated)",
              color: "var(--text)",
              border: "1px solid var(--border-hi)",
              fontSize: 12,
              minWidth: 180,
            }}
          >
            <option value="">all cameras</option>
            {cameras.map((camera) => (
              <option key={camera.id} value={camera.id}>{camera.name}</option>
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
              updateFilter("since", e.target.value);
            }}
            style={{
              padding: "5px 10px",
              background: "var(--elevated)",
              color: "var(--text)",
              border: "1px solid var(--border-hi)",
              fontSize: 12,
            }}
          />
          <div
            style={{ display: "flex", gap: 4, marginTop: 4 }}
            role="group"
            aria-label="Quick timeline ranges"
          >
            {(["today", "24h", "7d"] as const).map((preset) => (
              <button
                key={preset}
                className="btn btn-ghost"
                type="button"
                onClick={() => applySincePreset(preset)}
                style={{ padding: "2px 6px", fontSize: 10 }}
              >
                {preset}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="label" style={{ marginBottom: 4 }}>
            until
          </div>
          <input
            aria-label="Show events until"
            type="datetime-local"
            value={untilDate}
            onChange={(e) => updateFilter("until", e.target.value)}
            style={{
              padding: "5px 10px",
              background: "var(--elevated)",
              color: "var(--text)",
              border: "1px solid var(--border-hi)",
              fontSize: 12,
            }}
          />
        </div>

        {(eventType || cameraId || sinceDate || untilDate || search) && (
          <button
            className="btn btn-ghost"
            style={{ marginBottom: 1 }}
            onClick={reset}
          >
            clear
          </button>
        )}

        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          <button
            className="btn btn-ghost"
            type="button"
            onClick={exportVisiblePage}
            disabled={!data.length || isLoading}
            aria-label="Export visible timeline results as CSV"
            style={{ padding: "4px 9px" }}
          >
            export page
          </button>
          <span
            style={{ fontSize: 11, color: "var(--text-dim)", alignSelf: "center" }}
          >
            {countData === undefined
              ? isCountError
                ? "results unavailable"
                : "loading results…"
              : `${countData} results`}
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
                {["timestamp", "camera", "event", "location", "person", "item", "conf", "clip"].map(
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
              {groupedEvents.map((group) => (
                <Fragment key={group.key}>
                  <tr
                    aria-label={`${group.label}, ${group.events.length} events`}
                    style={{ background: "var(--surface)" }}
                  >
                    <th
                      colSpan={8}
                      scope="rowgroup"
                      style={{
                        padding: "6px 12px",
                        color: "var(--text-dim)",
                        fontSize: 10,
                        fontWeight: "normal",
                        letterSpacing: "0.08em",
                        textAlign: "left",
                        textTransform: "uppercase",
                      }}
                    >
                      {group.label} · {group.events.length} {group.events.length === 1 ? "event" : "events"}
                    </th>
                  </tr>
                  {group.events.map((e) => (
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
                      <td style={{ padding: "8px 12px", color: "var(--text-dim)" }}>
                        {e.camera_name}
                      </td>
                      <td style={{ padding: "8px 12px", color: "var(--text)" }}>
                        {e.action_label}
                        {e.annotation && (
                          <span
                            title="has operator note"
                            aria-label="has operator note"
                            style={{ marginLeft: 6, color: "var(--amber)", fontSize: 10 }}
                          >
                            ✎
                          </span>
                        )}
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
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
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
                          <button
                            className="btn btn-ghost"
                            style={{ padding: "2px 5px", fontSize: 9 }}
                            aria-label={`Redact ${e.action_label} event`}
                            onClick={(event) => {
                              event.stopPropagation();
                              confirmRedaction(e);
                            }}
                            disabled={redact.isPending}
                          >
                            {redact.isPending && redact.variables === e.id ? "..." : "redact"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </Fragment>
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
          {firstResult}–{lastResult}
        </span>
        <span
          aria-label="Timeline keyboard shortcuts"
          style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-dim)" }}
        >
          j/k pages
        </span>
        <button
          className="btn btn-ghost"
          disabled={!hasNextPage}
          onClick={() => setOffset(offset + PAGE)}
          style={{ padding: "4px 12px" }}
        >
          next →
        </button>
      </div>

      {selected && (
        <ClipModal
          event={selected}
          onClose={closeSelected}
          onAnnotationSaved={handleAnnotationSaved}
        />
      )}
    </div>
  );
}
