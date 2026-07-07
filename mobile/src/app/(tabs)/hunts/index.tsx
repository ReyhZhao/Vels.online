import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback } from 'react';
import { Plus } from 'lucide-react-native';
import { Badge } from '@/components/Badge';
import { Card } from '@/components/Card';
import { EmptyState, ErrorState, LoadingView } from '@/components/States';
import { usePagedList } from '@/hooks/usePagedList';
import { timeAgo } from '@/lib/format';
import { stateColor } from '@/lib/labels';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { Hunt } from '@/lib/types';

export default function HuntListScreen() {
  const router = useRouter();
  const { items, isLoading, isRefreshing, error, refresh } = usePagedList<Hunt>('/api/hunts/');

  // Refresh when returning from the create modal or a detail screen.
  useFocusEffect(
    useCallback(() => {
      if (!isLoading) refresh();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []),
  );

  return (
    <View style={styles.container}>
      {isLoading ? (
        <LoadingView />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <HuntRow
              hunt={item}
              onPress={() => router.push({ pathname: '/hunts/[id]', params: { id: item.id } })}
            />
          )}
          refreshControl={
            <RefreshControl refreshing={isRefreshing} onRefresh={refresh} tintColor={colors.muted} />
          }
          ListEmptyComponent={
            <EmptyState message="No hunts yet. Start one to sweep the fleet for a threat." />
          }
          contentContainerStyle={styles.listContent}
        />
      )}
      <Pressable
        style={styles.fab}
        onPress={() => router.push('/hunts/new')}
        accessibilityLabel="New hunt"
        testID="new-hunt-fab"
      >
        <Plus size={26} color="#fff" />
      </Pressable>
    </View>
  );
}

function HuntRow({ hunt, onPress }: { hunt: Hunt; onPress: () => void }) {
  return (
    <Card onPress={onPress} testID={`hunt-${hunt.id}`}>
      <View style={styles.rowTop}>
        <Text style={styles.title} numberOfLines={2}>
          {hunt.title || 'Untitled hunt'}
        </Text>
        <Badge label={hunt.status} color={stateColor(hunt.status)} />
      </View>
      <View style={styles.meta}>
        <Text style={styles.metaText}>
          {hunt.scope_all_orgs ? 'All orgs' : 'Scoped'} · {hunt.lookback_days}d lookback
        </Text>
        <Text style={styles.metaText}>{timeAgo(hunt.created_at)}</Text>
      </View>
      <View style={styles.meta}>
        <Text style={styles.metaText}>
          {hunt.finding_count} finding{hunt.finding_count === 1 ? '' : 's'}
          {hunt.spawned_incident_count > 0
            ? ` · ${hunt.spawned_incident_count} incident${hunt.spawned_incident_count === 1 ? '' : 's'}`
            : ''}
        </Text>
        {hunt.owner_username ? <Text style={styles.metaText}>@{hunt.owner_username}</Text> : null}
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
    paddingTop: spacing.sm,
    paddingBottom: 96,
    flexGrow: 1,
  },
  rowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  title: {
    flex: 1,
    color: colors.foreground,
    fontSize: fontSize.md,
    fontWeight: '600',
  },
  meta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 2,
  },
  metaText: {
    color: colors.muted,
    fontSize: fontSize.xs,
  },
  fab: {
    position: 'absolute',
    right: spacing.lg,
    bottom: spacing.xl,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 3 },
  },
});
