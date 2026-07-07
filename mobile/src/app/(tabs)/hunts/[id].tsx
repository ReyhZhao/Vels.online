import { useCallback, useEffect, useRef, useState } from 'react';
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
import { humanize, timeAgo } from '@/lib/format';
import { stateColor } from '@/lib/labels';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { Hunt } from '@/lib/types';

const IN_FLIGHT = ['created', 'scoping', 'scoping_running', 'running'];
const POLL_MS = 4000;

export default function HuntDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [hunt, setHunt] = useState<Hunt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [confirmingOrg, setConfirmingOrg] = useState<number | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(
    async ({ refreshing = false } = {}) => {
      if (refreshing) setIsRefreshing(true);
      try {
        const res = await api.get(`/api/hunts/${id}/`);
        setHunt(res.data);
        setError(null);
      } catch (err: any) {
        setError(err?.response?.data?.detail ?? 'Could not load hunt.');
      } finally {
        setIsRefreshing(false);
      }
    },
    [id],
  );

  useEffect(() => {
    load();
  }, [load]);

  // Poll while the hunt is in flight so the event feed and findings fill in live.
  useEffect(() => {
    if (hunt && IN_FLIGHT.includes(hunt.status)) {
      pollRef.current = setInterval(() => load(), POLL_MS);
      return () => {
        if (pollRef.current) clearInterval(pollRef.current);
      };
    }
    return undefined;
  }, [hunt?.status, load]);

  async function cancelHunt() {
    setCancelling(true);
    try {
      await api.post(`/api/hunts/${id}/cancel/`);
      await load();
    } catch (err: any) {
      RNAlert.alert('Cancel failed', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setCancelling(false);
    }
  }

  async function confirmIncident(organizationId: number) {
    setConfirmingOrg(organizationId);
    try {
      const res = await api.post(`/api/hunts/${id}/confirm-incident/`, {
        organization_id: organizationId,
      });
      const displayId = res.data.incident_display_id;
      await load();
      RNAlert.alert('Incident created', displayId, [
        { text: 'Stay here', style: 'cancel' },
        {
          text: 'Open incident',
          onPress: () => router.push({ pathname: '/incidents/[id]', params: { id: displayId } }),
        },
      ]);
    } catch (err: any) {
      RNAlert.alert('Confirm failed', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setConfirmingOrg(null);
    }
  }

  if (error) return <ErrorState message={error} />;
  if (!hunt) return <LoadingView />;

  const inFlight = IN_FLIGHT.includes(hunt.status);
  const narrativeEvents = (hunt.events ?? []).filter(
    (event) => typeof event.data?.text === 'string' && event.data.text,
  );

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={() => load({ refreshing: true })} tintColor={colors.muted} />
      }
      contentContainerStyle={styles.content}
    >
      <Stack.Screen options={{ title: hunt.title || 'Hunt' }} />
      <Text style={styles.title}>{hunt.title || 'Untitled hunt'}</Text>
      <View style={styles.badges}>
        <Badge label={hunt.status} color={stateColor(hunt.status)} />
        <Badge label={hunt.scope_all_orgs ? 'All orgs' : 'Scoped'} />
        <Badge label={`${hunt.lookback_days}d lookback`} />
      </View>

      {hunt.seed_text ? (
        <>
          <SectionHeader title="Hunting for" />
          <Card>
            <Text style={styles.body}>{hunt.seed_text}</Text>
          </Card>
        </>
      ) : null}

      {hunt.plan ? (
        <>
          <SectionHeader title="Plan" />
          <Card>
            <Text style={styles.body}>{hunt.plan}</Text>
          </Card>
        </>
      ) : null}

      {narrativeEvents.length > 0 && (
        <>
          <SectionHeader title="Activity" />
          {narrativeEvents.slice(-12).map((event) => (
            <Card key={event.seq}>
              <View style={styles.eventHeader}>
                <Text style={styles.eventType}>{humanize(event.type)}</Text>
                <Text style={styles.time}>{timeAgo(event.created_at)}</Text>
              </View>
              <Text style={styles.body}>{String(event.data.text)}</Text>
            </Card>
          ))}
        </>
      )}

      {(hunt.proposed_incidents ?? []).length > 0 && (
        <>
          <SectionHeader title="Proposed incidents" />
          {hunt.proposed_incidents!.map((proposal) => (
            <Card key={proposal.organization_id}>
              <Text style={styles.proposalTitle}>{proposal.organization_name}</Text>
              <Text style={styles.metaText}>
                {proposal.finding_count} finding{proposal.finding_count === 1 ? '' : 's'}
              </Text>
              <Button
                title="Confirm incident"
                loading={confirmingOrg === proposal.organization_id}
                onPress={() => confirmIncident(proposal.organization_id)}
                style={styles.confirmButton}
              />
            </Card>
          ))}
        </>
      )}

      {(hunt.findings ?? []).length > 0 && (
        <>
          <SectionHeader title={`Findings (${hunt.findings!.length})`} />
          {hunt.findings!.map((finding) => (
            <Card key={finding.id}>
              <View style={styles.eventHeader}>
                <Text style={styles.eventType}>{finding.organization_name}</Text>
                {finding.materialised_incident_display_id ? (
                  <Badge label={finding.materialised_incident_display_id} color={colors.success} />
                ) : null}
              </View>
              <Text style={styles.body} numberOfLines={4}>
                {finding.summary}
              </Text>
              <Text style={styles.metaText}>{finding.source_index}</Text>
            </Card>
          ))}
        </>
      )}

      {inFlight && (
        <View style={styles.actions}>
          <KeyValue label="The hunt is running — this screen refreshes automatically." />
          <Button title="Cancel hunt" variant="destructive" loading={cancelling} onPress={cancelHunt} />
        </View>
      )}
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
  eventHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  eventType: {
    color: colors.primary,
    fontSize: fontSize.xs,
    fontWeight: '700',
  },
  time: {
    color: colors.muted,
    fontSize: fontSize.xs,
  },
  proposalTitle: {
    color: colors.foreground,
    fontSize: fontSize.md,
    fontWeight: '600',
  },
  metaText: {
    color: colors.muted,
    fontSize: fontSize.xs,
    marginTop: 2,
  },
  confirmButton: {
    marginTop: spacing.md,
  },
  actions: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    gap: spacing.sm,
  },
});
