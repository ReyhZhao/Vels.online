import { useMemo, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Link2 } from 'lucide-react-native';
import { Badge } from '@/components/Badge';
import { Card } from '@/components/Card';
import { FilterChips } from '@/components/FilterChips';
import { SearchBar } from '@/components/SearchBar';
import { EmptyState, ErrorState, LoadingView } from '@/components/States';
import { usePagedList } from '@/hooks/usePagedList';
import { humanize, timeAgo } from '@/lib/format';
import { ALERT_STATES, SEVERITIES, severityColor, stateColor } from '@/lib/labels';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { Alert } from '@/lib/types';

export default function AlertListScreen() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);

  const params = useMemo(
    () => ({
      per_page: 25,
      state: stateFilter ?? undefined,
      exclude_state: stateFilter ? undefined : 'ignored',
      severity: severityFilter ?? undefined,
      search: search || undefined,
    }),
    [stateFilter, severityFilter, search],
  );

  const { items, isLoading, isRefreshing, error, refresh, loadMore } =
    usePagedList<Alert>('/api/alerts/', params);

  return (
    <View style={styles.container}>
      <SearchBar placeholder="Search alerts…" onSearch={setSearch} />
      <FilterChips options={ALERT_STATES} selected={stateFilter} onSelect={setStateFilter} />
      <FilterChips options={SEVERITIES} selected={severityFilter} onSelect={setSeverityFilter} />
      {isLoading ? (
        <LoadingView />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => (
            <AlertRow
              alert={item}
              onPress={() =>
                router.push({ pathname: '/alerts/[id]', params: { id: item.display_id } })
              }
            />
          )}
          refreshControl={
            <RefreshControl refreshing={isRefreshing} onRefresh={refresh} tintColor={colors.muted} />
          }
          onEndReached={loadMore}
          onEndReachedThreshold={0.4}
          ListEmptyComponent={<EmptyState message="No alerts match the current filters." />}
          contentContainerStyle={styles.listContent}
        />
      )}
    </View>
  );
}

function AlertRow({ alert, onPress }: { alert: Alert; onPress: () => void }) {
  return (
    <Card onPress={onPress} testID={`alert-${alert.display_id}`}>
      <View style={styles.rowTop}>
        <Text style={styles.displayId}>{alert.display_id}</Text>
        <Text style={styles.time}>{timeAgo(alert.created_at)}</Text>
      </View>
      <Text style={styles.title} numberOfLines={2}>
        {alert.title}
      </Text>
      <View style={styles.badges}>
        <Badge label={alert.severity} color={severityColor(alert.severity)} />
        <Badge label={alert.state} color={stateColor(alert.state)} />
        <Badge label={humanize(alert.source_kind)} />
        {alert.incident_display_id ? (
          <View style={styles.linked}>
            <Link2 size={12} color={colors.primary} />
            <Text style={styles.linkedText}>{alert.incident_display_id}</Text>
          </View>
        ) : null}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  listContent: {
    paddingBottom: spacing.xl,
    flexGrow: 1,
  },
  rowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 2,
  },
  displayId: {
    color: colors.primary,
    fontSize: fontSize.xs,
    fontWeight: '700',
  },
  time: {
    color: colors.muted,
    fontSize: fontSize.xs,
  },
  title: {
    color: colors.foreground,
    fontSize: fontSize.md,
    fontWeight: '600',
    marginBottom: spacing.sm,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: spacing.xs,
  },
  linked: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  linkedText: {
    color: colors.primary,
    fontSize: fontSize.xs,
    fontWeight: '600',
  },
});
