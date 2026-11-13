import { useEffect, useRef, useState } from "react";
import { askQuestion } from "../api/client";

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  confidence?: number;
  clips?: string[];
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 0,
      role: "assistant",
      content:
        'system ready. ask anything — "where are my keys?", "who came home at 3pm?", "did any packages arrive today?"',
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (scrollTimerRef.current !== null) {
        window.clearTimeout(scrollTimerRef.current);
      }
    };
  }, []);

  const history = messages.slice(-6).map((m) => ({
    role: m.role,
    content: m.content,
  }));

  async function send(question = input) {
    const q = question.trim();
    if (!q || loading) return;
    setInput("");
    setError("");

    const uid = Date.now();
    setMessages((p) => [...p, { id: uid, role: "user", content: q }]);
    setLoading(true);

    try {
      const { data } = await askQuestion(q, history);
      setMessages((p) => [
        ...p,
        {
          id: uid + 1,
          role: "assistant",
          content: data.answer,
          confidence: data.confidence,
          clips: data.clips,
        },
      ]);
    } catch {
      setError("query unavailable — check that the API and query engine are running.");
    } finally {
      setLoading(false);
      if (scrollTimerRef.current !== null) {
        window.clearTimeout(scrollTimerRef.current);
      }
      scrollTimerRef.current = window.setTimeout(
        () => bottomRef.current?.scrollIntoView({ behavior: "smooth" }),
        50
      );
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        borderLeft: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      <div
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexShrink: 0,
        }}
      >
        <span className="panel-bullet" aria-hidden="true" />
        <span className="section-title">query interface</span>
        {messages.length > 1 && (
          <button
            className="btn btn-ghost chat-clear"
            type="button"
            onClick={() => setMessages((p) => p.slice(0, 1))}
          >
            clear
          </button>
        )}
      </div>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div aria-live="polite" aria-busy={loading}>
        {messages.map((m) => (
          <div
            key={m.id}
            style={{
              maxWidth: "90%",
              padding: "8px 12px",
              fontSize: 12,
              lineHeight: 1.6,
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              background:
                m.role === "user" ? "var(--elevated)" : "transparent",
              border:
                m.role === "assistant"
                  ? "1px solid var(--border)"
                  : "1px solid var(--border-hi)",
              borderLeft:
                m.role === "assistant"
                  ? "2px solid var(--accent)"
                  : "1px solid var(--border-hi)",
            }}
          >
            {m.role === "assistant" && (
              <span
                style={{
                  fontSize: 9,
                  color: "var(--accent)",
                  letterSpacing: "0.1em",
                  display: "block",
                  marginBottom: 4,
                  textTransform: "uppercase",
                }}
              >
                ▸ evidence answer
              </span>
            )}
            <span style={{ color: "var(--text)" }}>{m.content}</span>
            {m.confidence !== undefined && m.confidence < 0.8 && (
              <div
                style={{
                  fontSize: 10,
                  color: "var(--amber)",
                  marginTop: 4,
                  letterSpacing: "0.08em",
                }}
              >
                ! {Math.round(m.confidence * 100)}% confidence
              </div>
            )}
            {m.clips && m.clips.length > 0 && (
              <div style={{ marginTop: 6 }}>
                {m.clips.map((c, i) => (
                  <a
                    key={i}
                    href={c}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      display: "inline-block",
                      fontSize: 10,
                      color: "var(--accent)",
                      textDecoration: "underline",
                      marginRight: 8,
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                    }}
                  >
                    clip {i + 1} →
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
        </div>
        {messages.length === 1 && !loading && (
          <div className="chat-suggestions" role="group" aria-label="Suggested questions">
            {["what happened today?", "did any packages arrive?", "who was in the garage?"] .map((suggestion) => (
              <button
                key={suggestion}
                className="btn btn-ghost"
                type="button"
                onClick={() => send(suggestion)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
        {loading && (
          <div
            style={{
              fontSize: 11,
              color: "var(--text-dim)",
              letterSpacing: "0.08em",
            }}
          >
            processing...
          </div>
        )}
        {error && <div className="chat-error" role="alert">{error}</div>}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
        style={{
          padding: "10px 12px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          gap: 8,
          flexShrink: 0,
        }}
      >
        <input
          aria-label="Ask about camera history"
          maxLength={1000}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="where are my keys?"
          disabled={loading}
          style={{
            flex: 1,
            padding: "7px 10px",
            fontSize: 12,
            background: "var(--elevated)",
            border: "1px solid var(--border-hi)",
            color: "var(--text)",
          }}
        />
        <button
          className="btn btn-primary"
          type="submit"
          disabled={loading || !input.trim()}
          style={{ padding: "7px 14px" }}
        >
          {loading ? "..." : "ask"}
        </button>
      </form>
    </div>
  );
}
