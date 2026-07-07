import { useMemo, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Paperclip, ListChecks, Link2 } from 'lucide-react-native';
import { Badge } from '@/components/Badge';
import { Card } from '@/components/Card';
import { FilterChips } from '@/components/FilterChips';
import { SearchBar } from '@/components/SearchBar';
import { EmptyState, ErrorState, LoadingView } from '@/components/States';
import { usePagedList } from '@/hooks/usePagedList';
import { timeAgo } from '@/lib/format';
import { INCIDENT_STATES, SEVERITIES, severityColor, stateColor } from '@/lib/labels';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { Incident } from '@/lib/types';

const OPEN_STATES = 'new,triaged,in_progress,on_hold,pending_closure';

export default function IncidentListScreen() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);

  const params = useMemo(
    () => ({
      per_page: 25,
      state: stateFilter ?? OPEN_STATES,
      severity: severityFilter ?? undefined,
      q: search || undefined,
    }),
    [stateFilter, severityFilter, search],
  );

  const { items, isLoading, isRefreshing, error, refresh, loadMore } =
    usePagedList<Incident>('/api/incidents/', params);

  return (
    <View style={styles.container}>
      <SearchBar placeholder="Search incidents…" onSearch={setSearch} />
      <FilterChips options={INCIDENT_STATES} selected={stateFilter} onSelect={setStateFilter} allLabel="Open" />
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
            <IncidentRow
              incident={item}
              onPress={() =>
                router.push({ pathname: '/incidents/[id]', params: { id: item.display_id } })
              }
            />
          )}
          refreshControl={
            <RefreshControl refreshing={isRefreshing} onRefresh={refresh} tintColor={colors.muted} />
          }
          onEndReached={loadMore}
          onEndReachedThreshold={0.4}
          ListEmptyComponent={<EmptyState message="No incidents match the current filters." />}
          contentContainerStyle={styles.listContent}
        />
      )}
    </View>
  );
}

function IncidentRow({ incident, onPress }: { incident: Incident; onPress: () => void }) {
  return (
    <Card onPress={onPress} testID={`incident-${incident.display_id}`}>
      <View style={styles.rowTop}>
        <Text style={styles.displayId}>{incident.display_id}</Text>
        <Text style={styles.time}>{timeAgo(incident.created_at)}</Text>
      </View>
      <Text style={styles.title} numberOfLines={2}>
        {incident.title}
      </Text>
      <View style={styles.badges}>
        <Badge label={incident.severity} color={severityColor(incident.severity)} />
        <Badge label={incident.state} color={stateColor(incident.state)} />
        {incident.org_name ? <Badge label={incident.org_name} /> : null}
      </View>
      <View style={styles.meta}>
        {incident.assignee_username ? (
          <Text style={styles.metaText}>@{incident.assignee_username}</Text>
        ) : (
          <Text style={styles.metaText}>Unassigned</Text>
        )}
        <View style={styles.counts}>
          {incident.linked_alert_count > 0 && (
            <View style={styles.count}>
              <Link2 size={12} color={colors.muted} />
              <Text style={styles.metaText}>{incident.linked_alert_count}</Text>
            </View>
          )}
          {incident.task_count > 0 && (
            <View style={styles.count}>
              <ListChecks size={12} color={colors.muted} />
              <Text style={styles.metaText}>{incident.task_count}</Text>
            </View>
          )}
          {incident.attachment_count > 0 && (
            <View style={styles.count}>
              <Paperclip size={12} color={colors.muted} />
              <Text style={styles.metaText}>{incident.attachment_count}</Text>
            </View>
          )}
        </View>
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
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  meta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  metaText: {
    color: colors.muted,
    fontSize: fontSize.xs,
  },
  counts: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  count: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
});
