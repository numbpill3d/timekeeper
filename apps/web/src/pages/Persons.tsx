import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { listPersons, updatePerson, deletePerson, Person } from "../api/client";

function PersonAvatar({ label, isKnown }: { label: string; isKnown: boolean }) {
  const initials = label
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div
      style={{
        width: 44,
        height: 44,
        border: `1px solid ${isKnown ? "var(--accent)" : "var(--border-hi)"}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 13,
        fontWeight: "bold",
        color: isKnown ? "var(--accent)" : "var(--text-dim)",
        flexShrink: 0,
        background: "var(--elevated)",
        letterSpacing: "0.05em",
      }}
    >
      {initials || "?"}
    </div>
  );
}

function PersonCard({ person }: { person: Person }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(person.label);
  const [confirming, setConfirming] = useState(false);

  const update = useMutation({
    mutationFn: (data: { label?: string; is_known?: boolean }) =>
      updatePerson(person.id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["persons"] }),
  });

  const remove = useMutation({
    mutationFn: () => deletePerson(person.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["persons"] }),
  });

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
        <PersonAvatar label={person.label} isKnown={person.is_known} />
        <div style={{ flex: 1, minWidth: 0 }}>
          {editing ? (
            <input
              aria-label={`Edit label for ${person.label}`}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  update.mutate({ label });
                  setEditing(false);
                }
                if (e.key === "Escape") {
                  setLabel(person.label);
                  setEditing(false);
                }
              }}
              autoFocus
              style={{
                width: "100%",
                padding: "4px 8px",
                fontSize: 13,
                background: "var(--elevated)",
                border: "1px solid var(--accent)",
                color: "var(--text)",
              }}
            />
          ) : (
            <div
              style={{
                fontSize: 13,
                color: "var(--text-bright)",
                fontWeight: "bold",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {person.label}
            </div>
          )}
          <div
            style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 3 }}
          >
            {person.last_seen_at
              ? formatDistanceToNow(new Date(person.last_seen_at), {
                  addSuffix: true,
                })
              : "never seen"}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-end" }}>
          <span
            className={`badge ${person.is_known ? "badge-green" : "badge-amber"}`}
          >
            {person.is_known ? "known" : "unknown"}
          </span>
          <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
            {person.event_count} events
          </span>
        </div>
      </div>

      {person.appearance_tags && person.appearance_tags.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {person.appearance_tags.map((t) => (
            <span key={t} className="badge badge-dim">
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div
        style={{
          borderTop: "1px solid var(--border)",
          paddingTop: 10,
          display: "flex",
          gap: 6,
          flexWrap: "wrap",
        }}
      >
        {confirming ? (
          <>
            <span
              style={{
                fontSize: 11,
                color: "var(--accent)",
                flex: 1,
                alignSelf: "center",
              }}
            >
              delete this person?
            </span>
            <button
              className="btn btn-danger"
              style={{ padding: "4px 10px" }}
              onClick={() => remove.mutate()}
            >
              delete
            </button>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={() => setConfirming(false)}
            >
              cancel
            </button>
          </>
        ) : (
          <>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={() => setEditing(!editing)}
            >
              {editing ? "cancel" : "rename"}
            </button>
            {editing && (
              <button
                className="btn btn-primary"
                style={{ padding: "4px 10px" }}
                onClick={() => {
                  update.mutate({ label });
                  setEditing(false);
                }}
              >
                save
              </button>
            )}
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={() =>
                update.mutate({ is_known: !person.is_known })
              }
            >
              mark {person.is_known ? "unknown" : "known"}
            </button>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px", marginLeft: "auto", color: "var(--accent-dim)" }}
              onClick={() => setConfirming(true)}
            >
              delete
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export function Persons() {
  const [tab, setTab] = useState<"all" | "known" | "unknown">("all");

  const { data: persons = [], isLoading } = useQuery({
    queryKey: ["persons"],
    queryFn: () => listPersons().then((r) => r.data),
    refetchInterval: 30_000,
  });

  const filtered =
    tab === "known"
      ? persons.filter((p) => p.is_known)
      : tab === "unknown"
      ? persons.filter((p) => !p.is_known)
      : persons;

  const knownCount = persons.filter((p) => p.is_known).length;
  const unknownCount = persons.filter((p) => !p.is_known).length;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      <div className="page-header">
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="section-title">persons</span>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {knownCount} known · {unknownCount} unknown
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          borderBottom: "1px solid var(--border)",
          padding: "0 20px",
          flexShrink: 0,
        }}
      >
        {(["all", "known", "unknown"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              background: "none",
              border: "none",
              borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
              padding: "8px 16px 7px",
              fontSize: 11,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              color: tab === t ? "var(--text-bright)" : "var(--text-dim)",
              cursor: "pointer",
              fontFamily: "var(--font)",
              transition: "all 0.1s",
            }}
          >
            {t}
            <span
              style={{
                marginLeft: 6,
                fontSize: 10,
                color: "var(--text-dim)",
              }}
            >
              {t === "all"
                ? persons.length
                : t === "known"
                ? knownCount
                : unknownCount}
            </span>
          </button>
        ))}
      </div>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px 20px",
        }}
      >
        {isLoading ? (
          <div style={{ color: "var(--text-dim)", fontSize: 12 }}>
            loading...
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ color: "var(--text-dim)", fontSize: 12, padding: "32px 0" }}>
            {tab === "all"
              ? "no persons detected yet."
              : `no ${tab} persons.`}
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            {filtered.map((p) => (
              <PersonCard key={p.id} person={p} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
