import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import { OrgContext } from '../context/OrgContext';
import IncidentList from './IncidentList';

const SELECTED_ORG = { id: 1, name: 'Acme Corp', slug: 'acme', wazuh_group: 'acme' };

const INCIDENTS = [
  {
    id: 1,
    display_id: 'INC-2026-0001',
    title: 'Suspicious login',
    severity: 'high',
    tlp: 'amber',
    pap: 'amber',
    state: 'new',
    org_slug: 'acme',
    source_kind: 'manual',
    created_at: '2026-01-15T10:00:00Z',
    created_by_username: 'alice',
    assignee_username: null,
  },
  {
    id: 2,
    display_id: 'INC-2026-0002',
    title: 'Malware detected',
    severity: 'critical',
    tlp: 'green',
    pap: 'green',
    state: 'new',
    org_slug: 'acme',
    source_kind: 'wazuh_event',
    created_at: '2026-01-20T12:00:00Z',
    created_by_username: 'bob',
    assignee_username: 'charlie',
  },
];

function renderPage(selectedOrg = SELECTED_ORG) {
  return render(
    <MemoryRouter>
      <OrgContext.Provider value={{ orgs: [SELECTED_ORG], selectedOrg, setSelectedOrg: vi.fn(), isLoading: false }}>
        <IncidentList />
      </OrgContext.Provider>
    </MemoryRouter>
  );
}

describe('IncidentList', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows empty state when no incidents', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText('No incidents.')).toBeInTheDocument());
  });

  it('renders incident rows with correct data', async () => {
    api.get.mockResolvedValue({ data: INCIDENTS });
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    expect(screen.getByText('Suspicious login')).toBeInTheDocument();
    expect(screen.getByText('INC-2026-0002')).toBeInTheDocument();
    expect(screen.getByText('Malware detected')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByText('critical')).toBeInTheDocument();
  });

  it('shows page heading', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText('Incidents')).toBeInTheDocument());
  });

  it('fetches from the incidents endpoint', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/incidents/'));
  });

  it('shows error message on failure', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Permission denied.' } } });
    renderPage();
    await waitFor(() => expect(screen.getByText('Permission denied.')).toBeInTheDocument());
  });
});
