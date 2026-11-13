import { useState } from "react";
import { Linking, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { formatDistanceToNow } from "date-fns";
import { OmniscientEvent, updateEventAnnotation } from "../api/client";

interface Props {
  event: OmniscientEvent;
  onRedact?: () => void;
  redacting?: boolean;
  allowAnnotation?: boolean;
}

export function EventCard({ event, onRedact, redacting, allowAnnotation }: Props) {
  const [note, setNote] = useState(event.annotation ?? "");
  const [editingNote, setEditingNote] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const ago = formatDistanceToNow(new Date(event.timestamp), {
    addSuffix: true,
  });

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Text style={styles.label} numberOfLines={1}>
          {event.action_label}
        </Text>
        <Text style={styles.time}>{ago}</Text>
      </View>
      {event.location_label && (
        <Text style={styles.loc}>
          {event.camera_name} · {event.location_label}
        </Text>
      )}
      {!event.location_label && (
        <Text style={styles.loc}>{event.camera_name}</Text>
      )}
      {event.person_label && (
        <Text style={styles.tag}>{event.person_label}</Text>
      )}
      {event.object_label && (
        <Text style={styles.object}>{event.object_label}</Text>
      )}
      {event.clip_path && (
        <Pressable
          accessibilityRole="link"
          accessibilityLabel="Open event evidence"
          onPress={() => {
            void Linking.openURL(event.clip_path!).catch(() => undefined);
          }}
        >
          <Text style={styles.clip}>view evidence →</Text>
        </Pressable>
      )}
      {allowAnnotation ? (
        <View style={styles.annotationBlock}>
          {editingNote ? (
            <>
              <TextInput
                accessibilityLabel="Event review note"
                value={note}
                onChangeText={setNote}
                maxLength={2000}
                multiline
                placeholder="Add a review note"
                placeholderTextColor="#666"
                style={styles.noteInput}
              />
              <View style={styles.noteActions}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Save event note"
                  disabled={savingNote}
                  onPress={() => {
                    setSavingNote(true);
                    void updateEventAnnotation(event.id, note.trim() || null)
                      .then(() => setEditingNote(false))
                      .catch(() => undefined)
                      .finally(() => setSavingNote(false));
                  }}
                >
                  <Text style={styles.noteAction}>{savingNote ? "saving..." : "save note"}</Text>
                </Pressable>
                <Pressable accessibilityRole="button" accessibilityLabel="Cancel event note" onPress={() => setEditingNote(false)}>
                  <Text style={styles.noteCancel}>cancel</Text>
                </Pressable>
              </View>
            </>
          ) : (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={note ? "Edit event note" : "Add event note"}
              onPress={() => setEditingNote(true)}
            >
              <Text style={styles.noteText}>{note ? `note: ${note}` : "+ add note"}</Text>
            </Pressable>
          )}
        </View>
      ) : null}
      {onRedact ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`Redact ${event.action_label} event`}
          disabled={redacting}
          onPress={onRedact}
          style={styles.redact}
        >
          <Text style={styles.redactText}>{redacting ? "redacting..." : "redact event"}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { paddingVertical: 10 },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 8,
  },
  label: { color: "#fff", fontSize: 14, flex: 1 },
  time: { color: "#555", fontSize: 11, flexShrink: 0 },
  loc: { color: "#888", fontSize: 12, marginTop: 2 },
  tag: {
    color: "#c00",
    fontSize: 11,
    marginTop: 4,
    fontWeight: "600",
  },
  object: {
    color: "#d99a00",
    fontSize: 11,
    marginTop: 4,
    fontWeight: "600",
  },
  clip: {
    color: "#c00",
    fontSize: 11,
    marginTop: 6,
    textDecorationLine: "underline",
  },
  redact: { alignSelf: "flex-start", marginTop: 8, paddingVertical: 2 },
  redactText: { color: "#777", fontSize: 10, textDecorationLine: "underline" },
  annotationBlock: { marginTop: 7 },
  noteText: { color: "#888", fontSize: 11 },
  noteInput: {
    backgroundColor: "#111", borderColor: "#333", borderWidth: 1, color: "#fff",
    minHeight: 54, paddingHorizontal: 8, paddingVertical: 7, fontSize: 11,
  },
  noteActions: { flexDirection: "row", gap: 12, marginTop: 5 },
  noteAction: { color: "#c00", fontSize: 10, textDecorationLine: "underline" },
  noteCancel: { color: "#777", fontSize: 10, textDecorationLine: "underline" },
});
