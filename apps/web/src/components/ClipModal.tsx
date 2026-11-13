import { useEffect, useRef, useState } from "react";
import { updateEventAnnotation } from "../api/client";
import type { OmniscientEvent } from "../api/client";

interface Props {
  event: OmniscientEvent;
  onClose: () => void;
  onAnnotationSaved?: (note: string | null) => void;
}

function isImageClip(value: string | null): boolean {
  if (!value) return false;
  try {
    // Presigned object URLs include a query string; classify by pathname so
    // the signature does not make JPEG evidence render as a video.
    return /\.(jpg|jpeg|png|webp)$/i.test(new URL(value, window.location.origin).pathname);
  } catch {
    return false;
  }
}

export function ClipModal({ event, onClose, onAnnotationSaved }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [note, setNote] = useState(event.annotation ?? "");
  const [savingNote, setSavingNote] = useState(false);
  const [noteError, setNoteError] = useState("");

  useEffect(() => {
    closeRef.current?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const isImage = isImageClip(event.clip_path);

  async function saveAnnotation() {
    const nextNote = note.trim() || null;
    setSavingNote(true);
    setNoteError("");
    try {
      await updateEventAnnotation(event.id, nextNote);
      onAnnotationSaved?.(nextNote);
    } catch {
      setNoteError("couldn't save this note; the event was left unchanged.");
    } finally {
      setSavingNote(false);
    }
  }

  return (
    <div
      onClick={onClose}
      role="presentation"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.88)",
        zIndex: 9990,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 32,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Event evidence"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border-hi)",
          boxShadow: "4px 4px 0 var(--border)",
          width: "100%",
          maxWidth: 800,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "10px 16px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span
              style={{
                fontSize: 12,
                color: "var(--text-bright)",
                letterSpacing: "0.04em",
              }}
            >
              {event.action_label}
            </span>
            <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
              {new Date(event.timestamp).toLocaleString()}
              {event.location_label && ` · ${event.location_label}`}
            </span>
          </div>
          <button
            ref={closeRef}
            className="btn btn-ghost"
            aria-label="Close event evidence"
            style={{ padding: "3px 10px" }}
            onClick={onClose}
          >
            esc
          </button>
        </div>

        {/* Clip viewer */}
        <div
          style={{
            background: "#000",
            minHeight: 200,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {event.clip_path ? (
            isImage ? (
              <img
                src={event.clip_path}
                alt={`Evidence image for ${event.action_label}`}
                style={{ maxWidth: "100%", maxHeight: 480, display: "block" }}
              />
            ) : (
              <video
                src={event.clip_path}
                controls
                autoPlay
                aria-label={`Evidence video for ${event.action_label}`}
                style={{ maxWidth: "100%", maxHeight: 480 }}
              />
            )
          ) : (
            <span
              style={{
                color: "var(--text-dim)",
                fontSize: 11,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              no clip available
            </span>
          )}
        </div>

        {/* Metadata row */}
        <div
          style={{
            padding: "10px 16px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            gap: 20,
            flexWrap: "wrap",
          }}
        >
          {[
            { k: "type", v: event.event_type.replace(/_/g, " ") },
            { k: "person", v: event.person_label ?? "—" },
            { k: "object", v: event.object_label ?? "—" },
            { k: "location", v: event.location_label ?? "—" },
            {
              k: "confidence",
              v: `${Math.round(event.confidence * 100)}%`,
            },
          ].map(({ k, v }) => (
            <div key={k}>
              <div className="label">{k}</div>
              <div style={{ fontSize: 12, color: "var(--text)", marginTop: 2 }}>
                {v}
              </div>
            </div>
          ))}
        </div>

        <div style={{ padding: "10px 16px", borderTop: "1px solid var(--border)" }}>
          <label htmlFor="event-annotation" className="label">operator note</label>
          <textarea
            id="event-annotation"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={2000}
            placeholder="Add a review note for this event"
            rows={3}
            style={{ width: "100%", marginTop: 5, resize: "vertical", boxSizing: "border-box" }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6 }}>
            <button className="btn btn-ghost" type="button" onClick={() => void saveAnnotation()} disabled={savingNote}>
              {savingNote ? "saving..." : "save note"}
            </button>
            <span style={{ fontSize: 10, color: "var(--text-dim)" }}>{note.length}/2000</span>
            {noteError && <span role="alert" style={{ fontSize: 10, color: "var(--accent-hi)" }}>{noteError}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
