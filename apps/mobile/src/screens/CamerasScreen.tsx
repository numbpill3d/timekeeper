import { StyleSheet, Text, View, FlatList, Pressable } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Camera, updateCamera } from "../api/client";

export function CamerasScreen() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => api.get<Camera[]>("/cameras").then((r) => r.data),
  });
  const toggle = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      updateCamera(id, isActive),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
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
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`${item.is_active ? "Pause" : "Resume"} ${item.name}`}
              disabled={toggle.isPending && toggle.variables?.id === item.id}
              onPress={() =>
                toggle.mutate({ id: item.id, isActive: !item.is_active })
              }
              style={styles.action}
            >
              <Text style={styles.actionText}>
                {toggle.isPending && toggle.variables?.id === item.id
                  ? "updating..."
                  : item.is_active
                    ? "pause camera"
                    : "resume camera"}
              </Text>
            </Pressable>
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
  action: {
    alignSelf: "flex-start",
    borderColor: "#555",
    borderWidth: 1,
    marginTop: 10,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  actionText: { color: "#ccc", fontSize: 12 },
  empty: { color: "#888", fontSize: 14, textAlign: "center", marginTop: 32 },
});
