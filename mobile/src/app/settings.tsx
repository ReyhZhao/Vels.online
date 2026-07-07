import { useCallback, useEffect, useState } from 'react';
import { Alert as RNAlert, ScrollView, StyleSheet, Switch, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { KeyValue, SectionHeader } from '@/components/KeyValue';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import { getServerUrl } from '@/lib/server';
import { colors, fontSize, spacing } from '@/lib/theme';
import { registerForPushNotifications, unregisterPushToken } from '@/notifications/push';

const PUSH_PREFS: { key: string; label: string }[] = [
  { key: 'push_assignment', label: 'Assignments' },
  { key: 'push_delegation', label: 'Delegations' },
  { key: 'push_comment', label: 'Comments' },
  { key: 'push_state_change', label: 'State changes' },
  { key: 'push_incident_alert', label: 'Incident alerts' },
  { key: 'push_task_complete', label: 'Task completions' },
  { key: 'push_hunt_complete', label: 'Hunt completions' },
  { key: 'push_shift_swap', label: 'Shift swaps' },
];

export default function SettingsScreen() {
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [prefs, setPrefs] = useState<Record<string, boolean> | null>(null);
  const [pushToken, setPushToken] = useState<string | null>(null);
  const [enablingPush, setEnablingPush] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  const loadPrefs = useCallback(async () => {
    try {
      const res = await api.get('/api/me/notification-prefs/');
      setPrefs(res.data);
    } catch {
      setPrefs(null);
    }
  }, []);

  useEffect(() => {
    loadPrefs();
  }, [loadPrefs]);

  async function togglePref(key: string, value: boolean) {
    setPrefs((prev) => (prev ? { ...prev, [key]: value } : prev));
    try {
      await api.patch('/api/me/notification-prefs/', { [key]: value });
    } catch {
      await loadPrefs();
    }
  }

  async function enablePush() {
    setEnablingPush(true);
    try {
      const token = await registerForPushNotifications();
      setPushToken(token);
      if (!token) {
        RNAlert.alert(
          'Push unavailable',
          'Could not register this device — check notification permissions in system settings.',
        );
      }
    } finally {
      setEnablingPush(false);
    }
  }

  async function handleSignOut() {
    setSigningOut(true);
    await unregisterPushToken();
    await signOut();
    router.replace('/login');
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <SectionHeader title="Account" />
      <Card>
        <KeyValue label="Signed in as" value={user?.username} />
        <KeyValue label="Email" value={user?.email} />
        <KeyValue label="Server" value={getServerUrl()} />
      </Card>

      <SectionHeader title="Push notifications" />
      <Card>
        <Text style={styles.help}>
          Enable push on this device, then choose which events reach you.
        </Text>
        <Button
          title={pushToken ? 'Push enabled on this device' : 'Enable push on this device'}
          variant={pushToken ? 'secondary' : 'primary'}
          loading={enablingPush}
          onPress={enablePush}
          style={styles.pushButton}
        />
        {prefs &&
          PUSH_PREFS.map(({ key, label }) => (
            <KeyValue key={key} label={label}>
              <Switch
                value={!!prefs[key]}
                onValueChange={(value) => togglePref(key, value)}
                trackColor={{ true: colors.primary, false: colors.secondary }}
                testID={`pref-${key}`}
              />
            </KeyValue>
          ))}
      </Card>

      <SectionHeader title="Session" />
      <Card>
        <Button
          title="Sign out"
          variant="destructive"
          loading={signingOut}
          onPress={handleSignOut}
        />
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingBottom: spacing.xl,
  },
  help: {
    color: colors.muted,
    fontSize: fontSize.sm,
    marginBottom: spacing.md,
  },
  pushButton: {
    marginBottom: spacing.md,
  },
});
