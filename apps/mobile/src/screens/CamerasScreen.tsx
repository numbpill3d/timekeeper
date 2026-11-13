import { StyleSheet, Text, View, FlatList } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

interface Camera {
  id: string;
  name: string;
  protocol: string;
  location_label: string | null;
  is_active: boolean;
}

export function CamerasScreen() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => api.get<Camera[]>("/cameras").then((r) => r.data),
  });

  return (
    <View style={styles.container}>
      <FlatList
        data={data ?? []}
        refreshing={isLoading}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {isError ? "couldn't load cameras." : "no cameras connected yet."}
          </Text>
        }
        keyExtractor={(c) => c.id}
        renderItem={({ item }) => (
          <View style={styles.card}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.meta}>
              {item.location_label ?? "no location"} · {item.protocol} · {item.is_active ? "active" : "paused"}
            </Text>
            <View
              accessibilityLabel={item.is_active ? "Camera active" : "Camera paused"}
              style={[styles.dot, item.is_active ? styles.online : styles.offline]}
            />
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  card: {
    backgroundColor: "#111",
    borderRadius: 4,
    padding: 14,
    marginBottom: 8,
  },
  name: { color: "#fff", fontSize: 15, fontWeight: "600" },
  meta: { color: "#888", fontSize: 12, marginTop: 2 },
  dot: { width: 8, height: 8, borderRadius: 4, marginTop: 8 },
  online: { backgroundColor: "#0c0" },
  offline: { backgroundColor: "#600" },
  empty: { color: "#888", fontSize: 14, textAlign: "center", marginTop: 32 },
});
