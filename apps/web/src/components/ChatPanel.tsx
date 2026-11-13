import { useEffect, useRef, useState } from "react";
import { askQuestion, describeQueryError, QueryEvidence, redactEvent } from "../api/client";

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  confidence?: number;
  clips?: string[];
  evidence?: QueryEvidence[];
}

const SAVED_QUESTIONS_KEY = "timekeeper_saved_questions";
const MAX_SAVED_QUESTIONS = 12;

function loadSavedQuestions(): string[] {
  try {
    const raw = localStorage.getItem(SAVED_QUESTIONS_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((question): question is string => typeof question === "string")
      .map((question) => question.trim())
      .filter(Boolean)
      .filter((question, index, questions) => questions.indexOf(question) === index)
      .slice(0, MAX_SAVED_QUESTIONS);
  } catch {
    return [];
  }
}

function evidenceTime(timestamp: string | null): string {
  if (!timestamp) return "unknown time";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? "unknown time"
    : new Intl.DateTimeFormat(undefined, {
        month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
      }).format(date);
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
  const [failedQuestion, setFailedQuestion] = useState("");
  const [savedQuestions, setSavedQuestions] = useState<string[]>(loadSavedQuestions);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollTimerRef = useRef<number | null>(null);
  const copyTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (scrollTimerRef.current !== null) {
        window.clearTimeout(scrollTimerRef.current);
      }
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(SAVED_QUESTIONS_KEY, JSON.stringify(savedQuestions));
    } catch {
      // Storage can be unavailable in private or restricted browser contexts.
    }
  }, [savedQuestions]);

  const history = messages.slice(-6).map((m) => ({
    role: m.role,
    content: m.content,
  }));

  async function send(question = input) {
    const q = question.trim();
    if (!q || loading) return;
    setInput("");
    setError("");
    setFailedQuestion("");

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
          evidence: data.evidence,
        },
      ]);
    } catch (err) {
      setError(describeQueryError(err));
      setFailedQuestion(q);
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

  async function copyAnswer(id: number, content: string) {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(id);
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
      copyTimerRef.current = window.setTimeout(() => {
        copyTimerRef.current = null;
        setCopiedId(null);
      }, 1800);
    } catch {
      setError("could not copy the answer — check browser clipboard permissions.");
    }
  }

  async function redactEvidence(messageId: number, eventId: string) {
    if (!window.confirm("Permanently remove this evidence event and its clip?")) return;
    try {
      await redactEvent(eventId);
      setMessages((current) => current.map((message) => {
        if (message.id !== messageId) return message;
        const redactedClip = message.evidence?.find((item) => item.event_id === eventId)?.clip_url;
        return {
          ...message,
          evidence: message.evidence?.filter((item) => item.event_id !== eventId),
          clips: redactedClip
            ? message.clips?.filter((clip) => clip !== redactedClip)
            : message.clips,
        };
      }));
      setError("");
    } catch {
      setError("couldn't redact that evidence; it was left unchanged.");
    }
  }

  function saveQuestion(question = input) {
    const q = question.trim();
    if (!q) return;
    setSavedQuestions((current) => [q, ...current.filter((item) => item !== q)].slice(0, MAX_SAVED_QUESTIONS));
  }

  function removeSavedQuestion(question: string) {
    setSavedQuestions((current) => current.filter((item) => item !== question));
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
            <div className="chat-answer-line">
              <span style={{ color: "var(--text)" }}>{m.content}</span>
              {m.role === "assistant" && (
                <button
                  className="btn btn-ghost chat-copy"
                  type="button"
                  aria-label="Copy evidence answer"
                  onClick={() => void copyAnswer(m.id, m.content)}
                >
                  {copiedId === m.id ? "copied" : "copy"}
                </button>
              )}
            </div>
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
            {m.role === "assistant" && m.confidence === 0 && !m.evidence?.length && (
              <div
                role="status"
                style={{
                  fontSize: 10,
                  color: "var(--text-dim)",
                  marginTop: 5,
                }}
              >
                no matching recorded evidence was returned
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
            {m.evidence && m.evidence.length > 0 && (
              <div className="query-evidence" aria-label="Supporting evidence">
                <div className="query-evidence-title">supporting evidence</div>
                {m.evidence.map((item, index) => {
                  const itemName = item.object_label ?? item.object_category;
                  const cameraDetails = item.from_camera_name && item.to_camera_name
                    ? `${item.from_camera_name} → ${item.to_camera_name}`
                    : item.camera_name;
                  const details = [
                    item.person_label,
                    itemName,
                    item.location_label,
                    cameraDetails,
                  ]
                    .filter(Boolean)
                    .join(" · ");
                  const confidence = item.confidence == null
                    ? null
                    : `${Math.round(item.confidence * 100)}% evidence confidence`;
                  return (
                    <div className="query-evidence-row" key={`${m.id}-evidence-${index}`}>
                      <span>{evidenceTime(item.timestamp)}</span>
                      <span>{item.action_label ?? item.event_type ?? "activity"}</span>
                      {details && <span>{details}</span>}
                      {confidence && <span className="query-evidence-confidence">{confidence}</span>}
                      {item.clip_url && (
                        <a href={item.clip_url} target="_blank" rel="noreferrer">
                          verify →
                        </a>
                      )}
                      {item.event_id && (
                        <button
                          className="btn btn-ghost"
                          type="button"
                          style={{ padding: "1px 4px", fontSize: 9 }}
                          aria-label="Redact supporting evidence"
                          onClick={() => void redactEvidence(m.id, item.event_id!)}
                        >
                          redact
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
        </div>
        {messages.length === 1 && !loading && (
          <div className="chat-suggestion-groups">
            {savedQuestions.length > 0 && (
              <div className="chat-suggestions" role="group" aria-label="Saved questions">
                <span className="chat-suggestion-label">saved</span>
                {savedQuestions.map((question) => (
                  <span className="chat-saved-question" key={question}>
                    <button className="btn btn-ghost" type="button" onClick={() => void send(question)}>
                      {question}
                    </button>
                    <button
                      className="chat-remove-saved"
                      type="button"
                      aria-label={`Remove saved question: ${question}`}
                      onClick={() => removeSavedQuestion(question)}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="chat-suggestions" role="group" aria-label="Suggested questions">
              <span className="chat-suggestion-label">try asking</span>
              {["what happened today?", "did any packages arrive?", "who was in the garage?"] .map((suggestion) => (
                <button
                  key={suggestion}
                  className="btn btn-ghost"
                  type="button"
                  onClick={() => void send(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
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
        {error && (
          <div className="chat-error" role="alert">
            <span>{error}</span>
            {failedQuestion && (
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => void send(failedQuestion)}
                disabled={loading}
              >
                retry
              </button>
            )}
          </div>
        )}
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
        <button
          className="btn btn-ghost chat-save"
          type="button"
          aria-label="Save question"
          onClick={() => saveQuestion()}
          disabled={loading || !input.trim()}
        >
          save
        </button>
      </form>
    </div>
  );
}
