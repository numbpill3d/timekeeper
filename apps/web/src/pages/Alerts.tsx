import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listAlerts,
  createAlert,
  toggleAlert,
  deleteAlert,
  AlertRule,
} from "../api/client";

const PRIORITY_STYLE: Record<string, { badge: string; label: string }> = {
  critical:      { badge: "badge-red",   label: "critical" },
  important:     { badge: "badge-amber", label: "important" },
  informational: { badge: "badge-dim",   label: "info" },
};

const CHANNEL_LABELS: Record<string, string> = {
  push: "push",
  sms:  "sms",
};

function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label
      className="toggle"
      title={checked ? "active" : "paused"}
      aria-busy={disabled}
    >
      <input
        aria-label={`${checked ? "Disable" : "Enable"} ${label}`}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="toggle-track" />
      <span className="toggle-knob" />
    </label>
  );
}

function AlertRow({ rule }: { rule: AlertRule }) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");

  const toggle = useMutation({
    mutationFn: (active: boolean) => toggleAlert(rule.id, active),
    onMutate: () => setError(""),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
    onError: () => setError("could not update this alert"),
  });

  const remove = useMutation({
    mutationFn: () => deleteAlert(rule.id),
    onMutate: () => setError(""),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
    onError: () => setError("could not delete this alert"),
  });

  const p = PRIORITY_STYLE[rule.priority] ?? PRIORITY_STYLE.informational;

  return (
    <div
      style={{
        padding: "12px 20px",
        borderBottom: "1px solid var(--border)",
        display: "flex",
        flexWrap: "wrap",
        gap: 14,
        alignItems: "center",
        opacity: rule.is_active ? 1 : 0.5,
        transition: "opacity 0.1s",
      }}
    >
      <Toggle
        checked={rule.is_active}
        onChange={(v) => toggle.mutate(v)}
        label={rule.name}
        disabled={toggle.isPending || remove.isPending}
      />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 12,
            color: "var(--text-bright)",
            fontWeight: "bold",
          }}
        >
          {rule.name}
        </div>
        <div
          style={{
            fontSize: 11,
            color: "var(--text-dim)",
            marginTop: 2,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {rule.rule_text}
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
        <span className={`badge ${p.badge}`}>{p.label}</span>
        {rule.channels.map((ch) => (
          <span key={ch} className="badge badge-dim">
            {CHANNEL_LABELS[ch] ?? ch}
          </span>
        ))}
      </div>

      <div>
        {confirming ? (
          <div style={{ display: "flex", gap: 6 }}>
            <button
              className="btn btn-danger"
              style={{ padding: "3px 8px" }}
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
            >
              {remove.isPending ? "deleting..." : "delete"}
            </button>
            <button
              className="btn btn-ghost"
              style={{ padding: "3px 8px" }}
              onClick={() => setConfirming(false)}
            >
              cancel
            </button>
          </div>
        ) : (
          <button
            className="btn btn-ghost"
            aria-label={`Delete alert rule ${rule.name}`}
            style={{ padding: "3px 8px", fontSize: 10 }}
            onClick={() => setConfirming(true)}
            disabled={toggle.isPending || remove.isPending}
          >
            ✕
          </button>
        )}
      </div>
      {error && (
        <div
          role="alert"
          style={{ color: "var(--accent)", fontSize: 10, flexBasis: "100%" }}
        >
          ! {error}
        </div>
      )}
    </div>
  );
}

export function Alerts() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [ruleText, setRuleText] = useState("");
  const [priority, setPriority] = useState("important");
  const [channels, setChannels] = useState<string[]>(["push"]);
  const [error, setError] = useState("");

  const { data: rules = [], isLoading, isError, refetch } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => listAlerts().then((r) => r.data),
  });

  const create = useMutation({
    mutationFn: () =>
      createAlert({ name, rule_text: ruleText, priority, channels }).then(
        (r) => r.data
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      setName("");
      setRuleText("");
      setPriority("important");
      setChannels(["push"]);
      setError("");
      setShowForm(false);
    },
    onError: (e: unknown) => {
      const d =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;
      setError(d ?? "failed to create rule");
    },
  });

  function toggleChannel(ch: string) {
    setChannels((prev) =>
      prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]
    );
  }

  const activeCount = rules.filter((r) => r.is_active).length;

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
          <span className="section-title">alert rules</span>
          <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
            {activeCount}/{rules.length} active
          </span>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowForm((v) => !v)}
        >
          {showForm ? "cancel" : "+ new rule"}
        </button>
      </div>

      {/* Create form */}
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
          <div className="section-title">new alert rule</div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 2fr",
              gap: 10,
            }}
          >
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                rule name
              </div>
              <input
                aria-label="Alert rule name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="unknown visitor"
                style={{ width: "100%", padding: "7px 10px" }}
              />
            </div>
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                natural language rule
              </div>
              <input
                aria-label="Natural language alert rule"
                value={ruleText}
                onChange={(e) => setRuleText(e.target.value)}
                placeholder="alert me when an unknown person enters the front door"
                style={{ width: "100%", padding: "7px 10px" }}
              />
            </div>
          </div>

          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            <div>
              <div className="label" style={{ marginBottom: 6 }}>
                priority
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                {["critical", "important", "informational"].map((p) => (
                  <button
                    key={p}
                    aria-pressed={priority === p}
                    onClick={() => setPriority(p)}
                    style={{
                      background:
                        priority === p ? "var(--accent)" : "transparent",
                      color:
                        priority === p ? "#fff" : "var(--text-dim)",
                      border: `1px solid ${
                        priority === p ? "var(--accent)" : "var(--border-hi)"
                      }`,
                      padding: "4px 10px",
                      fontSize: 10,
                      textTransform: "uppercase",
                      letterSpacing: "0.1em",
                      cursor: "pointer",
                      fontFamily: "var(--font)",
                    }}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="label" style={{ marginBottom: 6 }}>
                channels
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                {["push", "sms"].map((ch) => (
                  <button
                    key={ch}
                    aria-pressed={channels.includes(ch)}
                    disabled={channels.length === 1 && channels.includes(ch)}
                    title={
                      channels.length === 1 && channels.includes(ch)
                        ? "Select another channel before disabling this one"
                        : undefined
                    }
                    onClick={() => toggleChannel(ch)}
                    style={{
                      background: channels.includes(ch)
                        ? "var(--elevated)"
                        : "transparent",
                      color: channels.includes(ch)
                        ? "var(--text-bright)"
                        : "var(--text-dim)",
                      border: `1px solid ${
                        channels.includes(ch)
                          ? "var(--border-hi)"
                          : "var(--border)"
                      }`,
                      padding: "4px 10px",
                      fontSize: 10,
                      textTransform: "uppercase",
                      letterSpacing: "0.1em",
                      cursor:
                        channels.length === 1 && channels.includes(ch)
                          ? "not-allowed"
                          : "pointer",
                      fontFamily: "var(--font)",
                      opacity:
                        channels.length === 1 && channels.includes(ch) ? 0.65 : 1,
                    }}
                  >
                    {ch}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {error && (
            <div
              style={{ fontSize: 11, color: "var(--accent)", letterSpacing: "0.05em" }}
            >
              ! {error}
            </div>
          )}

          <div>
            <button
              className="btn btn-primary"
              disabled={!name || !ruleText || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? "creating..." : "create rule"}
            </button>
          </div>
        </div>
      )}

      {/* Rules list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {isLoading ? (
          <div
            style={{ padding: "32px 20px", color: "var(--text-dim)", fontSize: 12 }}
          >
            loading...
          </div>
        ) : isError ? (
          <div role="alert" style={{ padding: "32px 20px", color: "var(--accent)", fontSize: 12, display: "flex", gap: 10, alignItems: "center" }}>
            couldn't load alert rules.
            <button className="btn btn-ghost" onClick={() => void refetch()}>retry</button>
          </div>
        ) : rules.length === 0 ? (
          <div
            style={{
              padding: "40px 20px",
              color: "var(--text-dim)",
              fontSize: 12,
            }}
          >
            no alert rules. create one to start receiving notifications.
          </div>
        ) : (
          rules.map((r) => <AlertRow key={r.id} rule={r} />)
        )}
      </div>
    </div>
  );
}
