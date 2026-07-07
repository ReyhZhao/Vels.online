import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import NotificationsScreen from '@/app/notifications';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

import api from '@/lib/api';

const page = {
  count: 2,
  unread_count: 1,
  results: [
    {
      id: 11,
      kind: 'assignment',
      incident_display_id: 'INC-42',
      payload: { title: 'You were assigned INC-42', body: 'Ransomware on acme-dc-01' },
      created_at: new Date().toISOString(),
      read_at: null,
    },
    {
      id: 12,
      kind: 'comment',
      incident_display_id: 'INC-40',
      payload: { title: 'New comment on INC-40' },
      created_at: new Date().toISOString(),
      read_at: new Date().toISOString(),
    },
  ],
};

describe('NotificationsScreen', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.get as jest.Mock).mockResolvedValue({ data: page });
    (api.post as jest.Mock).mockResolvedValue({ data: {} });
  });

  it('lists notifications with the unread count', async () => {
    await render(<NotificationsScreen />);
    expect(await screen.findByText('You were assigned INC-42')).toBeOnTheScreen();
    expect(screen.getByText('1 unread')).toBeOnTheScreen();
  });

  it('marks all read', async () => {
    await render(<NotificationsScreen />);
    await screen.findByText('You were assigned INC-42');
    await fireEvent.press(screen.getByTestId('read-all'));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/me/notifications/read-all/'),
    );
  });

  it('opens the linked incident and marks the notification read', async () => {
    await render(<NotificationsScreen />);
    await fireEvent.press(await screen.findByTestId('notification-11'));
    expect(api.post).toHaveBeenCalledWith('/api/me/notifications/11/read/');
    expect(mockPush).toHaveBeenCalledWith({
      pathname: '/incidents/[id]',
      params: { id: 'INC-42' },
    });
  });
});
