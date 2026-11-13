import { useEffect, useRef, useState } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import {
  EventStream,
  listEvents,
  openEventStream,
  OmniscientEvent,
} from "../api/client";
import { EventCard } from "../components/EventCard";

export function HomeScreen() {
  const [liveEvents, setLiveEvents] = useState<OmniscientEvent[]>([]);
  const wsRef = useRef<EventStream | null>(null);

  const { data: recentEvents, isLoading, isError } = useQuery({
    queryKey: ["events"],
    queryFn: () => listEvents({ limit: 20 }).then((r) => r.data),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    let disposed = false;
    openEventStream((e) => {
      if (!disposed) setLiveEvents((prev) => [e, ...prev.filter((item) => item.id !== e.id)].slice(0, 5));
    }).then((stream) => {
      if (disposed) stream.close();
      else wsRef.current = stream;
    }).catch(() => {
      // REST polling remains available when the live stream is unavailable.
    });
    return () => {
      disposed = true;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, []);

  const allEvents = Array.from(
    new Map([...liveEvents, ...(recentEvents ?? [])].map((event) => [event.id, event])).values()
  )
    .sort((left, right) => {
      const leftTime = Date.parse(left.timestamp);
      const rightTime = Date.parse(right.timestamp);
      return (Number.isFinite(rightTime) ? rightTime : 0) -
        (Number.isFinite(leftTime) ? leftTime : 0);
    })
    .slice(0, 20);

  return (
    <View style={styles.container}>
      <Text style={styles.header}>recent activity</Text>
      <FlatList
        data={allEvents}
        refreshing={isLoading}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {isError ? "couldn't load activity right now." : "no activity recorded yet."}
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
  header: { color: "#888", fontSize: 12, letterSpacing: 1, marginBottom: 12 },
  sep: { height: 1, backgroundColor: "#111" },
  empty: { color: "#888", fontSize: 14, textAlign: "center", marginTop: 32 },
});
