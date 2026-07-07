import { useState } from 'react';
import {
  Image,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { WebView } from 'react-native-webview';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { registerForPushNotifications } from '@/notifications/push';
import { Button } from '@/components/Button';
import { getServerUrl, saveServerUrl } from '@/lib/server';
import { colors, fontSize, radius, spacing } from '@/lib/theme';

/**
 * Sign-in flow: the backend authenticates via allauth (OIDC SSO) with Django
 * session cookies, so we run the whole login inside a WebView that shares its
 * cookie store with the app's networking layer (sharedCookiesEnabled on iOS;
 * Android WebView cookies are shared with React Native's fetch natively).
 * Once the session lands on /login-redirect/ we re-check /api/me/.
 */
export default function LoginScreen() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [serverInput, setServerInput] = useState(getServerUrl());
  const [showWebView, setShowWebView] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function completeIfAuthenticated(): Promise<boolean> {
    const user = await refresh();
    if (user) {
      registerForPushNotifications().catch(() => {});
      router.replace('/(tabs)/incidents');
      return true;
    }
    return false;
  }

  async function handleConnect() {
    setError(null);
    setChecking(true);
    try {
      await saveServerUrl(serverInput);
      // An existing session (or DEV_AUTO_LOGIN in local dev) skips the SSO round-trip.
      if (await completeIfAuthenticated()) return;
      setShowWebView(true);
    } catch {
      setError('Could not reach the server. Check the URL and try again.');
    } finally {
      setChecking(false);
    }
  }

  async function handleNavigationChange(url: string) {
    if (url.includes('/login-redirect') || /\/(dashboard|incidents)/.test(url)) {
      if (await completeIfAuthenticated()) return;
    }
  }

  if (showWebView) {
    return (
      <SafeAreaView style={styles.container}>
        <WebView
          source={{ uri: `${getServerUrl()}/auth/login/` }}
          sharedCookiesEnabled
          incognito={false}
          onNavigationStateChange={(navState) => handleNavigationChange(navState.url)}
          style={styles.webview}
        />
        <View style={styles.webviewFooter}>
          <Button title="Cancel" variant="secondary" onPress={() => setShowWebView(false)} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.form}
      >
        <Image source={require('@/assets/images/icon.png')} style={styles.logo} />
        <Text style={styles.title}>Vels Online</Text>
        <Text style={styles.subtitle}>Security Operations</Text>

        <Text style={styles.label}>Server</Text>
        <TextInput
          style={styles.input}
          value={serverInput}
          onChangeText={setServerInput}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="https://vels.online"
          placeholderTextColor={colors.muted}
          testID="server-input"
        />
        {error && <Text style={styles.error}>{error}</Text>}
        <Button title="Sign in" onPress={handleConnect} loading={checking} style={styles.button} />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  form: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  logo: {
    width: 72,
    height: 72,
    borderRadius: 16,
    alignSelf: 'center',
    marginBottom: spacing.md,
  },
  title: {
    color: colors.foreground,
    fontSize: fontSize.xl,
    fontWeight: '700',
    textAlign: 'center',
  },
  subtitle: {
    color: colors.muted,
    fontSize: fontSize.sm,
    textAlign: 'center',
    marginBottom: spacing.xl * 2,
  },
  label: {
    color: colors.muted,
    fontSize: fontSize.sm,
    marginBottom: spacing.xs,
  },
  input: {
    backgroundColor: colors.secondary,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius,
    color: colors.foreground,
    fontSize: fontSize.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    marginBottom: spacing.lg,
  },
  error: {
    color: colors.destructive,
    fontSize: fontSize.sm,
    marginBottom: spacing.md,
  },
  button: {
    marginTop: spacing.sm,
  },
  webview: {
    flex: 1,
  },
  webviewFooter: {
    padding: spacing.md,
    backgroundColor: colors.background,
  },
});
