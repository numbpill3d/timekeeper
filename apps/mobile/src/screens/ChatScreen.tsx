/**
 * Signature feature: natural language query interface.
 * User types or speaks a question; receives a structured answer
 * with optional video clip thumbnails.
 */

import { useState, useRef } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { askQuestion, QueryEvidence } from "../api/client";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  confidence?: number;
  clips?: string[];
  evidence?: QueryEvidence[];
}

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
  const listRef = useRef<FlatList>(null);

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
                    </View>
                  );
                })}
              </View>
            ) : null}
          </View>
        )}
      />

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
