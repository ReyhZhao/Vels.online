import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { post: jest.fn(), delete: jest.fn() },
}));

import api from '@/lib/api';
import { registerForPushNotifications } from './push';

describe('registerForPushNotifications', () => {
  beforeEach(() => jest.clearAllMocks());

  it('registers the Expo token with the backend', async () => {
    (api.post as jest.Mock).mockResolvedValue({ status: 201 });
    const token = await registerForPushNotifications();
    expect(token).toBe('ExponentPushToken[test]');
    expect(api.post).toHaveBeenCalledWith('/api/me/push/expo-token/', {
      token: 'ExponentPushToken[test]',
      platform: Platform.OS,
    });
  });

  it('returns null when permission is denied', async () => {
    (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValueOnce({ status: 'denied' });
    (Notifications.requestPermissionsAsync as jest.Mock).mockResolvedValueOnce({
      status: 'denied',
    });
    const token = await registerForPushNotifications();
    expect(token).toBeNull();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('returns null when the backend rejects the registration', async () => {
    (api.post as jest.Mock).mockRejectedValue(new Error('401'));
    const token = await registerForPushNotifications();
    expect(token).toBeNull();
  });
});
