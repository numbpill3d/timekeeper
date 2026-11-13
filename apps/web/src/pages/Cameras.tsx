import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listCameras,
  addCamera,
  updateCamera,
  deleteCamera,
  Camera,
} from "../api/client";

const PROTOCOLS = ["rtsp", "http", "https", "hls", "file", "onvif", "ring", "nest", "arlo", "wyze"];
const DEFAULT_RETENTION_DAYS = 30;
const STATUS_COLOR = {
  paused: "var(--text-dim)",
  starting: "var(--amber)",
  online: "var(--green)",
  stale: "var(--amber)",
  error: "var(--accent)",
} as const;

function cameraDiagnostic(cam: Camera): string {
  if (cam.is_edge_only) {
    return "external agent required before this source can be captured";
  }
  if (cam.status === "paused") {
    return "capture paused — resume to collect new evidence";
  }
  if (cam.status === "starting") {
    return "waiting for the first frame — check source reachability and configuration";
  }
  if (cam.status === "stale") {
    return "no recent frame — check the camera network and source availability";
  }
  if (cam.status === "error") {
    const attempts = cam.consecutive_failures > 1
      ? ` (${cam.consecutive_failures} consecutive failures)`
      : "";
    return `capture error${attempts} — check the source and ingestion logs`;
  }
  return "receiving frames normally";
}

function CameraCard({
  cam,
  onToggle,
  onDelete,
  onSave,
  togglePending,
  deletePending,
  savePending,
}: {
  cam: Camera;
  onToggle: () => void;
  onDelete: () => void;
  onSave: (data: {
    name: string;
    stream_url: string;
    protocol: string;
    location_label: string | null;
  }) => Promise<unknown>;
  togglePending: boolean;
  deletePending: boolean;
  savePending: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(cam.name);
  const [editUrl, setEditUrl] = useState(cam.stream_url);
  const [editLocation, setEditLocation] = useState(cam.location_label ?? "");
  const [editProtocol, setEditProtocol] = useState(cam.protocol);
  const [editError, setEditError] = useState("");

  function startEditing() {
    setEditName(cam.name);
    setEditUrl(cam.stream_url);
    setEditLocation(cam.location_label ?? "");
    setEditProtocol(cam.protocol);
    setEditError("");
    setEditing(true);
  }

  async function save() {
    const name = editName.trim();
    const stream_url = editUrl.trim();
    if (!name || !stream_url) {
      setEditError("name and stream URL are required");
      return;
    }
    setEditError("");
    try {
      await onSave({
        name,
        stream_url,
        protocol: editProtocol,
        location_label: editLocation.trim() || null,
      });
      setEditing(false);
    } catch {
      setEditError("could not save camera changes");
    }
  }

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
              background: STATUS_COLOR[cam.status],
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: 10,
              color: STATUS_COLOR[cam.status],
              textTransform: "uppercase",
              letterSpacing: "0.1em",
            }}
          >
            {cam.status}
          </span>
        </div>
      </div>

      {editing ? (
        <div style={{ display: "grid", gap: 8 }}>
          <input
            aria-label={`Edit name for ${cam.name}`}
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            style={{ width: "100%", padding: "6px 8px" }}
          />
          <input
            aria-label={`Edit stream URL for ${cam.name}`}
            value={editUrl}
            onChange={(e) => setEditUrl(e.target.value)}
            style={{ width: "100%", padding: "6px 8px" }}
          />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <input
              aria-label={`Edit location for ${cam.name}`}
              value={editLocation}
              onChange={(e) => setEditLocation(e.target.value)}
              placeholder="location (optional)"
              style={{ width: "100%", padding: "6px 8px" }}
            />
            <select
              aria-label={`Edit protocol for ${cam.name}`}
              value={editProtocol}
              onChange={(e) => setEditProtocol(e.target.value)}
              style={{ width: "100%", padding: "6px 8px" }}
            >
              {PROTOCOLS.map((protocol) => (
                <option key={protocol} value={protocol}>{protocol}</option>
              ))}
            </select>
          </div>
          {editError && <div role="alert" style={{ color: "var(--accent)", fontSize: 11 }}>{editError}</div>}
        </div>
      ) : (
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
      )}

      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span className="badge badge-dim">{editing ? editProtocol : cam.protocol}</span>
        {cam.is_edge_only && (
          <span className="badge badge-amber">external agent required</span>
        )}
      </div>

      <div style={{ fontSize: 10, color: "var(--text-dim)" }}>
        {cam.last_frame_at
          ? `last frame ${formatDistanceToNow(new Date(cam.last_frame_at), { addSuffix: true })}`
          : "no frame received yet"}
        {cam.status === "error" && cam.last_error_code
          ? ` · ${cam.last_error_code}`
          : ""}
        {cam.last_frame_width && cam.last_frame_height
          ? ` · ${cam.last_frame_width}×${cam.last_frame_height}`
          : ""}
        {cam.observed_fps
          ? ` · ~${cam.observed_fps.toFixed(1)} fps`
          : ""}
      </div>
      <div
        role="status"
        style={{
          borderLeft: `2px solid ${STATUS_COLOR[cam.status]}`,
          paddingLeft: 8,
          color: STATUS_COLOR[cam.status],
          fontSize: 10,
        }}
      >
        {cameraDiagnostic(cam)}
      </div>

      <div
        style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          padding: "8px 10px",
          display: "grid",
          gap: 3,
        }}
        aria-label={`Privacy and retention for ${cam.name}`}
      >
        <div style={{ color: "var(--text-bright)", fontSize: 10, letterSpacing: "0.04em" }}>
          privacy &amp; retention
        </div>
        <div style={{ color: "var(--text-dim)", fontSize: 10 }}>
          evidence kept locally for {DEFAULT_RETENTION_DAYS} days by default
        </div>
        <div style={{ color: "var(--text-dim)", fontSize: 10 }}>
          person-specific retention can override this window
        </div>
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
        {editing ? (
          <>
            <button
              className="btn btn-primary"
              style={{ padding: "4px 10px" }}
              onClick={() => void save()}
              disabled={savePending}
            >
              {savePending ? "saving..." : "save"}
            </button>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={() => setEditing(false)}
              disabled={savePending}
            >
              cancel
            </button>
          </>
        ) : confirming ? (
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
              disabled={deletePending}
            >
              {deletePending ? "removing..." : "yes"}
            </button>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={() => setConfirming(false)}
              disabled={deletePending}
            >
              no
            </button>
          </>
        ) : (
          <>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={startEditing}
              disabled={togglePending || deletePending}
            >
              edit
            </button>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px" }}
              onClick={onToggle}
              disabled={togglePending || deletePending}
              aria-label={`${cam.is_active ? "Pause" : "Resume"} ${cam.name}`}
            >
              {togglePending ? "..." : cam.is_active ? "pause" : "resume"}
            </button>
            <button
              className="btn btn-ghost"
              style={{ padding: "4px 10px", marginLeft: "auto" }}
              onClick={() => setConfirming(true)}
              disabled={togglePending || deletePending}
            >
              remove
            </button>
          </>
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
  const [providerConfigText, setProviderConfigText] = useState("");
  const [error, setError] = useState("");
  const [removeError, setRemoveError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [setupStep, setSetupStep] = useState<1 | 2>(1);
  const [privacyAcknowledged, setPrivacyAcknowledged] = useState(false);

  const { data: cameras = [], isLoading, isError, refetch } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => listCameras().then((r) => r.data),
    refetchInterval: 15_000,
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
        provider_config,
      }).then((r) => r.data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cameras"] });
      setName("");
      setUrl("");
      setLoc("");
      setProto("rtsp");
      setProviderConfigText("");
      setError("");
      setSetupStep(1);
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
    onSuccess: () => {
      setRemoveError("");
      qc.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: () => setRemoveError("failed to remove camera; its history was preserved"),
  });

  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updateCamera(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cameras"] }),
    onError: () => setError("failed to update camera status"),
  });

  const update = useMutation({
    mutationFn: ({ id, data }: {
      id: string;
      data: {
        name: string;
        stream_url: string;
        protocol: string;
        location_label: string | null;
      };
    }) => updateCamera(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cameras"] }),
  });

  const activeCams = cameras.filter((c) => c.is_active).length;

  function validateSourceStep(): boolean {
    if (!name.trim()) {
      setError("give this camera a name first");
      return false;
    }
    setError("");
    setSetupStep(2);
    return true;
  }

  function validateConnectionStep(): boolean {
    if (!privacyAcknowledged) {
      setError("confirm that you are authorized to monitor and retain this feed");
      return false;
    }
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setError("stream URL is required");
      return false;
    }
    try {
      const parsed = new URL(trimmedUrl);
      const deviceProtocols = ["ring", "nest", "arlo", "wyze"];
      if (deviceProtocols.includes(proto) && parsed.protocol !== `${proto}:`) {
        setError(`use a ${proto}:// device URL for the ${proto} adapter`);
        return false;
      }
      if (providerConfigText.trim()) {
        const config = JSON.parse(providerConfigText) as unknown;
        if (!config || Array.isArray(config) || typeof config !== "object") {
          setError("provider config must be a JSON object");
          return false;
        }
      }
    } catch {
      setError("enter a valid stream URL and provider JSON");
      return false;
    }
    setError("");
    return true;
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
      {/* Header */}
      <div className="page-header">
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="section-title">cameras</span>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {activeCams}/{cameras.length} active
          </span>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            setShowForm((v) => !v);
            setSetupStep(1);
            setPrivacyAcknowledged(false);
            setError("");
          }}
        >
          {showForm ? "cancel" : "+ add camera"}
        </button>
      </div>

      {removeError && (
        <div role="alert" style={{ padding: "8px 20px", color: "var(--accent)", fontSize: 11 }}>
          ! {removeError}
        </div>
      )}

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
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <div className="section-title">add camera</div>
            <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
              step {setupStep} of 2 · {setupStep === 1 ? "name the source" : "connect and place it"}
            </span>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 2fr",
              gap: 10,
            }}
          >
            {setupStep === 1 ? (
              <>
                <div>
                  <div className="label" style={{ marginBottom: 4 }}>
                    name
                  </div>
                  <input
                    aria-label="Camera name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="front door"
                    autoFocus
                    style={{ width: "100%", padding: "7px 10px" }}
                  />
                </div>
                <div>
                  <div className="label" style={{ marginBottom: 4 }}>
                    source type
                  </div>
                  <select
                    aria-label="Camera protocol"
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
              </>
            ) : (
              <>
                <div>
                  <div className="label" style={{ marginBottom: 4 }}>
                    stream URL
                  </div>
                  <input
                    aria-label="Camera stream URL"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder={proto === "ring" || proto === "nest" ? `${proto}://device-id` : "rtsp://192.168.1.100/stream"}
                    autoFocus
                    style={{ width: "100%", padding: "7px 10px" }}
                  />
                </div>
                <div>
                  <div className="label" style={{ marginBottom: 4 }}>
                    location label
                  </div>
                  <input
                    aria-label="Camera location label"
                    value={loc}
                    onChange={(e) => setLoc(e.target.value)}
                    placeholder="front entrance (optional)"
                    style={{ width: "100%", padding: "7px 10px" }}
                  />
                </div>
              </>
            )}
          </div>
          {setupStep === 2 && (proto === "ring" || proto === "nest" || proto === "arlo" || proto === "wyze") && (
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                provider config (JSON, no secrets)
              </div>
              <input
                aria-label="Camera provider configuration JSON"
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
          {setupStep === 2 && (
            <label
              style={{
                display: "flex",
                gap: 8,
                alignItems: "flex-start",
                padding: "9px 10px",
                border: "1px solid var(--border-hi)",
                background: "var(--elevated)",
                color: "var(--text-dim)",
                fontSize: 10,
                lineHeight: 1.5,
              }}
            >
              <input
                type="checkbox"
                checked={privacyAcknowledged}
                onChange={(event) => {
                  setPrivacyAcknowledged(event.target.checked);
                  if (event.target.checked) setError("");
                }}
                aria-label="Confirm camera monitoring authorization"
                style={{ marginTop: 2 }}
              />
              <span>
                I am authorized to monitor and retain this feed. Evidence stays in
                this Timekeeper deployment until retention cleanup or camera deletion;
                use appropriate notice and consent for people in view.
              </span>
            </label>
          )}
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
            {setupStep === 2 && (
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => {
                  setError("");
                  setSetupStep(1);
                }}
                disabled={add.isPending}
              >
                back
              </button>
            )}
            <button
              className="btn btn-primary"
              type="button"
              disabled={add.isPending}
              onClick={() => {
                if (setupStep === 1) {
                  validateSourceStep();
                } else if (validateConnectionStep()) {
                  add.mutate();
                }
              }}
            >
              {add.isPending ? "..." : setupStep === 1 ? "next" : "add camera"}
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
        ) : isError ? (
          <div role="alert" style={{ color: "var(--accent)", fontSize: 12, padding: "32px 0", display: "flex", gap: 10, alignItems: "center" }}>
            couldn't load cameras.
            <button className="btn btn-ghost" onClick={() => void refetch()}>retry</button>
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
                onToggle={() => {
                  setError("");
                  toggle.mutate({ id: c.id, is_active: !c.is_active });
                }}
                onDelete={() => remove.mutate(c.id)}
                onSave={(data) => update.mutateAsync({ id: c.id, data })}
                togglePending={toggle.isPending && toggle.variables?.id === c.id}
                deletePending={remove.isPending && remove.variables === c.id}
                savePending={update.isPending && update.variables?.id === c.id}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
