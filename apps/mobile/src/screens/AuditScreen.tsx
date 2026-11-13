import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { listAuditLog, AuditRecord } from "../api/client";

export function AuditScreen() {
  const { data = [], isLoading, isRefetching, isError, refetch } = useQuery({
    queryKey: ["audit-log"],
    queryFn: () => listAuditLog().then((r) => r.data),
  });

  return (
    <View style={styles.container}>
      <Text style={styles.intro}>
        Destructive actions are recorded for this account. Raw evidence is not copied into the audit log.
      </Text>
      <FlatList
        data={data}
        refreshing={isLoading || isRefetching}
        onRefresh={() => void refetch()}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={
          isError ? (
            <View style={styles.emptyState}>
              <Text style={styles.empty}>couldn't load audit history.</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Retry loading audit history"
                onPress={() => void refetch()}
                style={styles.retry}
              >
                <Text style={styles.retryText}>retry</Text>
              </Pressable>
            </View>
          ) : (
            <Text style={styles.empty}>no destructive actions recorded.</Text>
          )
        }
        renderItem={({ item }) => <AuditRow item={item} />}
        ItemSeparatorComponent={() => <View style={styles.separator} />}
      />
    </View>
  );
}

function AuditRow({ item }: { item: AuditRecord }) {
  return (
    <View style={styles.row}>
      <Text style={styles.action}>{item.action} {item.resource_type}</Text>
      <Text style={styles.meta}>
        {new Date(item.created_at).toLocaleString()}
        {item.resource_id ? ` · ${item.resource_id.slice(0, 8)}...` : ""}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#000", padding: 16 },
  intro: { color: "#888", fontSize: 12, lineHeight: 18, marginBottom: 14 },
  row: { borderLeftColor: "#555", borderLeftWidth: 2, paddingVertical: 9, paddingHorizontal: 10 },
  action: { color: "#fff", fontSize: 13 },
  meta: { color: "#777", fontSize: 11, marginTop: 3 },
  separator: { height: 1, backgroundColor: "#111" },
  emptyState: { alignItems: "center", marginTop: 32 },
  empty: { color: "#888", fontSize: 14, textAlign: "center" },
  retry: { borderColor: "#555", borderWidth: 1, marginTop: 12, paddingHorizontal: 12, paddingVertical: 7 },
  retryText: { color: "#ccc", fontSize: 12 },
});
