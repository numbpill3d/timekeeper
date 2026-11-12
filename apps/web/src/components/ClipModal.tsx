import { useEffect } from "react";
import type { OmniscientEvent } from "../api/client";

interface Props {
  event: OmniscientEvent;
  onClose: () => void;
}

export function ClipModal({ event, onClose }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const isImage =
    event.clip_path?.match(/\.(jpg|jpeg|png|webp)$/i) !== null;

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
            className="btn btn-ghost"
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
                alt="event clip"
                style={{ maxWidth: "100%", maxHeight: 480, display: "block" }}
              />
            ) : (
              <video
                src={event.clip_path}
                controls
                autoPlay
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
      </div>
    </div>
  );
}
