import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listCameras, addCamera, deleteCamera, Camera } from "../api/client";

const PROTOCOLS = ["rtsp", "http", "https", "hls", "file", "onvif", "ring", "nest", "arlo", "wyze"];

function CameraCard({
  cam,
  onDelete,
}: {
  cam: Camera;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        transition: "border-color 0.1s",
      }}
      onMouseEnter={(e) =>
        ((e.currentTarget as HTMLElement).style.borderColor = "var(--border-hi)")
      }
      onMouseLeave={(e) =>
        ((e.currentTarget as HTMLElement).style.borderColor = "var(--border)")
      }
    >
      {/* Top row */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-bright)",
              fontWeight: "bold",
              letterSpacing: "0.04em",
            }}
          >
            {cam.name}
          </div>
          {cam.location_label && (
            <div
              style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}
            >
              {cam.location_label}
            </div>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              width: 7,
              height: 7,
              background: cam.is_active ? "var(--green)" : "var(--text-dim)",
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: 10,
              color: cam.is_active ? "var(--green)" : "var(--text-dim)",
              textTransform: "uppercase",
              letterSpacing: "0.1em",
            }}
          >
            {cam.is_active ? "online" : "offline"}
          </span>
        </div>
      </div>

      {/* URL + badges */}
      <div
        style={{
          fontSize: 11,
          color: "var(--text-dim)",
          fontFamily: "var(--font)",
          wordBreak: "break-all",
          borderLeft: "2px solid var(--border-hi)",
          paddingLeft: 8,
        }}
      >
        {cam.stream_url}
      </div>

      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span className="badge badge-dim">{cam.protocol}</span>
        {cam.is_edge_only && (
          <span className="badge badge-amber">edge only</span>
        )}
      </div>

      {/* Actions */}
      <div
        style={{
          borderTop: "1px solid var(--border)",
          paddingTop: 10,
          display: "flex",
          gap: 8,
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
              remove this camera?
            </span>
            <button
              className="btn btn-danger"
              style={{ padding: "4px 10px" }}
              onClick={onDelete}
            >
              yes
            </button>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={() => setConfirming(false)}
            >
              no
            </button>
          </>
        ) : (
          <button
            className="btn btn-ghost"
            style={{ padding: "4px 10px", marginLeft: "auto" }}
            onClick={() => setConfirming(true)}
          >
            remove
          </button>
        )}
      </div>
    </div>
  );
}

export function Cameras() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [loc, setLoc] = useState("");
  const [proto, setProto] = useState("rtsp");
  const [edgeOnly, setEdgeOnly] = useState(false);
  const [providerConfigText, setProviderConfigText] = useState("");
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);

  const { data: cameras = [], isLoading } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => listCameras().then((r) => r.data),
  });

  const add = useMutation({
    mutationFn: () => {
      let provider_config: Record<string, unknown> | undefined;
      if (providerConfigText.trim()) {
        provider_config = JSON.parse(providerConfigText) as Record<string, unknown>;
      }
      return addCamera({
        name,
        stream_url: url,
        protocol: proto,
        location_label: loc || undefined,
        is_edge_only: edgeOnly,
        provider_config,
      }).then((r) => r.data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cameras"] });
      setName("");
      setUrl("");
      setLoc("");
      setProto("rtsp");
      setEdgeOnly(false);
      setProviderConfigText("");
      setError("");
      setShowForm(false);
    },
    onError: (e: unknown) => {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;
      setError(detail ?? "failed to add camera");
    },
  });

  const remove = useMutation({
    mutationFn: deleteCamera,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cameras"] }),
  });

  const onlineCams = cameras.filter((c) => c.is_active).length;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div className="page-header">
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="section-title">cameras</span>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {onlineCams}/{cameras.length} online
          </span>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm ? "cancel" : "+ add camera"}
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid var(--border)",
            background: "var(--surface)",
            display: "flex",
            flexDirection: "column",
            gap: 12,
            flexShrink: 0,
          }}
        >
          <div className="section-title">add camera</div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 2fr",
              gap: 10,
            }}
          >
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                name
              </div>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="front door"
                style={{ width: "100%", padding: "7px 10px" }}
              />
            </div>
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                stream url
              </div>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="rtsp://192.168.1.100/stream"
                style={{ width: "100%", padding: "7px 10px" }}
              />
            </div>
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                location label
              </div>
              <input
                value={loc}
                onChange={(e) => setLoc(e.target.value)}
                placeholder="front entrance (optional)"
                style={{ width: "100%", padding: "7px 10px" }}
              />
            </div>
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                protocol
              </div>
              <select
                value={proto}
                onChange={(e) => setProto(e.target.value)}
                style={{ width: "100%", padding: "7px 10px" }}
              >
                {PROTOCOLS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {(proto === "ring" || proto === "nest" || proto === "arlo" || proto === "wyze") && (
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                provider config (JSON, no secrets)
              </div>
              <input
                value={providerConfigText}
                onChange={(e) => setProviderConfigText(e.target.value)}
                placeholder='{"whep_url":"https://..."}'
                style={{ width: "100%", padding: "7px 10px" }}
              />
              <div style={{ color: "var(--text-dim)", fontSize: 10, marginTop: 4 }}>
                Tokens stay in ingestion: {proto.toUpperCase()}_ACCESS_TOKEN.
              </div>
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: "pointer",
                fontSize: 12,
              }}
            >
              <input
                type="checkbox"
                checked={edgeOnly}
                onChange={(e) => setEdgeOnly(e.target.checked)}
                style={{ width: 14, height: 14 }}
              />
              <span style={{ color: "var(--text-dim)" }}>
                edge-only (no cloud processing)
              </span>
            </label>
          </div>
          {error && (
            <div
              style={{
                fontSize: 11,
                color: "var(--accent)",
                letterSpacing: "0.05em",
              }}
            >
              ! {error}
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn btn-primary"
              disabled={!name || !url || add.isPending}
              onClick={() => add.mutate()}
            >
              {add.isPending ? "..." : "add camera"}
            </button>
          </div>
        </div>
      )}

      {/* Camera grid */}
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
        ) : cameras.length === 0 ? (
          <div
            style={{
              color: "var(--text-dim)",
              fontSize: 12,
              padding: "32px 0",
            }}
          >
            no cameras configured. add one to start.
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
              gap: 12,
            }}
          >
            {cameras.map((c) => (
              <CameraCard
                key={c.id}
                cam={c}
                onDelete={() => remove.mutate(c.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
