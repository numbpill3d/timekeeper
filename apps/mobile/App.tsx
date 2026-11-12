import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, StyleSheet, View } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import * as SecureStore from "expo-secure-store";
import * as Notifications from "expo-notifications";

import { setUnauthorizedCallback, updateProfile } from "./src/api/client";
import { CamerasScreen } from "./src/screens/CamerasScreen";
import { ChatScreen } from "./src/screens/ChatScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { LoginScreen } from "./src/screens/LoginScreen";
import { TimelineScreen } from "./src/screens/TimelineScreen";

const Tab = createBottomTabNavigator();
const queryClient = new QueryClient();

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

async function registerPushToken(): Promise<void> {
  if (Platform.OS === "ios") return; // FCM token registration requires APNs config for iOS
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== "granted") return;
  try {
    const { data: token } = await Notifications.getDevicePushTokenAsync();
    if (token) await updateProfile({ fcm_token: token });
  } catch {
    // Firebase not configured in this build — skip silently
  }
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    SecureStore.getItemAsync("access_token").then((t) => setAuthed(!!t));
    setUnauthorizedCallback(() => {
      queryClient.clear();
      setAuthed(false);
    });
  }, []);

  useEffect(() => {
    if (authed) registerPushToken();
  }, [authed]);

  if (authed === null) {
    return (
      <View style={styles.loading} accessibilityLabel="Loading Timekeeper">
        <ActivityIndicator color="#c00" />
      </View>
    );
  }

  if (!authed) {
    return (
      <LoginScreen
        onAuth={() => {
          queryClient.clear();
          setAuthed(true);
        }}
      />
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <NavigationContainer>
        <StatusBar style="light" />
        <Tab.Navigator
          screenOptions={{
            headerStyle: { backgroundColor: "#000" },
            headerTintColor: "#fff",
            tabBarStyle: { backgroundColor: "#000", borderTopColor: "#1a1a1a" },
            tabBarActiveTintColor: "#fff",
            tabBarInactiveTintColor: "#555",
          }}
        >
          <Tab.Screen name="Home" component={HomeScreen} />
          <Tab.Screen name="Chat" component={ChatScreen} />
          <Tab.Screen name="Timeline" component={TimelineScreen} />
          <Tab.Screen name="Cameras" component={CamerasScreen} />
        </Tab.Navigator>
      </NavigationContainer>
    </QueryClientProvider>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#000",
  },
});
