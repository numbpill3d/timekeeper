import { useState } from "react";
import {
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useQuery } from "@tanstack/react-query";
import { listEvents, OmniscientEvent } from "../api/client";
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
const TIME_RANGES = ["", "today", "24h", "7d"] as const;

type TimelineItem =
  | { type: "header"; key: string; label: string; count: number }
  | { type: "event"; key: string; event: OmniscientEvent };

function localDateTimeValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function TimelineScreen() {
  const [filter, setFilter] = useState("");
  const [since, setSince] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading, isRefetching, isError, refetch } = useQuery({
    queryKey: ["events", "timeline", filter, since, search],
    queryFn: () =>
      listEvents({
        limit: 100,
        event_type: filter || undefined,
        since: since || undefined,
        search: search || undefined,
      }).then((r) => r.data),
  });
  const timelineItems = (data ?? []).reduce<TimelineItem[]>((items, event) => {
    const date = new Date(event.timestamp);
    const validDate = !Number.isNaN(date.getTime());
    const key = validDate
      ? `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}-${date.getHours()}`
      : "unknown";
    const current = items[items.length - 1];
    if (current?.type === "header" && current.key === `header-${key}`) {
      current.count += 1;
    } else {
      items.push({
        type: "header",
        key: `header-${key}`,
        label: validDate
          ? date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" })
          : "unknown time",
        count: 1,
      });
    }
    items.push({ type: "event", key: event.id, event });
    return items;
  }, []);

  return (
    <View style={styles.container}>
      <View style={styles.searchRow}>
        <TextInput
          style={styles.searchInput}
          value={searchDraft}
          onChangeText={setSearchDraft}
          onSubmitEditing={() => setSearch(searchDraft.trim())}
          placeholder="person, item, location"
          placeholderTextColor="#555"
          maxLength={120}
          returnKeyType="search"
          accessibilityLabel="Search timeline evidence"
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Search timeline evidence"
          onPress={() => setSearch(searchDraft.trim())}
          style={styles.searchButton}
        >
          <Text style={styles.searchButtonText}>find</Text>
        </Pressable>
        {(search || searchDraft) ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Clear timeline search"
            onPress={() => {
              setSearchDraft("");
              setSearch("");
            }}
            style={styles.clearButton}
          >
            <Text style={styles.clearButtonText}>×</Text>
          </Pressable>
        ) : null}
      </View>
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
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filters}
        accessibilityLabel="Timeline time ranges"
      >
        {TIME_RANGES.map((range) => {
          const selected = since === range;
          return (
            <Pressable
              key={range || "any-time"}
              accessibilityRole="button"
              accessibilityLabel={range ? `Show events from ${range}` : "Show events from any time"}
              accessibilityState={{ selected }}
              onPress={() => {
                if (!range) {
                  setSince("");
                  return;
                }
                const date = new Date();
                if (range === "today") {
                  date.setHours(0, 0, 0, 0);
                } else {
                  date.setHours(date.getHours() - (range === "24h" ? 24 : 24 * 7));
                }
                setSince(localDateTimeValue(date));
              }}
              style={[styles.filter, selected && styles.filterSelected]}
            >
              <Text style={[styles.filterText, selected && styles.filterTextSelected]}>
                {range || "any time"}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
      <FlatList
        data={timelineItems}
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
        keyExtractor={(item) => item.key}
        renderItem={({ item }) => item.type === "header" ? (
          <View style={styles.groupHeader} accessibilityLabel={`${item.label}, ${item.count} events`}>
            <Text style={styles.groupLabel}>{item.label}</Text>
            <Text style={styles.groupCount}>{item.count} {item.count === 1 ? "event" : "events"}</Text>
          </View>
        ) : <EventCard event={item.event} />}
        ItemSeparatorComponent={() => <View style={styles.sep} />}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  filters: { gap: 8, paddingBottom: 12 },
  searchRow: { flexDirection: "row", gap: 6, alignItems: "center", paddingBottom: 10 },
  searchInput: {
    flex: 1,
    backgroundColor: "#111",
    borderColor: "#333",
    borderWidth: 1,
    color: "#fff",
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 12,
  },
  searchButton: { borderColor: "#555", borderWidth: 1, paddingHorizontal: 10, paddingVertical: 8 },
  searchButtonText: { color: "#ccc", fontSize: 11 },
  clearButton: { paddingHorizontal: 3, paddingVertical: 5 },
  clearButtonText: { color: "#888", fontSize: 18 },
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
  groupHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
    paddingHorizontal: 2,
    backgroundColor: "#000",
  },
  groupLabel: { color: "#888", fontSize: 10, textTransform: "uppercase", letterSpacing: 1 },
  groupCount: { color: "#555", fontSize: 10 },
  emptyState: { alignItems: "center", marginTop: 32 },
  empty: { color: "#888", fontSize: 14, textAlign: "center" },
  retry: { borderColor: "#555", borderWidth: 1, marginTop: 12, paddingHorizontal: 12, paddingVertical: 7 },
  retryText: { color: "#ccc", fontSize: 12 },
});
