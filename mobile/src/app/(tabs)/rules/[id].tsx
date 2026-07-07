import { useCallback, useEffect, useState } from 'react';
import {
  Alert as RNAlert,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { KeyValue, SectionHeader } from '@/components/KeyValue';
import { ErrorState, LoadingView } from '@/components/States';
import api from '@/lib/api';
import { formatDateTime, humanize, timeAgo } from '@/lib/format';
import { severityColor } from '@/lib/labels';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { SearchRule, SearchRuleLeg } from '@/lib/types';

export default function SearchRuleDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [rule, setRule] = useState<SearchRule | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [running, setRunning] = useState(false);
  const [toggling, setToggling] = useState(false);

  const load = useCallback(
    async ({ refreshing = false } = {}) => {
      if (refreshing) setIsRefreshing(true);
      try {
        const res = await api.get(`/api/correlations/search-rules/${id}/`);
        setRule(res.data);
        setError(null);
      } catch (err: any) {
        setError(err?.response?.data?.detail ?? 'Could not load rule.');
      } finally {
        setIsRefreshing(false);
      }
    },
    [id],
  );

  useEffect(() => {
    load();
  }, [load]);

  async function toggleEnabled(value: boolean) {
    if (!rule) return;
    setToggling(true);
    try {
      await api.patch(`/api/correlations/search-rules/${id}/`, { enabled: value });
      await load();
    } catch (err: any) {
      RNAlert.alert('Update failed', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setToggling(false);
    }
  }

  async function runNow() {
    setRunning(true);
    try {
      await api.post(`/api/correlations/search-rules/${id}/run/`);
      RNAlert.alert('Run scheduled', 'The rule has been queued to run now.');
    } catch (err: any) {
      RNAlert.alert('Run failed', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setRunning(false);
    }
  }

  if (error) return <ErrorState message={error} />;
  if (!rule) return <LoadingView />;

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={() => load({ refreshing: true })} tintColor={colors.muted} />
      }
      contentContainerStyle={styles.content}
    >
      <Stack.Screen options={{ title: rule.name }} />
      <Text style={styles.title}>{rule.name}</Text>
      {rule.description ? <Text style={styles.description}>{rule.description}</Text> : null}
      <View style={styles.badges}>
        <Badge label={rule.severity} color={severityColor(rule.severity)} />
        <Badge label={rule.organization === null ? 'System rule' : 'Org rule'} color={colors.purple} />
      </View>

      <SectionHeader title="Configuration" />
      <Card>
        <KeyValue label="Enabled">
          <Switch
            value={rule.enabled}
            onValueChange={toggleEnabled}
            disabled={toggling}
            trackColor={{ true: colors.primary, false: colors.secondary }}
            testID="rule-enabled-switch"
          />
        </KeyValue>
        <KeyValue label="Correlation key" value={humanize(rule.correlation_key)} />
        <KeyValue label="Window" value={`${rule.window_minutes} min`} />
        <KeyValue label="Interval" value={`every ${rule.interval_minutes} min`} />
        <KeyValue label="Updated" value={formatDateTime(rule.updated_at)} />
      </Card>

      <SectionHeader title={`Legs (${rule.legs.length})`} />
      {rule.legs
        .slice()
        .sort((a, b) => a.display_order - b.display_order)
        .map((leg, index) => (
          <Card key={leg.id ?? index}>
            <Text style={styles.legTitle}>
              Leg {index + 1} — {leg.count_operator === 'lte' ? '≤' : '≥'} {leg.count} match
              {leg.count === 1 ? '' : 'es'}
            </Text>
            {leg.conditions.map((condition, conditionIndex) => (
              <Text key={conditionIndex} style={styles.condition}>
                {condition.field_name} {condition.operator} “{condition.value}”
              </Text>
            ))}
            {legConstraintLabel(leg) ? (
              <Text style={styles.constraint}>{legConstraintLabel(leg)}</Text>
            ) : null}
          </Card>
        ))}

      <SectionHeader title="Activity" />
      <Card>
        <KeyValue label="Firings" value={rule.firing_summary.count} />
        <KeyValue
          label="Last fired"
          value={
            rule.firing_summary.last_fired_at ? timeAgo(rule.firing_summary.last_fired_at) : 'never'
          }
        />
        <KeyValue
          label="Rule tests"
          value={
            rule.test_summary.total > 0
              ? `${rule.test_summary.passing}/${rule.test_summary.total} passing`
              : 'none'
          }
        />
      </Card>

      <View style={styles.actions}>
        <Button title="Run now" onPress={runNow} loading={running} />
      </View>
    </ScrollView>
  );
}

function legConstraintLabel(leg: SearchRuleLeg): string | null {
  if (leg.distinct_field && leg.min_distinct) {
    return `Diversity: ≥ ${leg.min_distinct} distinct ${leg.distinct_field}`;
  }
  if (leg.novelty_field) {
    return `Novelty: first-seen ${leg.novelty_field}`;
  }
  return null;
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
  },
  description: {
    color: colors.muted,
    fontSize: fontSize.sm,
    marginHorizontal: spacing.lg,
    marginTop: spacing.xs,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
  },
  legTitle: {
    color: colors.foreground,
    fontSize: fontSize.sm,
    fontWeight: '600',
    marginBottom: spacing.xs,
  },
  condition: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontFamily: Platform.select({ ios: 'Menlo', default: 'monospace' }),
    marginBottom: 2,
  },
  constraint: {
    color: colors.purple,
    fontSize: fontSize.xs,
    marginTop: spacing.xs,
  },
  actions: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
  },
});
