import { useEffect, useRef, useState } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { listEvents, openEventStream, OmniscientEvent } from "../api/client";
import { EventCard } from "../components/EventCard";

export function HomeScreen() {
  const [liveEvents, setLiveEvents] = useState<OmniscientEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const { data: recentEvents } = useQuery({
    queryKey: ["events"],
    queryFn: () => listEvents({ limit: 20 }).then((r) => r.data),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    openEventStream((e) => {
      setLiveEvents((prev) => [e, ...prev].slice(0, 5));
    }).then((ws) => {
      wsRef.current = ws;
    });
    return () => wsRef.current?.close();
  }, []);

  const allEvents = [...liveEvents, ...(recentEvents ?? [])].slice(0, 20);

  return (
    <View style={styles.container}>
      <Text style={styles.header}>recent activity</Text>
      <FlatList
        data={allEvents}
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
});
