import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { formatDistanceToNow } from "date-fns";
import { OmniscientEvent } from "../api/client";

interface Props {
  event: OmniscientEvent;
}

export function EventCard({ event }: Props) {
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
});
