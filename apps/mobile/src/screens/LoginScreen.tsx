import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as SecureStore from "expo-secure-store";
import { login, register } from "../api/client";

interface Props {
  onAuth: () => void;
}

export function LoginScreen({ onAuth }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    if (!email || !password || loading) return;
    setError("");
    setLoading(true);
    try {
      const fn = mode === "login" ? login : register;
      const { data } = await fn(email, password);
      await SecureStore.setItemAsync("access_token", data.access_token);
      onAuth();
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;
      setError(detail ?? "something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.box}>
        <Text style={styles.brand}>OMNISCIENT</Text>
        <Text style={styles.sub}>home intelligence</Text>

        <TextInput
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          placeholder="email"
          placeholderTextColor="#555"
          autoCapitalize="none"
          keyboardType="email-address"
          autoComplete="email"
        />
        <TextInput
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          placeholder="password"
          placeholderTextColor="#555"
          secureTextEntry
          onSubmitEditing={submit}
          returnKeyType="done"
        />

        {error ? <Text style={styles.error}>! {error}</Text> : null}

        <Pressable
          style={[styles.btn, loading && styles.btnDisabled]}
          onPress={submit}
          disabled={loading}
        >
          <Text style={styles.btnText}>
            {loading ? "..." : mode === "login" ? "sign in" : "create account"}
          </Text>
        </Pressable>

        <Pressable
          onPress={() => {
            setMode((m) => (m === "login" ? "register" : "login"));
            setError("");
          }}
        >
          <Text style={styles.toggle}>
            {mode === "login"
              ? "no account? register"
              : "have an account? sign in"}
          </Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#000",
    justifyContent: "center",
    alignItems: "center",
    padding: 24,
  },
  box: {
    width: "100%",
    maxWidth: 360,
    backgroundColor: "#0a0a0a",
    borderWidth: 1,
    borderColor: "#1a1a1a",
    padding: 28,
    gap: 12,
  },
  brand: {
    color: "#c00",
    fontSize: 18,
    fontWeight: "bold",
    letterSpacing: 4,
    marginBottom: 2,
  },
  sub: { color: "#444", fontSize: 11, letterSpacing: 1, marginBottom: 8 },
  input: {
    backgroundColor: "#111",
    borderWidth: 1,
    borderColor: "#222",
    color: "#fff",
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
  },
  error: { color: "#c00", fontSize: 12 },
  btn: {
    backgroundColor: "#c00",
    paddingVertical: 12,
    alignItems: "center",
    marginTop: 4,
  },
  btnDisabled: { backgroundColor: "#600" },
  btnText: { color: "#fff", fontWeight: "bold", letterSpacing: 1 },
  toggle: {
    color: "#555",
    fontSize: 12,
    textAlign: "center",
    marginTop: 4,
  },
});
