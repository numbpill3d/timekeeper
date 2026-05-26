import { useEffect, useState } from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import * as SecureStore from "expo-secure-store";

import { setUnauthorizedCallback } from "./src/api/client";
import { CamerasScreen } from "./src/screens/CamerasScreen";
import { ChatScreen } from "./src/screens/ChatScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { LoginScreen } from "./src/screens/LoginScreen";
import { TimelineScreen } from "./src/screens/TimelineScreen";

const Tab = createBottomTabNavigator();
const queryClient = new QueryClient();

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    SecureStore.getItemAsync("access_token").then((t) => setAuthed(!!t));
    setUnauthorizedCallback(() => {
      queryClient.clear();
      setAuthed(false);
    });
  }, []);

  if (authed === null) return null;

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
