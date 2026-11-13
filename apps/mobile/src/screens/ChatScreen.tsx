/**
 * Signature feature: natural language query interface.
 * User types or speaks a question; receives a structured answer
 * with optional video clip thumbnails.
 */

import { useEffect, useState, useRef } from "react";
import {
  FlatList,
  Alert,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as Clipboard from "expo-clipboard";
import * as SecureStore from "expo-secure-store";
import { askQuestion, QueryEvidence, redactEvent } from "../api/client";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  confidence?: number;
  clips?: string[];
  evidence?: QueryEvidence[];
}

const SAVED_QUESTIONS_KEY = "timekeeper_saved_questions";
const MAX_SAVED_QUESTIONS = 12;

function evidenceTime(timestamp: string | null): string {
  if (!timestamp) return "unknown time";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? "unknown time"
    : date.toLocaleString(undefined, {
        month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
      });
}

export function ChatScreen() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [queryError, setQueryError] = useState("");
  const [failedQuestion, setFailedQuestion] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copyError, setCopyError] = useState("");
  const [savedQuestions, setSavedQuestions] = useState<string[]>([]);
  const [savedQuestionsLoaded, setSavedQuestionsLoaded] = useState(false);
  const listRef = useRef<FlatList>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
  }, []);

  useEffect(() => {
    let active = true;
    void SecureStore.getItemAsync(SAVED_QUESTIONS_KEY)
      .then((raw) => {
        if (!active) return;
        try {
          const parsed: unknown = raw ? JSON.parse(raw) : [];
          const questions = Array.isArray(parsed)
            ? parsed
                .filter((question): question is string => typeof question === "string")
                .map((question) => question.trim())
                .filter(Boolean)
                .filter((question, index, items) => items.indexOf(question) === index)
                .slice(0, MAX_SAVED_QUESTIONS)
            : [];
          setSavedQuestions(questions);
        } catch {
          setSavedQuestions([]);
        }
        setSavedQuestionsLoaded(true);
      })
      .catch(() => {
        if (active) setSavedQuestionsLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!savedQuestionsLoaded) return;
    void SecureStore.setItemAsync(SAVED_QUESTIONS_KEY, JSON.stringify(savedQuestions)).catch(() => undefined);
  }, [savedQuestions, savedQuestionsLoaded]);

  const history = messages.slice(-6).map((m) => ({
    role: m.role,
    content: m.content,
  }));

  async function send(questionOverride?: string) {
    const question = (questionOverride ?? input).trim();
    if (!question || loading) return;
    setInput("");
    setQueryError("");
    setFailedQuestion("");

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: question,
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const { data } = await askQuestion(question, history);
      const reply: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: data.answer,
        confidence: data.confidence,
        clips: data.clips,
        evidence: data.evidence,
      };
      setMessages((prev) => [...prev, reply]);
    } catch {
      setQueryError("couldn't reach the server right now.");
      setFailedQuestion(question);
    } finally {
      setLoading(false);
      listRef.current?.scrollToEnd({ animated: true });
    }
  }

  async function copyAnswer(id: string, content: string) {
    try {
      await Clipboard.setStringAsync(content);
      setCopyError("");
      setCopiedId(id);
      if (copyTimerRef.current !== null) clearTimeout(copyTimerRef.current);
      copyTimerRef.current = setTimeout(() => {
        copyTimerRef.current = null;
        setCopiedId(null);
      }, 1800);
    } catch {
      setCopyError("couldn't copy the answer to the clipboard.");
    }
  }

  function confirmRedaction(messageId: string, eventId: string) {
    Alert.alert(
      "Redact evidence?",
      "Permanently remove this evidence event and its clip?",
      [
        { text: "cancel", style: "cancel" },
        {
          text: "redact",
          style: "destructive",
          onPress: () => {
            void redactEvent(eventId)
              .then(() => {
                setMessages((current) => current.map((message) => (
                  message.id === messageId
                    ? { ...message, evidence: message.evidence?.filter((item) => item.event_id !== eventId) }
                    : message
                )));
                setQueryError("");
              })
              .catch(() => setQueryError("couldn't redact that evidence; it was left unchanged."));
          },
        },
      ],
    );
  }

  function saveQuestion() {
    const question = input.trim();
    if (!question) return;
    setSavedQuestions((current) => [question, ...current.filter((item) => item !== question)].slice(0, MAX_SAVED_QUESTIONS));
  }

  function removeSavedQuestion(question: string) {
    setSavedQuestions((current) => current.filter((item) => item !== question));
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={90}
    >
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => m.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <View
            style={[
              styles.bubble,
              item.role === "user" ? styles.userBubble : styles.aiBubble,
            ]}
          >
            <Text style={styles.bubbleText}>{item.content}</Text>
            {item.role === "assistant" ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Copy evidence answer"
                onPress={() => void copyAnswer(item.id, item.content)}
              >
                <Text style={copiedId === item.id ? styles.copiedText : styles.copyText}>
                  {copiedId === item.id ? "copied" : "copy answer"}
                </Text>
              </Pressable>
            ) : null}
            {item.confidence !== undefined && item.confidence < 0.8 && (
              <Text style={styles.confidence}>
                {Math.round(item.confidence * 100)}% confidence
              </Text>
            )}
            {item.role === "assistant" && item.confidence === 0 && !item.evidence?.length ? (
              <Text style={styles.noEvidence} accessibilityRole="text">
                no matching recorded evidence was returned
              </Text>
            ) : null}
            {item.clips?.map((clip: string, index: number) => (
              <Pressable
                key={`${item.id}-clip-${index}`}
                accessibilityRole="link"
                accessibilityLabel={`Open evidence clip ${index + 1}`}
                onPress={() => {
                  void Linking.openURL(clip).catch(() => undefined);
                }}
              >
                <Text style={styles.clip}>view evidence {index + 1} →</Text>
              </Pressable>
            ))}
            {item.evidence?.length ? (
              <View style={styles.evidence} accessibilityLabel="Supporting evidence">
                <Text style={styles.evidenceTitle}>supporting evidence</Text>
                {item.evidence.map((evidence: QueryEvidence, index: number) => {
                  const itemName = evidence.object_label ?? evidence.object_category;
                  const details = [
                    evidence.person_label,
                    itemName,
                    evidence.location_label,
                    evidence.camera_name,
                  ]
                    .filter(Boolean)
                    .join(" · ");
                  const confidence = evidence.confidence == null
                    ? ""
                    : ` · ${Math.round(evidence.confidence * 100)}% evidence confidence`;
                  return (
                    <View key={`${item.id}-evidence-${index}`} style={styles.evidenceRow}>
                      <Text style={styles.evidenceText}>
                        {evidenceTime(evidence.timestamp)} · {evidence.action_label ?? evidence.event_type ?? "activity"}{confidence}
                      </Text>
                      {details ? <Text style={styles.evidenceDetail}>{details}</Text> : null}
                      {evidence.clip_url ? (
                        <Pressable
                          accessibilityRole="link"
                          accessibilityLabel={`Verify evidence ${index + 1}`}
                          onPress={() => void Linking.openURL(evidence.clip_url!).catch(() => undefined)}
                        >
                          <Text style={styles.clip}>verify evidence →</Text>
                        </Pressable>
                      ) : null}
                      {evidence.event_id ? (
                        <Pressable
                          accessibilityRole="button"
                          accessibilityLabel="Redact supporting evidence"
                          onPress={() => confirmRedaction(item.id, evidence.event_id!)}
                        >
                          <Text style={styles.redactText}>redact evidence</Text>
                        </Pressable>
                      ) : null}
                    </View>
                  );
                })}
              </View>
            ) : null}
          </View>
        )}
      />

      {savedQuestions.length > 0 ? (
        <View style={styles.savedRow} accessibilityLabel="Saved questions">
          <Text style={styles.savedLabel}>saved</Text>
          {savedQuestions.map((question) => (
            <View style={styles.savedQuestion} key={question}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Ask saved question: ${question}`}
                onPress={() => void send(question)}
                disabled={loading}
              >
                <Text style={styles.savedText} numberOfLines={1}>{question}</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Remove saved question: ${question}`}
                onPress={() => removeSavedQuestion(question)}
                disabled={loading}
              >
                <Text style={styles.removeSavedText}>×</Text>
              </Pressable>
            </View>
          ))}
        </View>
      ) : null}

      {queryError ? (
        <View style={styles.errorRow} accessibilityRole="alert">
          <Text style={styles.errorText}>{queryError}</Text>
          {failedQuestion ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Retry query"
              onPress={() => void send(failedQuestion)}
              disabled={loading}
            >
              <Text style={styles.retryText}>retry</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      {copyError ? (
        <Text style={styles.copyError} accessibilityRole="alert">
          {copyError}
        </Text>
      ) : null}

      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="ask about your home..."
          placeholderTextColor="#555"
          maxLength={1000}
          accessibilityLabel="Ask about camera history"
          onSubmitEditing={() => void send()}
          returnKeyType="send"
          editable={!loading}
        />
        <Pressable
          style={[styles.sendBtn, loading && styles.sendBtnDisabled]}
          onPress={() => void send()}
          disabled={loading}
        >
          <Text style={styles.sendText}>{loading ? "..." : "ask"}</Text>
        </Pressable>
        <Pressable
          style={styles.saveBtn}
          accessibilityRole="button"
          accessibilityLabel="Save question"
          onPress={saveQuestion}
          disabled={loading || !input.trim()}
        >
          <Text style={styles.saveText}>save</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000" },
  list: { padding: 16, gap: 12 },
  bubble: {
    maxWidth: "80%",
    borderRadius: 4,
    padding: 12,
  },
  userBubble: { alignSelf: "flex-end", backgroundColor: "#1a1a1a" },
  aiBubble: {
    alignSelf: "flex-start",
    backgroundColor: "#111",
    borderLeftWidth: 2,
    borderLeftColor: "#e00",
  },
  bubbleText: { color: "#fff", fontSize: 14, lineHeight: 20 },
  confidence: { color: "#888", fontSize: 11, marginTop: 4 },
  noEvidence: { color: "#777", fontSize: 11, marginTop: 5 },
  evidence: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "#282828",
  },
  evidenceTitle: { color: "#c00", fontSize: 10, letterSpacing: 1, marginBottom: 5 },
  evidenceRow: { marginBottom: 7 },
  evidenceText: { color: "#ddd", fontSize: 11, lineHeight: 16 },
  evidenceDetail: { color: "#888", fontSize: 11, lineHeight: 16 },
  clip: {
    color: "#e00",
    fontSize: 11,
    marginTop: 6,
    textDecorationLine: "underline",
  },
  redactText: { color: "#777", fontSize: 10, marginTop: 4, textDecorationLine: "underline" },
  errorRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: "#282828",
  },
  errorText: { color: "#c66", fontSize: 11, flex: 1 },
  retryText: { color: "#ccc", fontSize: 12 },
  copyText: { color: "#888", fontSize: 10, marginTop: 6, textDecorationLine: "underline" },
  copiedText: { color: "#0c0", fontSize: 10, marginTop: 6 },
  copyError: { color: "#c66", fontSize: 11, paddingHorizontal: 12, paddingVertical: 6 },
  savedRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  savedLabel: { color: "#777", fontSize: 10, textTransform: "uppercase" },
  savedQuestion: {
    flexDirection: "row",
    alignItems: "center",
    maxWidth: "82%",
    backgroundColor: "#111",
    borderWidth: 1,
    borderColor: "#282828",
    borderRadius: 4,
  },
  savedText: { color: "#ccc", fontSize: 11, paddingHorizontal: 7, paddingVertical: 5 },
  removeSavedText: { color: "#777", fontSize: 14, paddingHorizontal: 5 },
  saveBtn: { justifyContent: "center", paddingHorizontal: 4 },
  saveText: { color: "#aaa", fontSize: 11 },
  inputRow: {
    flexDirection: "row",
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: "#1a1a1a",
    gap: 8,
  },
  input: {
    flex: 1,
    backgroundColor: "#111",
    color: "#fff",
    borderRadius: 4,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
  },
  sendBtn: {
    backgroundColor: "#c00",
    borderRadius: 4,
    paddingHorizontal: 16,
    justifyContent: "center",
  },
  sendBtnDisabled: { backgroundColor: "#600" },
  sendText: { color: "#fff", fontWeight: "600" },
});
