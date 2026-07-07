import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Bell } from 'lucide-react-native';
import { useRouter } from 'expo-router';
import api from '../lib/api';
import { colors, fontSize } from '../lib/theme';

/** Header notification bell with the authoritative unread count, polled like the web app. */
export function HeaderBell() {
  const router = useRouter();
  const [unreadCount, setUnreadCount] = useState(0);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const res = await api.get('/api/me/notifications/unread-count/');
      setUnreadCount(res.data.unread_count ?? 0);
    } catch {
      // silently ignore — badge just stays stale
    }
  }, []);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30_000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  return (
    <Pressable
      onPress={() => router.push('/notifications')}
      style={styles.button}
      accessibilityLabel="Notifications"
      testID="header-bell"
    >
      <Bell size={22} color={colors.foreground} />
      {unreadCount > 0 && (
        <View style={styles.badge}>
          <Text style={styles.badgeText}>{unreadCount > 99 ? '99+' : unreadCount}</Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    padding: 6,
    marginRight: 4,
  },
  badge: {
    position: 'absolute',
    top: 0,
    right: -2,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  badgeText: {
    color: '#fff',
    fontSize: fontSize.xs - 2,
    fontWeight: '700',
  },
});
