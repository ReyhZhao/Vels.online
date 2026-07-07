import { useCallback, useEffect, useState } from 'react';
import { Alert as RNAlert, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { ShieldAlert, ShieldCheck } from 'lucide-react-native';
import { Badge } from '@/components/Badge';
import { Card } from '@/components/Card';
import { KeyValue, SectionHeader } from '@/components/KeyValue';
import { ErrorState, LoadingView } from '@/components/States';
import api from '@/lib/api';
import { formatDateTime, humanize, timeAgo } from '@/lib/format';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { Asset } from '@/lib/types';

export default function AssetDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [asset, setAsset] = useState<Asset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.get(`/api/assets/${id}/`);
      setAsset(res.data);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not load asset.');
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleActive(value: boolean) {
    setToggling(true);
    try {
      await api.patch(`/api/assets/${id}/`, { is_active: value });
      await load();
    } catch (err: any) {
      RNAlert.alert('Update failed', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setToggling(false);
    }
  }

  if (error) return <ErrorState message={error} />;
  if (!asset) return <LoadingView />;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Stack.Screen options={{ title: asset.name }} />
      <Text style={styles.name}>{asset.name}</Text>
      <View style={styles.badges}>
        <Badge label={asset.kind === 'route' ? 'Route asset' : 'Host asset'} color={colors.purple} />
        <Badge label={asset.org_slug} />
        {asset.internet_facing && <Badge label="internet-facing" color={colors.orange} />}
      </View>

      <SectionHeader title="Details" />
      <Card>
        <KeyValue label="Active">
          <Switch
            value={asset.is_active}
            onValueChange={toggleActive}
            disabled={toggling}
            trackColor={{ true: colors.primary, false: colors.secondary }}
            testID="asset-active-switch"
          />
        </KeyValue>
        {asset.kind === 'host' ? (
          <>
            <KeyValue label="Agent" value={asset.agent_name} />
            <KeyValue label="IP address" value={asset.ip_address} />
            <KeyValue label="Role" value={humanize(asset.role)} />
          </>
        ) : (
          <KeyValue label="FQDN" value={asset.route_fqdn} />
        )}
        <KeyValue label="Permanent" value={asset.is_permanent ? 'yes' : 'no'} />
        <KeyValue
          label="Last seen"
          value={asset.last_seen_at ? timeAgo(asset.last_seen_at) : 'never'}
        />
        <KeyValue label="Created" value={formatDateTime(asset.created_at)} />
      </Card>

      {asset.kind === 'host' && (
        <>
          <SectionHeader title={`Exposures (${asset.exposures.length})`} />
          {asset.exposures.length === 0 ? (
            <Card>
              <Text style={styles.metaText}>
                No exposures — this host is not internet-facing.
              </Text>
            </Card>
          ) : (
            asset.exposures.map((exposure, index) => (
              <Card key={index}>
                <View style={styles.exposureHeader}>
                  {exposure.protection === 'protected' ? (
                    <ShieldCheck size={16} color={colors.success} />
                  ) : (
                    <ShieldAlert size={16} color={colors.destructive} />
                  )}
                  <Text style={styles.exposureTitle}>
                    {exposure.kind === 'ingress_route' ? 'Ingress route' : 'Direct NAT'}
                  </Text>
                  <Badge
                    label={exposure.protection}
                    color={exposure.protection === 'protected' ? colors.success : colors.destructive}
                  />
                </View>
                {Object.entries(exposure.specifics)
                  .filter(([, value]) => value !== null && value !== undefined && value !== '')
                  .map(([key, value]) => (
                    <KeyValue key={key} label={humanize(key)} value={String(value)} />
                  ))}
              </Card>
            ))
          )}
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
    marginBottom: spacing.sm,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
  },
  metaText: {
    color: colors.muted,
    fontSize: fontSize.sm,
  },
  exposureHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.xs,
  },
  exposureTitle: {
    flex: 1,
    color: colors.foreground,
    fontSize: fontSize.md,
    fontWeight: '600',
  },
});
