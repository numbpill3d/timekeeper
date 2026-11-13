import { useState } from "react";
import {
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useQuery } from "@tanstack/react-query";
import { listEvents } from "../api/client";
import { EventCard } from "../components/EventCard";

const EVENT_TYPES = [
  "person_entered",
  "person_exited",
  "person_detected",
  "object_placed",
  "object_picked_up",
  "object_moved",
  "door_opened",
  "door_closed",
  "package_delivered",
  "intrusion_detected",
  "unknown_person",
  "fall_detected",
] as const;

export function TimelineScreen() {
  const [filter, setFilter] = useState("");

  const { data, isLoading, isRefetching, isError, refetch } = useQuery({
    queryKey: ["events", "timeline", filter],
    queryFn: () =>
      listEvents({
        limit: 100,
        event_type: filter || undefined,
      }).then((r) => r.data),
  });

  return (
    <View style={styles.container}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filters}
        accessibilityLabel="Event type filters"
      >
        {["", ...EVENT_TYPES].map((eventType) => {
          const selected = filter === eventType;
          return (
            <Pressable
              key={eventType || "all"}
              accessibilityRole="button"
              accessibilityLabel={eventType ? `Filter ${eventType.replaceAll("_", " ")}` : "Show all events"}
              accessibilityState={{ selected }}
              onPress={() => setFilter(eventType)}
              style={[styles.filter, selected && styles.filterSelected]}
            >
              <Text style={[styles.filterText, selected && styles.filterTextSelected]}>
                {eventType ? eventType.replaceAll("_", " ") : "all"}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
      <FlatList
        data={data ?? []}
        refreshing={isLoading || isRefetching}
        onRefresh={() => void refetch()}
        ListEmptyComponent={
          isError ? (
            <View style={styles.emptyState}>
              <Text style={styles.empty}>couldn't load the timeline.</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Retry loading timeline"
                onPress={() => void refetch()}
                style={styles.retry}
              >
                <Text style={styles.retryText}>retry</Text>
              </Pressable>
            </View>
          ) : (
            <Text style={styles.empty}>no matching events.</Text>
          )
        }
        keyExtractor={(e) => e.id}
        renderItem={({ item }) => <EventCard event={item} />}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  filters: { gap: 8, paddingBottom: 12 },
  filter: {
    borderColor: "#333",
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  filterSelected: { backgroundColor: "#c00", borderColor: "#c00" },
  filterText: { color: "#888", fontSize: 11 },
  filterTextSelected: { color: "#fff" },
  sep: { height: 1, backgroundColor: "#111" },
  emptyState: { alignItems: "center", marginTop: 32 },
  empty: { color: "#888", fontSize: 14, textAlign: "center" },
  retry: { borderColor: "#555", borderWidth: 1, marginTop: 12, paddingHorizontal: 12, paddingVertical: 7 },
  retryText: { color: "#ccc", fontSize: 12 },
});
