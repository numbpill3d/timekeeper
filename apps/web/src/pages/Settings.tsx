import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  createPipedreamConnectToken,
  getProfile,
  listAuditLog,
  updateProfile,
} from "../api/client";

const TIER_INFO: Record<
  string,
  { label: string; features: string[] }
> = {
  free: {
    label: "free",
    features: ["2 cameras", "10 queries/month", "30-day event default"],
  },
  home: {
    label: "home",
    features: ["5 cameras", "unlimited queries", "30-day event default"],
  },
  family: {
    label: "family",
    features: ["10 cameras", "unlimited queries", "30-day event default"],
  },
  pro: {
    label: "pro",
    features: ["unlimited cameras", "unlimited queries", "30-day event default"],
  },
};

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: "0.14em",
          color: "var(--text-dim)",
          marginBottom: 10,
          paddingBottom: 6,
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <span style={{ color: "var(--accent)", fontSize: 8 }}>◆</span>
        {title}
      </div>
      {children}
    </div>
  );
}

export function Settings() {
  const [fcmToken, setFcmToken] = useState("");
  const [phone, setPhone] = useState("");
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [connectError, setConnectError] = useState("");
  const savedTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (savedTimerRef.current !== null) {
        window.clearTimeout(savedTimerRef.current);
      }
    };
  }, []);

  const { data: profile, isLoading, isError, refetch } = useQuery({
    queryKey: ["profile"],
    queryFn: () => getProfile().then((r) => r.data),
  });
  const {
    data: audit = [],
    isLoading: auditLoading,
    isError: auditError,
    refetch: refetchAudit,
  } = useQuery({
    queryKey: ["audit-log"],
    queryFn: () => listAuditLog().then((r) => r.data),
  });

  useEffect(() => {
    if (profile) {
      setFcmToken(profile.fcm_token ?? "");
      setPhone(profile.phone ?? "");
    }
  }, [profile]);

  const save = useMutation({
    mutationFn: () =>
      updateProfile({
        fcm_token: fcmToken || null,
        phone: phone || null,
      }),
    onMutate: () => {
      setSaveError("");
      setSaved(false);
    },
    onSuccess: () => {
      setSaved(true);
      if (savedTimerRef.current !== null) {
        window.clearTimeout(savedTimerRef.current);
      }
      savedTimerRef.current = window.setTimeout(() => {
        savedTimerRef.current = null;
        setSaved(false);
      }, 2000);
    },
    onError: () => setSaveError("could not save notification settings"),
  });

  const connectPipedream = useMutation({
    mutationFn: createPipedreamConnectToken,
    onSuccess: ({ data }) => {
      setConnectError("");
      window.location.assign(data.connect_link_url);
    },
    onError: (error: unknown) => {
      const detail =
        (error as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;
      setConnectError(detail ?? "could not start the Pipedream Connect flow");
    },
  });

  const tier = TIER_INFO[profile?.tier ?? "free"] ?? TIER_INFO.free;

  function exportAuditLog() {
    if (!audit.length) return;
    const headers = ["created_at", "action", "resource_type", "resource_id", "metadata"];
    const csvCell = (value: unknown) => `"${String(value ?? "").replace(/"/g, '""')}"`;
    const rows = audit.map((entry) => [
      entry.created_at,
      entry.action,
      entry.resource_type,
      entry.resource_id,
      JSON.stringify(entry.metadata),
    ]);
    const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "timekeeper-audit-log.csv";
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
      <div className="page-header">
        <span className="section-title">settings</span>
      </div>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "24px",
          display: "flex",
          flexDirection: "column",
          gap: 32,
          maxWidth: 640,
        }}
      >
        {isLoading ? (
          <div style={{ color: "var(--text-dim)", fontSize: 12 }}>
            loading...
          </div>
        ) : isError ? (
          <div role="alert" style={{ color: "var(--accent)", fontSize: 12, display: "flex", gap: 10, alignItems: "center" }}>
            couldn't load your profile.
            <button className="btn btn-ghost" onClick={() => void refetch()}>retry</button>
          </div>
        ) : (
          <>
            {/* Account */}
            <Section title="account">
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                <div style={{ display: "flex", gap: 16 }}>
                  <div>
                    <div className="label" style={{ marginBottom: 4 }}>
                      email
                    </div>
                    <div style={{ fontSize: 13, color: "var(--text)" }}>
                      {profile?.email ?? "—"}
                    </div>
                  </div>
                  <div>
                    <div className="label" style={{ marginBottom: 4 }}>
                      user id
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--text-dim)",
                        fontFamily: "var(--font)",
                      }}
                    >
                      {profile?.user_id?.slice(0, 8) ?? "—"}...
                    </div>
                  </div>
                </div>
              </div>
            </Section>

            {/* Plan */}
            <Section title="plan">
              <div
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  padding: "16px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <span
                    style={{
                      fontSize: 15,
                      fontWeight: "bold",
                      color: "var(--text-bright)",
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                    }}
                  >
                    {tier.label}
                  </span>
                  <span className="badge badge-dim">current plan</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {tier.features.map((f) => (
                    <span
                      key={f}
                      style={{
                        fontSize: 11,
                        color: "var(--text-dim)",
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                      }}
                    >
                      <span
                        style={{
                          width: 4,
                          height: 4,
                          background: "var(--accent)",
                          display: "inline-block",
                          flexShrink: 0,
                        }}
                      />
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            </Section>

            {/* Notifications */}
            <Section title="notifications">
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div>
                  <div className="label" style={{ marginBottom: 4 }}>
                    FCM push token
                  </div>
                  <div
                    style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 6 }}
                  >
                    paste your device FCM token to receive push notifications
                  </div>
                  <input
                    aria-label="FCM push token"
                    value={fcmToken}
                    onChange={(e) => setFcmToken(e.target.value)}
                    placeholder="fcm token from your mobile app..."
                    style={{ width: "100%", padding: "7px 10px", fontSize: 11 }}
                  />
                </div>

                <div>
                  <div className="label" style={{ marginBottom: 4 }}>
                    phone number (SMS)
                  </div>
                  <div
                    style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 6 }}
                  >
                    E.164 format — +12125551234 — required for SMS alerts
                  </div>
                  <input
                    aria-label="Phone number for SMS alerts"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+12125551234"
                    style={{ width: "100%", padding: "7px 10px" }}
                  />
                </div>

                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <button
                    className="btn btn-primary"
                    onClick={() => save.mutate()}
                    disabled={save.isPending}
                  >
                    {save.isPending ? "saving..." : "save notification settings"}
                  </button>
                  {saved && (
                    <span
                      style={{
                        fontSize: 11,
                        color: "var(--green)",
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                      }}
                    >
                      ✓ saved
                    </span>
                  )}
                </div>
                {saveError && (
                  <div role="alert" style={{ fontSize: 11, color: "var(--accent)" }}>
                    ! {saveError}
                  </div>
                )}
              </div>
            </Section>

            {/* Integrations */}
            <Section title="integrations">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  connect an account through Pipedream. credentials stay with
                  Pipedream and are never stored in Timekeeper.
                </div>
                <button
                  className="btn btn-primary"
                  style={{ alignSelf: "flex-start" }}
                  onClick={() => connectPipedream.mutate()}
                  disabled={connectPipedream.isPending}
                >
                  {connectPipedream.isPending ? "starting..." : "connect an app"}
                </button>
                {connectError && (
                  <div style={{ fontSize: 11, color: "var(--accent)" }}>
                    ! {connectError}
                  </div>
                )}
              </div>
            </Section>

            {/* Audit history */}
            <Section title="audit history">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  recent destructive actions are recorded for this account. sensitive evidence content is not copied into the log.
                </div>
                {auditLoading ? (
                  <div style={{ color: "var(--text-dim)", fontSize: 11 }}>loading audit history...</div>
                ) : auditError ? (
                  <div role="alert" style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--accent)", fontSize: 11 }}>
                    couldn't load audit history.
                    <button className="btn btn-ghost" onClick={() => void refetchAudit()}>retry</button>
                  </div>
                ) : audit.length === 0 ? (
                  <div style={{ color: "var(--text-dim)", fontSize: 11 }}>no destructive actions recorded.</div>
                ) : (
                  <>
                    <div style={{ display: "grid", gap: 6 }}>
                      {audit.map((entry) => (
                        <div key={entry.id} style={{ borderLeft: "2px solid var(--border-hi)", padding: "6px 8px", fontSize: 11 }}>
                          <div style={{ color: "var(--text-bright)" }}>
                            {entry.action} {entry.resource_type}
                          </div>
                          <div style={{ color: "var(--text-dim)", marginTop: 2 }}>
                            {new Date(entry.created_at).toLocaleString()}
                            {entry.resource_id ? ` · ${entry.resource_id.slice(0, 8)}...` : ""}
                          </div>
                        </div>
                      ))}
                    </div>
                    <button className="btn btn-ghost" style={{ alignSelf: "flex-start" }} onClick={exportAuditLog}>
                      export audit log
                    </button>
                  </>
                )}
              </div>
            </Section>

            {/* Session */}
            <Section title="session">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div
                  style={{ fontSize: 12, color: "var(--text-dim)" }}
                >
                  signing out clears your local session. your data is preserved.
                </div>
                <button
                  className="btn btn-ghost"
                  style={{ alignSelf: "flex-start" }}
                  onClick={() => {
                    localStorage.removeItem("access_token");
                    window.location.reload();
                  }}
                >
                  sign out
                </button>
              </div>
            </Section>
          </>
        )}
      </div>
    </div>
  );
}
