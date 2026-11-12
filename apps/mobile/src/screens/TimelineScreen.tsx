import { useState } from "react";
import { FlatList, StyleSheet, Text, TextInput, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { listEvents } from "../api/client";
import { EventCard } from "../components/EventCard";

export function TimelineScreen() {
  const [filter, setFilter] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["events", "timeline", filter],
    queryFn: () =>
      listEvents({
        limit: 100,
        event_type: filter || undefined,
      }).then((r) => r.data),
  });

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.search}
        value={filter}
        onChangeText={setFilter}
        placeholder="filter by event type..."
        placeholderTextColor="#555"
      />
      <FlatList
        data={data ?? []}
        refreshing={isLoading}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {isError ? "couldn't load the timeline." : "no matching events."}
          </Text>
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
  search: {
    backgroundColor: "#111",
    color: "#fff",
    borderRadius: 4,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginBottom: 12,
    fontSize: 14,
  },
  sep: { height: 1, backgroundColor: "#111" },
  empty: { color: "#888", fontSize: 14, textAlign: "center", marginTop: 32 },
});
