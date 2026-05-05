import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import { OrgContext } from '../context/OrgContext';
import DashboardPage from './DashboardPage';

const SELECTED_ORG = { id: 1, name: 'Acme', slug: 'acme', wazuh_group: 'acme' };

const STATS = {
  agent_count: 5,
  active_count: 4,
  vulnerabilities: { critical: 2, high: 7, medium: 12, low: 3 },
  events_24h: 42,
};

function renderPage(selectedOrg = SELECTED_ORG) {
  return render(
    <MemoryRouter>
      <OrgContext.Provider
        value={{ orgs: [SELECTED_ORG], selectedOrg, setSelectedOrg: vi.fn(), isLoading: false }}
      >
        <DashboardPage />
      </OrgContext.Provider>
    </MemoryRouter>
  );
}

describe('DashboardPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the Security service card linking to /security', async () => {
    api.get.mockResolvedValue({ data: STATS });
    renderPage();

    const securityCard = screen.getByRole('link', { name: /security/i });
    expect(securityCard).toBeInTheDocument();
    expect(securityCard).toHaveAttribute('href', '/security');
    await waitFor(() => expect(screen.getByText('24')).toBeInTheDocument());
  });

  it('displays fetched vulnerability count', async () => {
    api.get.mockResolvedValue({ data: STATS });
    renderPage();

    // 2 + 7 + 12 + 3 = 24
    await waitFor(() => expect(screen.getByText('24')).toBeInTheDocument());
  });

  it('displays fetched agent count', async () => {
    api.get.mockResolvedValue({ data: STATS });
    renderPage();

    await waitFor(() => expect(screen.getByText('5')).toBeInTheDocument());
  });

  it('shows loading indicator while data is being fetched', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();

    expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0);
  });

  it('shows fallback "—" when API call fails', async () => {
    api.get.mockRejectedValue(new Error('Network Error'));
    renderPage();

    await waitFor(() => {
      const dashes = screen.getAllByText('—');
      expect(dashes.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('does not fetch when no org is selected', () => {
    renderPage(null);
    expect(api.get).not.toHaveBeenCalled();
  });
});
