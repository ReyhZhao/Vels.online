import { useCallback, useEffect, useState } from 'react';
import { Linking, ScrollView, StyleSheet, Text } from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Card } from '@/components/Card';
import { KeyValue, SectionHeader } from '@/components/KeyValue';
import { ErrorState, LoadingView } from '@/components/States';
import api from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { Asset, Contact } from '@/lib/types';

export default function ContactDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [contact, setContact] = useState<Contact | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [contactRes, assetsRes] = await Promise.all([
        api.get(`/api/contacts/${id}/`),
        api.get(`/api/contacts/${id}/assets/`).catch(() => ({ data: [] })),
      ]);
      setContact(contactRes.data);
      setAssets(assetsRes.data);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not load contact.');
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorState message={error} />;
  if (!contact) return <LoadingView />;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Stack.Screen options={{ title: contact.name }} />
      <Text style={styles.name}>{contact.name}</Text>
      <Text style={styles.email} onPress={() => Linking.openURL(`mailto:${contact.email}`)}>
        {contact.email}
      </Text>

      <SectionHeader title="Details" />
      <Card>
        <KeyValue label="Job title" value={contact.job_title || '—'} />
        <KeyValue label="Department" value={contact.department || '—'} />
        <KeyValue label="Organisation" value={contact.org_name} />
        <KeyValue label="Added" value={formatDateTime(contact.created_at)} />
      </Card>

      {assets.length > 0 && (
        <>
          <SectionHeader title={`Owned assets (${assets.length})`} />
          {assets.map((asset) => (
            <Card
              key={asset.id}
              onPress={() =>
                router.push({
                  pathname: '/directory/asset/[id]',
                  params: { id: String(asset.id) },
                })
              }
            >
              <Text style={styles.assetName}>{asset.name}</Text>
              <Text style={styles.metaText}>
                {asset.kind === 'route'
                  ? asset.route_fqdn ?? 'route'
                  : [asset.role, asset.ip_address].filter(Boolean).join(' · ') || 'host'}
              </Text>
            </Card>
          ))}
        </>
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
  name: {
    color: colors.foreground,
    fontSize: fontSize.xl,
    fontWeight: '700',
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
  },
  email: {
    color: colors.primary,
    fontSize: fontSize.md,
    marginHorizontal: spacing.lg,
    marginTop: spacing.xs,
  },
  assetName: {
    color: colors.foreground,
    fontSize: fontSize.md,
    fontWeight: '600',
  },
  metaText: {
    color: colors.muted,
    fontSize: fontSize.xs,
    marginTop: 2,
  },
});
