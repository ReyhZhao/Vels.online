import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import { AuthContext } from '../context/AuthContext';
import { OrgContext } from '../context/OrgContext';
import SecurityDashboard from './SecurityDashboard';

const SELECTED_ORG = { id: 1, name: 'Acme Corp', slug: 'acme', wazuh_group: 'acme' };

const STATS = {
  agent_count: 5,
  active_count: 4,
  vulnerabilities: { critical: 2, high: 7, medium: 12, low: 3 },
  events_24h: 42,
};

const AGENTS = [
  {
    id: '001',
    name: 'server-01',
    ip: '10.0.0.1',
    status: 'active',
    os: 'Ubuntu 22.04',
    last_seen: '2024-01-01T12:00:00Z',
  },
  {
    id: '002',
    name: 'server-02',
    ip: '10.0.0.2',
    status: 'disconnected',
    os: 'Windows 11',
    last_seen: '2024-01-01T10:00:00Z',
  },
];

function renderDashboard(selectedOrg = SELECTED_ORG) {
  return render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{ user: { is_staff: false }, isAuthenticated: true, isLoading: false }}
      >
        <OrgContext.Provider
          value={{
            orgs: [SELECTED_ORG],
            selectedOrg,
            setSelectedOrg: vi.fn(),
            isLoading: false,
          }}
        >
          <SecurityDashboard />
        </OrgContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

// Both a mobile card list and a desktop table render in jsdom; the table is
// the deterministic surface for agent-row assertions.
const table = () => screen.getByRole('table');

describe('SecurityDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation((url) => {
      if (url.includes('/dashboard/')) return Promise.resolve({ data: STATS });
      if (url.includes('/agents/')) return Promise.resolve({ data: AGENTS });
      return Promise.reject(new Error(`unexpected url: ${url}`));
    });
    api.post.mockResolvedValue({ data: { detail: 'Cache cleared.' } });
  });

  it('renders fleet stats from API', async () => {
    renderDashboard();

    await waitFor(() => expect(screen.getByText('5')).toBeInTheDocument());
    expect(screen.getByText('4')).toBeInTheDocument();   // active_count
    expect(screen.getByText('2')).toBeInTheDocument();   // critical
    expect(screen.getByText('42')).toBeInTheDocument();  // events_24h
  });

  it('renders agent list with correct status indicators', async () => {
    renderDashboard();

    await waitFor(() => expect(within(table()).getByText('server-01')).toBeInTheDocument());
    expect(within(table()).getByText('server-02')).toBeInTheDocument();

    expect(within(table()).getByText('active')).toBeInTheDocument();
    expect(within(table()).getByText('disconnected')).toBeInTheDocument();
  });

  it('shows empty state when agent list is empty', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/dashboard/')) return Promise.resolve({ data: STATS });
      if (url.includes('/agents/')) return Promise.resolve({ data: [] });
      return Promise.reject(new Error(`unexpected url: ${url}`));
    });

    renderDashboard();

    await waitFor(() => expect(within(table()).getByText('No agents enrolled.')).toBeInTheDocument());
  });

  it('filters agents by search query (name / IP / OS)', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() => within(table()).getByText('server-01'));
    await user.type(screen.getByLabelText('Search agents'), 'Windows');
    await waitFor(() => expect(within(table()).queryByText('server-01')).not.toBeInTheDocument());
    expect(within(table()).getByText('server-02')).toBeInTheDocument();
  });

  it('filters agents by status', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() => within(table()).getByText('server-01'));
    await user.selectOptions(screen.getByLabelText('Status filter'), 'disconnected');
    await waitFor(() => expect(within(table()).queryByText('server-01')).not.toBeInTheDocument());
    expect(within(table()).getByText('server-02')).toBeInTheDocument();
  });

  it('sorts agents by name', async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() => within(table()).getByText('server-01'));
    // default name asc → server-01 first
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('server-01')).toBeInTheDocument();
    await user.click(within(table()).getByRole('button', { name: 'Sort by Agent' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('server-02')).toBeInTheDocument();
  });

  it('refresh button calls refresh endpoint and re-fetches data', async () => {
    const user = userEvent.setup();
    renderDashboard();

    await waitFor(() => expect(within(table()).getByText('server-01')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/security/dashboard/refresh/', { org: 'acme' })
    );
    expect(api.get).toHaveBeenCalledTimes(4); // 2 initial + 2 after refresh
  });

  it('shows no org message when selectedOrg is null', () => {
    renderDashboard(null);
    expect(screen.getByText('No organisation assigned.')).toBeInTheDocument();
  });

  it('shows backend detail in error message when API returns an error with detail', async () => {
    api.get.mockRejectedValue({
      response: { data: { detail: 'Wazuh authentication failed: 401 Unauthorized' } },
    });

    renderDashboard();

    await waitFor(() =>
      expect(
        screen.getByText('Failed to load dashboard data: Wazuh authentication failed: 401 Unauthorized')
      ).toBeInTheDocument()
    );
  });

  it('shows generic fallback when API error has no detail', async () => {
    api.get.mockRejectedValue(new Error('Network Error'));

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText('Failed to load dashboard data.')).toBeInTheDocument()
    );
  });
});
