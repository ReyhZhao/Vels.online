import { useCallback, useEffect, useState } from 'react';
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { CheckCheck, Settings } from 'lucide-react-native';
import { Card } from '@/components/Card';
import { EmptyState, ErrorState, LoadingView } from '@/components/States';
import api from '@/lib/api';
import { humanize, timeAgo } from '@/lib/format';
import { colors, fontSize, spacing } from '@/lib/theme';
import type { AppNotification } from '@/lib/types';

export default function NotificationsScreen() {
  const router = useRouter();
  const [notifications, setNotifications] = useState<AppNotification[] | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const load = useCallback(async ({ refreshing = false } = {}) => {
    if (refreshing) setIsRefreshing(true);
    try {
      const res = await api.get('/api/me/notifications/');
      setNotifications(res.data.results);
      setUnreadCount(res.data.unread_count ?? 0);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not load notifications.');
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function markAllRead() {
    try {
      await api.post('/api/me/notifications/read-all/');
      await load();
    } catch {
      // reload next pull-to-refresh
    }
  }

  async function open(notification: AppNotification) {
    if (!notification.read_at) {
      api.post(`/api/me/notifications/${notification.id}/read/`).catch(() => {});
    }
    if (notification.incident_display_id) {
      router.push({
        pathname: '/incidents/[id]',
        params: { id: notification.incident_display_id },
      });
    } else {
      await load();
    }
  }

  if (error) return <ErrorState message={error} />;
  if (notifications === null) return <LoadingView />;

  return (
    <View style={styles.container}>
      <View style={styles.toolbar}>
        <Text style={styles.unread}>
          {unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}
        </Text>
        <View style={styles.toolbarActions}>
          {unreadCount > 0 && (
            <Pressable onPress={markAllRead} style={styles.toolbarButton} testID="read-all">
              <CheckCheck size={16} color={colors.primary} />
              <Text style={styles.toolbarButtonText}>Mark all read</Text>
            </Pressable>
          )}
          <Pressable
            onPress={() => router.push('/settings')}
            style={styles.toolbarButton}
            accessibilityLabel="Settings"
            testID="open-settings"
          >
            <Settings size={16} color={colors.muted} />
          </Pressable>
        </View>
      </View>
      <FlatList
        data={notifications}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => (
          <Card onPress={() => open(item)} testID={`notification-${item.id}`}>
            <View style={styles.row}>
              {!item.read_at && <View style={styles.dot} />}
              <View style={styles.body}>
                <View style={styles.header}>
                  <Text style={styles.kind}>{humanize(item.kind)}</Text>
                  <Text style={styles.time}>{timeAgo(item.created_at)}</Text>
                </View>
                <Text style={styles.title} numberOfLines={2}>
                  {item.payload?.title ?? humanize(item.kind)}
                </Text>
                {item.payload?.body ? (
                  <Text style={styles.text} numberOfLines={2}>
                    {item.payload.body}
                  </Text>
                ) : null}
                {item.incident_display_id ? (
                  <Text style={styles.incident}>{item.incident_display_id}</Text>
                ) : null}
              </View>
            </View>
          </Card>
        )}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => load({ refreshing: true })}
            tintColor={colors.muted}
          />
        }
        ListEmptyComponent={<EmptyState message="No notifications." />}
        contentContainerStyle={styles.listContent}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  toolbar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  unread: {
    color: colors.muted,
    fontSize: fontSize.sm,
  },
  toolbarActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
  },
  toolbarButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  toolbarButtonText: {
    color: colors.primary,
    fontSize: fontSize.sm,
    fontWeight: '600',
  },
  listContent: {
    paddingBottom: spacing.xl,
    flexGrow: 1,
  },
  row: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.primary,
    marginTop: 6,
  },
  body: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 2,
  },
  kind: {
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
  },
  text: {
    color: colors.muted,
    fontSize: fontSize.sm,
    marginTop: 2,
  },
  incident: {
    color: colors.primary,
    fontSize: fontSize.xs,
    fontWeight: '600',
    marginTop: spacing.xs,
  },
});
