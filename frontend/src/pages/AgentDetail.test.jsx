import { render, screen, waitFor, within } from '@testing-library/react';
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
  {
    timestamp: '2024-01-15T10:00:00Z',
    rule_description: 'SSH brute force',
    rule_id: '5710',
    level: 10,
    severity: 'high',
    agent_name: 'server-01',
  },
  {
    timestamp: '2024-01-15T09:00:00Z',
    rule_description: 'Sudo usage',
    rule_id: '5402',
    level: 5,
    severity: 'medium',
    agent_name: 'server-01',
  },
  {
    timestamp: '2024-01-15T08:00:00Z',
    rule_description: 'Failed login',
    rule_id: '5501',
    level: 13,
    severity: 'critical',
    agent_name: 'server-01',
  },
];

const EVENTS_PAGE_2 = [
  {
    timestamp: '2024-01-15T07:00:00Z',
    rule_description: 'Package updated',
    rule_id: '2900',
    level: 2,
    severity: 'low',
    agent_name: 'server-01',
  },
];

function renderAgentDetail(agentId = '001', selectedOrg = SELECTED_ORG) {
  return render(
    <MemoryRouter initialEntries={[`/security/agents/${agentId}`]}>
      <OrgContext.Provider
        value={{
          orgs: [SELECTED_ORG],
          selectedOrg,
          setSelectedOrg: vi.fn(),
          isLoading: false,
        }}
      >
        <Routes>
          <Route path="/security/agents/:agentId" element={<AgentDetail />} />
        </Routes>
      </OrgContext.Provider>
    </MemoryRouter>
  );
}

describe('AgentDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { events: EVENTS_PAGE_1, total: 3 } });
    api.post.mockResolvedValue({ data: { detail: 'Cache cleared.' } });
  });

  it('renders event list with severity badges', async () => {
    renderAgentDetail();

    await waitFor(() => expect(screen.getByText('SSH brute force')).toBeInTheDocument());

    expect(screen.getByText('Sudo usage')).toBeInTheDocument();
    expect(screen.getByText('Failed login')).toBeInTheDocument();

    // Severity badges
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();
    expect(screen.getByText('critical')).toBeInTheDocument();
  });

  it('does not show Show more when total equals events count', async () => {
    renderAgentDetail();

    await waitFor(() => expect(screen.getByText('SSH brute force')).toBeInTheDocument());

    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
  });

  it('shows Show more button when total exceeds loaded count', async () => {
    api.get.mockResolvedValue({ data: { events: EVENTS_PAGE_1, total: 150 } });

    renderAgentDetail();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /show more/i })).toBeInTheDocument()
    );
  });

  it('clicking Show more appends results without clearing existing ones', async () => {
    api.get
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_1, total: 4 } })
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_2, total: 4 } });

    const user = userEvent.setup();
    renderAgentDetail();

    await waitFor(() => expect(screen.getByText('SSH brute force')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /show more/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /show more/i }));

    await waitFor(() => expect(screen.getByText('Package updated')).toBeInTheDocument());

    // Original events still present
    expect(screen.getByText('SSH brute force')).toBeInTheDocument();
    expect(screen.getByText('Sudo usage')).toBeInTheDocument();

    // Show more gone when all loaded
    expect(screen.queryByRole('button', { name: /show more/i })).not.toBeInTheDocument();
  });

  it('second Show more call uses correct offset', async () => {
    api.get
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_1, total: 4 } })
      .mockResolvedValueOnce({ data: { events: EVENTS_PAGE_2, total: 4 } });

    const user = userEvent.setup();
    renderAgentDetail();

    await waitFor(() => screen.getByText('SSH brute force'));
    await user.click(screen.getByRole('button', { name: /show more/i }));
    await waitFor(() => screen.getByText('Package updated'));

    // Second call should have offset=3 (after 3 loaded)
    expect(api.get).toHaveBeenLastCalledWith(
      expect.stringContaining('offset=3')
    );
  });

  it('shows no org message when selectedOrg is null', () => {
    renderAgentDetail('001', null);
    expect(screen.getByText('No organisation assigned.')).toBeInTheDocument();
  });
});
