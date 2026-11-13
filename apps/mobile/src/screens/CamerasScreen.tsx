import { useState } from "react";
import { StyleSheet, Text, View, FlatList, Pressable } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Camera, getRetentionPreview, updateCamera } from "../api/client";

export function CamerasScreen() {
  const queryClient = useQueryClient();
  const [mutationError, setMutationError] = useState("");
  const { data, isLoading, isRefetching, isError, refetch } = useQuery({
    queryKey: ["cameras"],
    queryFn: () => api.get<Camera[]>("/cameras").then((r) => r.data),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });
  const { data: retention = [] } = useQuery({
    queryKey: ["retention-preview"],
    queryFn: () => getRetentionPreview().then((r) => r.data),
  });
  const toggle = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      updateCamera(id, isActive),
    onSuccess: () => {
      setMutationError("");
      return queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: () => setMutationError("couldn't update camera status."),
  });

  return (
    <View style={styles.container}>
      {mutationError ? (
        <Text
          style={styles.error}
          accessibilityRole="alert"
          accessibilityLiveRegion="polite"
        >
          {mutationError}
        </Text>
      ) : null}
      <FlatList
        data={data ?? []}
        refreshing={isLoading || isRefetching}
        onRefresh={() => void refetch()}
        ListEmptyComponent={
          isError ? (
            <View style={styles.emptyState}>
              <Text style={styles.empty}>couldn't load cameras.</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Retry loading cameras"
                onPress={() => void refetch()}
                style={styles.retry}
              >
                <Text style={styles.retryText}>retry</Text>
              </Pressable>
            </View>
          ) : (
            <Text style={styles.empty}>no cameras connected yet.</Text>
          )
        }
        keyExtractor={(c) => c.id}
        renderItem={({ item }) => {
          const impact = retention.find((entry) => entry.camera_id === item.id);
          return (
            <View style={styles.card}>
              <Text style={styles.name}>{item.name}</Text>
              <Text style={styles.meta}>
                {item.location_label ?? "no location"} · {item.protocol} · {item.status}
              </Text>
              <View
                accessibilityLabel={`Camera ${item.status}`}
                style={[styles.dot, item.status === "online" ? styles.online : styles.offline]}
              />
              <Text style={styles.health}>
                {item.last_frame_at
                  ? `last frame ${new Date(item.last_frame_at).toLocaleTimeString()}`
                  : "no frame received yet"}
                {item.status === "error" && item.last_error_code
                  ? ` · ${item.last_error_code}`
                  : ""}
                {item.last_frame_width && item.last_frame_height
                  ? ` · ${item.last_frame_width}×${item.last_frame_height}`
                  : ""}
                {item.observed_fps
                  ? ` · ~${item.observed_fps.toFixed(1)} fps`
                  : ""}
              </Text>
              <View
                style={styles.privacy}
                accessibilityLabel={`Privacy and retention for ${item.name}`}
              >
                <Text style={styles.privacyTitle}>privacy &amp; retention</Text>
                <Text style={styles.privacyText}>
                  evidence kept locally for {item.default_retention_days ?? 30} days by default
                </Text>
                <Text style={styles.privacyText}>
                  person-specific retention can override this window
                </Text>
                {impact ? (
                  <Text style={styles.privacyText}>
                    next sweep: {impact.events_expiring} events · {impact.detections_expiring} detections
                  </Text>
                ) : null}
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${item.is_active ? "Pause" : "Resume"} ${item.name}`}
                disabled={toggle.isPending}
                onPress={() => {
                  setMutationError("");
                  toggle.mutate({ id: item.id, isActive: !item.is_active });
                }}
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
          );
        }}
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
  health: { color: "#777", fontSize: 11, marginTop: 4 },
  privacy: {
    backgroundColor: "#171717",
    borderColor: "#333",
    borderWidth: 1,
    marginTop: 10,
    padding: 9,
    gap: 3,
  },
  privacyTitle: { color: "#eee", fontSize: 10, letterSpacing: 0.4 },
  privacyText: { color: "#888", fontSize: 10 },
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
  emptyState: { alignItems: "center", marginTop: 32 },
  empty: { color: "#888", fontSize: 14, textAlign: "center" },
  retry: { borderColor: "#555", borderWidth: 1, marginTop: 12, paddingHorizontal: 12, paddingVertical: 7 },
  retryText: { color: "#ccc", fontSize: 12 },
  error: { color: "#f66", fontSize: 12, marginBottom: 10 },
});
