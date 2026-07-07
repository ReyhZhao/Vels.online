import { useMemo, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { FlaskConical, Zap } from 'lucide-react-native';
import { Badge } from '@/components/Badge';
import { Card } from '@/components/Card';
import { SearchBar } from '@/components/SearchBar';
import { EmptyState, ErrorState, LoadingView } from '@/components/States';
import { usePagedList } from '@/hooks/usePagedList';
import { timeAgo } from '@/lib/format';
import { severityColor } from '@/lib/labels';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { SearchRule } from '@/lib/types';

export default function SearchRuleListScreen() {
  const router = useRouter();
  const [search, setSearch] = useState('');

  const { items, isLoading, isRefreshing, error, refresh } =
    usePagedList<SearchRule>('/api/correlations/search-rules/');

  const filtered = useMemo(() => {
    if (!search) return items;
    const term = search.toLowerCase();
    return items.filter(
      (rule) =>
        rule.name.toLowerCase().includes(term) ||
        rule.description.toLowerCase().includes(term),
    );
  }, [items, search]);

  return (
    <View style={styles.container}>
      <SearchBar placeholder="Search rules…" onSearch={setSearch} />
      {isLoading ? (
        <LoadingView />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => (
            <RuleRow
              rule={item}
              onPress={() => router.push({ pathname: '/rules/[id]', params: { id: String(item.id) } })}
            />
          )}
          refreshControl={
            <RefreshControl refreshing={isRefreshing} onRefresh={refresh} tintColor={colors.muted} />
          }
          ListEmptyComponent={<EmptyState message="No scheduled search rules." />}
          contentContainerStyle={styles.listContent}
        />
      )}
    </View>
  );
}

function RuleRow({ rule, onPress }: { rule: SearchRule; onPress: () => void }) {
  const testsFailing = rule.test_summary.failing + rule.test_summary.error > 0;
  return (
    <Card onPress={onPress} testID={`rule-${rule.id}`}>
      <View style={styles.rowTop}>
        <Text style={styles.name} numberOfLines={1}>
          {rule.name}
        </Text>
        <Badge
          label={rule.enabled ? 'enabled' : 'disabled'}
          color={rule.enabled ? colors.success : colors.muted}
        />
      </View>
      {rule.description ? (
        <Text style={styles.description} numberOfLines={2}>
          {rule.description}
        </Text>
      ) : null}
      <View style={styles.badges}>
        <Badge label={rule.severity} color={severityColor(rule.severity)} />
        <Badge label={rule.organization === null ? 'System' : 'Org'} color={colors.purple} />
      </View>
      <View style={styles.meta}>
        <View style={styles.metaItem}>
          <Zap size={12} color={colors.muted} />
          <Text style={styles.metaText}>
            {rule.firing_summary.count} firings
            {rule.firing_summary.last_fired_at
              ? ` · last ${timeAgo(rule.firing_summary.last_fired_at)}`
              : ''}
          </Text>
        </View>
        {rule.test_summary.total > 0 && (
          <View style={styles.metaItem}>
            <FlaskConical size={12} color={testsFailing ? colors.destructive : colors.success} />
            <Text
              style={[
                styles.metaText,
                { color: testsFailing ? colors.destructive : colors.success },
              ]}
            >
              {rule.test_summary.passing}/{rule.test_summary.total} passing
            </Text>
          </View>
        )}
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
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: 2,
  },
  name: {
    flex: 1,
    color: colors.foreground,
    fontSize: fontSize.md,
    fontWeight: '600',
  },
  description: {
    color: colors.muted,
    fontSize: fontSize.sm,
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
    gap: spacing.lg,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    color: colors.muted,
    fontSize: fontSize.xs,
  },
});
