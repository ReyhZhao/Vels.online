import { useMemo, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Globe, HardDrive, ShieldAlert } from 'lucide-react-native';
import { Badge } from '@/components/Badge';
import { Card } from '@/components/Card';
import { SearchBar } from '@/components/SearchBar';
import { Segmented } from '@/components/Segmented';
import { EmptyState, ErrorState, LoadingView } from '@/components/States';
import { usePagedList } from '@/hooks/usePagedList';
import { timeAgo } from '@/lib/format';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { Asset, Contact } from '@/lib/types';

const SECTIONS = ['contacts', 'assets'] as const;

export default function DirectoryScreen() {
  const [section, setSection] = useState<string>('contacts');
  const [search, setSearch] = useState('');

  return (
    <View style={styles.container}>
      <Segmented
        options={SECTIONS}
        labels={{ contacts: 'Contacts', assets: 'Assets' }}
        selected={section}
        onSelect={setSection}
      />
      <SearchBar
        placeholder={section === 'contacts' ? 'Search contacts…' : 'Search assets…'}
        onSearch={setSearch}
      />
      {section === 'contacts' ? <ContactList search={search} /> : <AssetList search={search} />}
    </View>
  );
}

function ContactList({ search }: { search: string }) {
  const router = useRouter();
  const { items, isLoading, isRefreshing, error, refresh } =
    usePagedList<Contact>('/api/contacts/');

  const filtered = useMemo(() => {
    if (!search) return items;
    const term = search.toLowerCase();
    return items.filter(
      (contact) =>
        contact.name.toLowerCase().includes(term) ||
        contact.email.toLowerCase().includes(term) ||
        (contact.org_name ?? '').toLowerCase().includes(term),
    );
  }, [items, search]);

  if (isLoading) return <LoadingView />;
  if (error) return <ErrorState message={error} />;

  return (
    <FlatList
      data={filtered}
      keyExtractor={(item) => String(item.id)}
      renderItem={({ item }) => (
        <Card
          onPress={() =>
            router.push({ pathname: '/directory/contact/[id]', params: { id: String(item.id) } })
          }
          testID={`contact-${item.id}`}
        >
          <Text style={styles.name}>{item.name}</Text>
          <Text style={styles.sub}>{item.email}</Text>
          <View style={styles.metaRow}>
            <Text style={styles.metaText}>
              {[item.job_title, item.department].filter(Boolean).join(' · ') || '—'}
            </Text>
            <Badge label={item.org_name} />
          </View>
        </Card>
      )}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={refresh} tintColor={colors.muted} />
      }
      ListEmptyComponent={<EmptyState message="No contacts found." />}
      contentContainerStyle={styles.listContent}
    />
  );
}

function AssetList({ search }: { search: string }) {
  const router = useRouter();
  const { items, isLoading, isRefreshing, error, refresh } = usePagedList<Asset>('/api/assets/');

  const filtered = useMemo(() => {
    if (!search) return items;
    const term = search.toLowerCase();
    return items.filter(
      (asset) =>
        asset.name.toLowerCase().includes(term) ||
        (asset.agent_name ?? '').toLowerCase().includes(term) ||
        (asset.ip_address ?? '').toLowerCase().includes(term) ||
        (asset.org_slug ?? '').toLowerCase().includes(term),
    );
  }, [items, search]);

  if (isLoading) return <LoadingView />;
  if (error) return <ErrorState message={error} />;

  return (
    <FlatList
      data={filtered}
      keyExtractor={(item) => String(item.id)}
      renderItem={({ item }) => (
        <Card
          onPress={() =>
            router.push({ pathname: '/directory/asset/[id]', params: { id: String(item.id) } })
          }
          testID={`asset-${item.id}`}
        >
          <View style={styles.assetRow}>
            {item.kind === 'route' ? (
              <Globe size={18} color={colors.muted} />
            ) : (
              <HardDrive size={18} color={colors.muted} />
            )}
            <View style={styles.assetBody}>
              <Text style={styles.name}>{item.name}</Text>
              <Text style={styles.metaText}>
                {item.kind === 'route'
                  ? item.route_fqdn ?? 'route'
                  : [item.role, item.ip_address].filter(Boolean).join(' · ') || 'host'}
              </Text>
            </View>
            <View style={styles.assetBadges}>
              {item.internet_facing && (
                <View style={styles.exposed}>
                  <ShieldAlert size={12} color={colors.orange} />
                  <Text style={styles.exposedText}>exposed</Text>
                </View>
              )}
              <Badge
                label={item.is_active ? 'active' : 'inactive'}
                color={item.is_active ? colors.success : colors.muted}
              />
            </View>
          </View>
        </Card>
      )}
      refreshControl={
        <RefreshControl refreshing={isRefreshing} onRefresh={refresh} tintColor={colors.muted} />
      }
      ListEmptyComponent={<EmptyState message="No assets found." />}
      contentContainerStyle={styles.listContent}
    />
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
  name: {
    color: colors.foreground,
    fontSize: fontSize.md,
    fontWeight: '600',
  },
  sub: {
    color: colors.primary,
    fontSize: fontSize.sm,
    marginTop: 2,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  metaText: {
    color: colors.muted,
    fontSize: fontSize.xs,
  },
  assetRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  assetBody: {
    flex: 1,
  },
  assetBadges: {
    alignItems: 'flex-end',
    gap: spacing.xs,
  },
  exposed: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  exposedText: {
    color: colors.orange,
    fontSize: fontSize.xs,
    fontWeight: '600',
  },
});
