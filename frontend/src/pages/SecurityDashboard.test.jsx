import { render, screen, waitFor } from '@testing-library/react';
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

    await waitFor(() => expect(screen.getByText('server-01')).toBeInTheDocument());
    expect(screen.getByText('server-02')).toBeInTheDocument();

    const activeBadge = screen.getByText('active');
    const disconnectedBadge = screen.getByText('disconnected');
    expect(activeBadge).toBeInTheDocument();
    expect(disconnectedBadge).toBeInTheDocument();
  });

  it('shows empty state when agent list is empty', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/dashboard/')) return Promise.resolve({ data: STATS });
      if (url.includes('/agents/')) return Promise.resolve({ data: [] });
      return Promise.reject(new Error(`unexpected url: ${url}`));
    });

    renderDashboard();

    await waitFor(() => expect(screen.getByText('No agents enrolled.')).toBeInTheDocument());
  });

  it('refresh button calls refresh endpoint and re-fetches data', async () => {
    const user = userEvent.setup();
    renderDashboard();

    await waitFor(() => expect(screen.getByText('server-01')).toBeInTheDocument());

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
});
