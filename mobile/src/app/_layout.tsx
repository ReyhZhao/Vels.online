import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { Stack, useRouter } from 'expo-router';
import * as Notifications from 'expo-notifications';
import { AuthProvider } from '@/context/AuthContext';
import { OrgProvider } from '@/context/OrgContext';
import { configureNotificationHandler } from '@/notifications/push';
import { colors } from '@/lib/theme';

configureNotificationHandler();

function useNotificationDeepLinks() {
  const router = useRouter();
  useEffect(() => {
    // Tapping a push carries the web link ("/incidents/INC-42"); map it to
    // the matching in-app screen, falling back to the notification center.
    const sub = Notifications.addNotificationResponseReceivedListener((response) => {
      const url = response.notification.request.content.data?.url;
      if (typeof url === 'string') {
        const incident = url.match(/\/incidents\/([\w-]+)/);
        if (incident) {
          router.push({ pathname: '/incidents/[id]', params: { id: incident[1] } });
          return;
        }
      }
      router.push('/notifications');
    });
    return () => sub.remove();
  }, [router]);
}

export default function RootLayout() {
  useNotificationDeepLinks();

  return (
    <AuthProvider>
      <OrgProvider>
        <StatusBar style="light" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.card },
            headerTintColor: colors.foreground,
            headerTitleStyle: { fontWeight: '600' },
            contentStyle: { backgroundColor: colors.background },
          }}
        >
          <Stack.Screen name="index" options={{ headerShown: false }} />
          <Stack.Screen name="login" options={{ headerShown: false }} />
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="notifications" options={{ title: 'Notifications' }} />
          <Stack.Screen name="settings" options={{ title: 'Settings' }} />
        </Stack>
      </OrgProvider>
    </AuthProvider>
  );
}
