import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import { OrgContext } from '../context/OrgContext';
import AgentDetail from './AgentDetail';

const SELECTED_ORG = { id: 1, name: 'Acme Corp', slug: 'acme', wazuh_group: 'acme' };

const EVENTS_PAGE_1 = [
  { timestamp: '2024-01-15T10:00:00Z', rule_description: 'SSH brute force', rule_id: '5710', level: 10, severity: 'high',     agent_name: 'server-01' },
  { timestamp: '2024-01-15T09:00:00Z', rule_description: 'Sudo usage',       rule_id: '5402', level:  5, severity: 'medium',   agent_name: 'server-01' },
  { timestamp: '2024-01-15T08:00:00Z', rule_description: 'Failed login',     rule_id: '5501', level: 13, severity: 'critical', agent_name: 'server-01' },
];

const EVENTS_PAGE_2 = [
  { timestamp: '2024-01-15T07:00:00Z', rule_description: 'Package updated', rule_id: '2900', level: 2, severity: 'low', agent_name: 'server-01' },
];

const VULNS = [
  { cve: 'CVE-2024-0001', severity: 'critical', package: 'curl',    version: '7.68.0', fix_available: false },
  { cve: 'CVE-2024-0002', severity: 'high',     package: 'openssl', version: '1.1.1',  fix_available: true  },
  { cve: 'CVE-2024-0003', severity: 'medium',   package: 'libc6',   version: '2.31',   fix_available: true  },
];

function renderAgentDetail(agentId = '001', selectedOrg = SELECTED_ORG) {
  return render(
    <MemoryRouter initialEntries={[`/security/agents/${agentId}`]}>
      <OrgContext.Provider value={{ orgs: [SELECTED_ORG], selectedOrg, setSelectedOrg: vi.fn(), isLoading: false }}>
        <Routes>
          <Route path="/security/agents/:agentId" element={<AgentDetail />} />
        </Routes>
      </OrgContext.Provider>
    </MemoryRouter>
  );
}

// Default: events endpoint returns EVENTS_PAGE_1, vulns endpoint returns VULNS
function setupMocks({ events = EVENTS_PAGE_1, eventsTotal = 3, vulns = VULNS, vulnsTotal = 3 } = {}) {
  api.get.mockImplementation((url) => {
    if (url.includes('/events/'))          return Promise.resolve({ data: { events, total: eventsTotal } });
    if (url.includes('/vulnerabilities/')) return Promise.resolve({ data: { vulnerabilities: vulns, total: vulnsTotal } });
    return Promise.reject(new Error(`unexpected: ${url}`));
  });
  api.post.mockResolvedValue({ data: { detail: 'Cache cleared.' } });
}

describe('AgentDetail — events tab', () => {
  beforeEach(() => { vi.clearAllMocks(); setupMocks(); });

  it('renders event list with severity badges', async () => {
    renderAgentDetail();

    await waitFor(() => expect(screen.getByText('SSH brute force')).toBeInTheDocument());
    expect(screen.getByText('Sudo usage')).toBeInTheDocument();
    expect(screen.getByText('Failed login')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();
    expect(screen.getByText('critical')).toBeInTheDocument();
  });

  it('does not show Show more when total equals loaded count', async () => {
    renderAgentDetail();

    await waitFor(() => screen.getByText('SSH brute force'));
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
  });

  it('shows Show more button when total exceeds loaded count', async () => {
    setupMocks({ eventsTotal: 150 });
    renderAgentDetail();

    await waitFor(() => expect(screen.getByRole('button', { name: /show more/i })).toBeInTheDocument());
  });

  it('clicking Show more appends results without clearing existing ones', async () => {
    api.get
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_1, total: 4 } })
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_2, total: 4 } });
    api.post.mockResolvedValue({ data: { detail: 'Cache cleared.' } });

    const user = userEvent.setup();
    renderAgentDetail();

    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /show more/i }));

    await waitFor(() => expect(screen.getByText('Package updated')).toBeInTheDocument());
    expect(screen.getByText('SSH brute force')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
  });

  it('shows no org message when selectedOrg is null', () => {
    renderAgentDetail('001', null);
    expect(screen.getByText('No organisation assigned.')).toBeInTheDocument();
  });
});

describe('AgentDetail — vulnerabilities tab', () => {
  beforeEach(() => { vi.clearAllMocks(); setupMocks(); });

  async function openVulnsTab() {
    const user = userEvent.setup();
    renderAgentDetail();
    // Wait for events tab to finish loading, then switch
    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /vulnerabilities/i }));
    return user;
  }

  it('renders vulnerability list with severity badges and CVE IDs', async () => {
    await openVulnsTab();

    await waitFor(() => expect(screen.getByText('CVE-2024-0001')).toBeInTheDocument());
    expect(screen.getByText('CVE-2024-0002')).toBeInTheDocument();
    expect(screen.getByText('CVE-2024-0003')).toBeInTheDocument();
    // Severity badges in vuln list
    expect(screen.getAllByText('critical').length).toBeGreaterThan(0);
    expect(screen.getAllByText('high').length).toBeGreaterThan(0);
    expect(screen.getAllByText('medium').length).toBeGreaterThan(0);
  });

  it('shows Fix available correctly', async () => {
    await openVulnsTab();

    await waitFor(() => screen.getByText('CVE-2024-0001'));
    // CVE-2024-0001 fix_available=false → "None"; CVE-2024-0002 fix_available=true → "Available"
    expect(screen.getByText('None')).toBeInTheDocument();
    expect(screen.getAllByText('Available').length).toBeGreaterThan(0);
  });

  it('shows pagination controls when total > 50', async () => {
    setupMocks({ vulnsTotal: 120 });
    await openVulnsTab();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument()
    );
    expect(screen.getByRole('button', { name: /previous/i })).toBeInTheDocument();
  });

  it('Previous button disabled on first page', async () => {
    setupMocks({ vulnsTotal: 120 });
    await openVulnsTab();

    await waitFor(() => screen.getByRole('button', { name: /previous/i }));
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
  });

  it('clicking Next navigates to page 2', async () => {
    setupMocks({ vulnsTotal: 120 });
    const user = await openVulnsTab();

    await waitFor(() => screen.getByRole('button', { name: /next/i }));
    await user.click(screen.getByRole('button', { name: /next/i }));

    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('offset=50'))
    );
  });
});
