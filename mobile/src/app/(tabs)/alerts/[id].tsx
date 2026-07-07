import { useCallback, useEffect, useState } from 'react';
import {
  Alert as RNAlert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { KeyValue, SectionHeader } from '@/components/KeyValue';
import { ErrorState, LoadingView } from '@/components/States';
import api from '@/lib/api';
import { formatDateTime, humanize } from '@/lib/format';
import { severityColor, stateColor } from '@/lib/labels';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { Alert } from '@/lib/types';

export default function AlertDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [alert, setAlert] = useState<Alert | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [updating, setUpdating] = useState<string | null>(null);

  const load = useCallback(
    async ({ refreshing = false } = {}) => {
      if (refreshing) setIsRefreshing(true);
      try {
        const res = await api.get(`/api/alerts/${id}/`);
        setAlert(res.data);
        setError(null);
      } catch (err: any) {
        setError(err?.response?.data?.detail ?? 'Could not load alert.');
      } finally {
        setIsRefreshing(false);
      }
    },
    [id],
  );

  useEffect(() => {
    load();
  }, [load]);

  async function setState(state: string) {
    setUpdating(state);
    try {
      await api.patch(`/api/alerts/${id}/`, { state });
      await load();
    } catch (err: any) {
      RNAlert.alert('Update failed', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setUpdating(null);
    }
  }

  if (error) return <ErrorState message={error} />;
  if (!alert) return <LoadingView />;

  const sourceRefEntries = Object.entries(alert.source_ref ?? {}).slice(0, 20);

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={() => load({ refreshing: true })} tintColor={colors.muted} />
      }
      contentContainerStyle={styles.content}
    >
      <Stack.Screen options={{ title: alert.display_id }} />
      <Text style={styles.title}>{alert.title}</Text>
      <View style={styles.badges}>
        <Badge label={alert.severity} color={severityColor(alert.severity)} />
        <Badge label={alert.state} color={stateColor(alert.state)} />
        <Badge label={humanize(alert.source_kind)} />
      </View>

      {alert.description ? (
        <>
          <SectionHeader title="Description" />
          <Card>
            <Text style={styles.body}>{alert.description}</Text>
          </Card>
        </>
      ) : null}

      <SectionHeader title="Details" />
      <Card>
        <KeyValue label="Organisation" value={alert.org_slug} />
        <KeyValue label="TLP / PAP" value={`${alert.tlp} / ${alert.pap}`} />
        <KeyValue label="Created" value={formatDateTime(alert.created_at)} />
        {alert.acknowledged_at ? (
          <KeyValue label="Acknowledged" value={formatDateTime(alert.acknowledged_at)} />
        ) : null}
        {alert.incident_display_id ? (
          <KeyValue label="Incident">
            <Text
              style={styles.link}
              onPress={() =>
                router.push({
                  pathname: '/incidents/[id]',
                  params: { id: alert.incident_display_id! },
                })
              }
            >
              {alert.incident_display_id}
            </Text>
          </KeyValue>
        ) : null}
      </Card>

      {sourceRefEntries.length > 0 && (
        <>
          <SectionHeader title="Source data" />
          <Card>
            {sourceRefEntries.map(([key, value]) => (
              <KeyValue
                key={key}
                label={key}
                value={typeof value === 'object' ? JSON.stringify(value) : String(value)}
              />
            ))}
          </Card>
        </>
      )}

      <SectionHeader title="Actions" />
      <View style={styles.actions}>
        {alert.state === 'new' && (
          <Button
            title="Acknowledge"
            loading={updating === 'acknowledged'}
            onPress={() => setState('acknowledged')}
            style={styles.actionButton}
          />
        )}
        {alert.state !== 'ignored' && (
          <Button
            title="Ignore"
            variant="secondary"
            loading={updating === 'ignored'}
            onPress={() => setState('ignored')}
            style={styles.actionButton}
          />
        )}
        {alert.state === 'ignored' && (
          <Button
            title="Restore"
            variant="secondary"
            loading={updating === 'new'}
            onPress={() => setState('new')}
            style={styles.actionButton}
          />
        )}
      </View>
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
  title: {
    color: colors.foreground,
    fontSize: fontSize.lg,
    fontWeight: '700',
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
  },
  body: {
    color: colors.foreground,
    fontSize: fontSize.sm,
    lineHeight: 20,
  },
  link: {
    color: colors.primary,
    fontSize: fontSize.sm,
    fontWeight: '600',
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  actionButton: {
    flexGrow: 1,
    minWidth: '45%',
  },
});
