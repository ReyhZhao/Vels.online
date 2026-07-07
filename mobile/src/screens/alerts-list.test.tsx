import { render, screen } from '@testing-library/react-native';
import AlertListScreen from '@/app/(tabs)/alerts/index';

const mockPush = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

import api from '@/lib/api';

const alertsPage = {
  count: 2,
  page: 1,
  per_page: 25,
  total_pages: 1,
  results: [
    {
      id: 1,
      display_id: 'AL-101',
      title: 'Port scan detected on acme-web-01',
      severity: 'high',
      state: 'new',
      source_kind: 'wazuh_event',
      incident_display_id: null,
      created_at: new Date().toISOString(),
    },
    {
      id: 2,
      display_id: 'AL-102',
      title: 'Suspicious login from new country',
      severity: 'critical',
      state: 'acknowledged',
      source_kind: 'api',
      incident_display_id: 'INC-7',
      created_at: new Date().toISOString(),
    },
  ],
};

describe('AlertListScreen', () => {
  beforeEach(() => {
    (api.get as jest.Mock).mockResolvedValue({ data: alertsPage });
  });

  it('renders the fetched alerts with severity and linkage', async () => {
    await render(<AlertListScreen />);
    expect(await screen.findByText('Port scan detected on acme-web-01')).toBeOnTheScreen();
    expect(screen.getByText('AL-101')).toBeOnTheScreen();
    // "Critical" exists as a filter chip too — the alert badge adds a second one.
    expect(screen.getAllByText('Critical').length).toBeGreaterThan(1);
    expect(screen.getByText('INC-7')).toBeOnTheScreen();
    expect(api.get).toHaveBeenCalledWith(
      '/api/alerts/',
      expect.objectContaining({
        params: expect.objectContaining({ per_page: 25, exclude_state: 'ignored', page: 1 }),
      }),
    );
  });
});
