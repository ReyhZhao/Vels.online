import { Platform } from 'react-native';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import api from '../lib/api';

/**
 * Foreground presentation: show banners for pushes arriving while the app is
 * open, mirroring the web app's in-page toast behaviour.
 */
export function configureNotificationHandler(): void {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldPlaySound: false,
      shouldSetBadge: true,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
}

/**
 * Ask for permission, obtain the Expo push token and register it with the
 * backend (notifications.ExpoPushToken). Safe to call on every sign-in —
 * registration is idempotent server-side.
 *
 * Returns the token when registered, null when unavailable (simulator,
 * permission denied, …).
 */
export async function registerForPushNotifications(): Promise<string | null> {
  if (!Device.isDevice) return null;

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'Polaris Security',
      importance: Notifications.AndroidImportance.HIGH,
      lightColor: '#3B82F6',
    });
  }

  const { status: existing } = await Notifications.getPermissionsAsync();
  let status = existing;
  if (existing !== 'granted') {
    const request = await Notifications.requestPermissionsAsync();
    status = request.status;
  }
  if (status !== 'granted') return null;

  let token: string;
  try {
    const result = await Notifications.getExpoPushTokenAsync();
    token = result.data;
  } catch {
    return null;
  }

  try {
    await api.post('/api/me/push/expo-token/', { token, platform: Platform.OS });
  } catch {
    return null;
  }
  return token;
}

/** Best-effort deregistration on sign-out so a shared device stops receiving pushes. */
export async function unregisterPushToken(): Promise<void> {
  if (!Device.isDevice) return;
  try {
    const result = await Notifications.getExpoPushTokenAsync();
    await api.delete('/api/me/push/expo-token/', { data: { token: result.data } });
  } catch {
    // token may never have been registered
  }
}
