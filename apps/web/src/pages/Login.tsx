import { useState } from "react";
import { api } from "../api/client";

interface Props {
  onAuth: () => void;
}

export function Login({ onAuth }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setError("");
    setLoading(true);
    try {
      const { data } = await api.post<{ access_token: string }>(
        mode === "login" ? "/auth/login" : "/auth/register",
        { email, password }
      );
      localStorage.setItem("access_token", data.access_token);
      onAuth();
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;
      setError(detail ?? "request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg)",
        /* subtle grid bg */
        backgroundImage:
          "linear-gradient(var(--border) 1px, transparent 1px)," +
          "linear-gradient(90deg, var(--border) 1px, transparent 1px)",
        backgroundSize: "40px 40px",
      }}
    >
      <div
        style={{
          width: 340,
          border: "1px solid var(--border-hi)",
          background: "var(--surface)",
          boxShadow: "4px 4px 0 var(--border)",
        }}
      >
        {/* Header bar */}
        <div
          style={{
            borderBottom: "1px solid var(--border)",
            padding: "12px 20px",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <div
            style={{
              width: 8,
              height: 8,
              background: "var(--accent)",
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: 11,
              fontWeight: "bold",
              letterSpacing: "0.2em",
              color: "var(--accent)",
              textTransform: "uppercase",
            }}
          >
            OMNISCIENT HOME
          </span>
        </div>

        <div style={{ padding: "28px 24px 24px" }}>
          {/* Mode title */}
          <div style={{ marginBottom: 20 }}>
            <div className="section-title" style={{ marginBottom: 4 }}>
              {mode === "login" ? "authenticate" : "create account"}
            </div>
            <div
              style={{ height: 1, background: "var(--border)", marginTop: 6 }}
            />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                email
              </div>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: "var(--elevated)",
                  border: "1px solid var(--border-hi)",
                  color: "var(--text)",
                }}
              />
            </div>

            <div>
              <div className="label" style={{ marginBottom: 4 }}>
                password
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  background: "var(--elevated)",
                  border: "1px solid var(--border-hi)",
                  color: "var(--text)",
                }}
                onKeyDown={(e) => e.key === "Enter" && submit()}
              />
            </div>

            {error && (
              <div
                style={{
                  padding: "6px 10px",
                  border: "1px solid var(--accent-dim)",
                  color: "var(--accent)",
                  fontSize: 11,
                  letterSpacing: "0.05em",
                }}
              >
                ! {error}
              </div>
            )}

            <button
              className="btn btn-primary"
              style={{ width: "100%", marginTop: 4, padding: "10px" }}
              onClick={submit}
              disabled={loading || !email || !password}
            >
              {loading ? "..." : mode === "login" ? "sign in" : "create account"}
            </button>

            <button
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--text-dim)",
                fontSize: 11,
                letterSpacing: "0.08em",
                textDecoration: "underline",
                padding: "2px 0",
                fontFamily: "var(--font)",
                textTransform: "uppercase",
              }}
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
              }}
            >
              {mode === "login"
                ? "register new account →"
                : "← back to sign in"}
            </button>
          </div>
        </div>

        <div
          style={{
            borderTop: "1px solid var(--border)",
            padding: "8px 20px",
            fontSize: 10,
            color: "var(--text-dim)",
          }}
        >
          home surveillance intelligence platform v0.1
        </div>
      </div>
    </div>
  );
}
