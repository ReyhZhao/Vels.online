import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), delete: vi.fn() },
}));

import api from '../lib/axios';
import { OrgContext } from '../context/OrgContext';
import RiskAcceptancePage from './RiskAcceptancePage';

const SELECTED_ORG = { id: 1, name: 'Acme Corp', slug: 'acme', wazuh_group: 'acme' };

const ACCEPTANCES = [
  {
    id: 1,
    cve_id: 'CVE-2024-0001',
    org_slug: 'acme',
    accepted_by: 'alice',
    accepted_at: '2024-01-15T10:00:00Z',
    note: 'Mitigated externally.',
    severity: 'critical',
    cvss_score: 9.8,
  },
  {
    id: 2,
    cve_id: 'CVE-2024-0002',
    org_slug: 'acme',
    accepted_by: 'bob',
    accepted_at: '2024-01-20T12:00:00Z',
    note: '',
    severity: 'high',
    cvss_score: 7.5,
  },
];

function renderPage(selectedOrg = SELECTED_ORG) {
  return render(
    <MemoryRouter>
      <OrgContext.Provider value={{ orgs: [SELECTED_ORG], selectedOrg, setSelectedOrg: vi.fn(), isLoading: false }}>
        <RiskAcceptancePage />
      </OrgContext.Provider>
    </MemoryRouter>
  );
}

describe('RiskAcceptancePage', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  // ── loading / empty states ──────────────────────────────────────────────────

  it('shows no org message when selectedOrg is null', () => {
    renderPage(null);
    expect(screen.getByText('No organisation assigned.')).toBeInTheDocument();
  });

  it('shows loading state while fetching', async () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows empty state when no acceptances', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText('No accepted vulnerabilities.')).toBeInTheDocument());
  });

  // ── rendering acceptances ───────────────────────────────────────────────────

  it('renders acceptance rows with correct data', async () => {
    api.get.mockResolvedValue({ data: ACCEPTANCES });
    renderPage();

    await waitFor(() => screen.getByText('CVE-2024-0001'));
    expect(screen.getByText('CVE-2024-0002')).toBeInTheDocument();
    expect(screen.getByText('alice')).toBeInTheDocument();
    expect(screen.getByText('bob')).toBeInTheDocument();
    expect(screen.getByText('Mitigated externally.')).toBeInTheDocument();
    // severity values also appear in the filter dropdown options
    expect(screen.getAllByText('critical').length).toBeGreaterThan(0);
    expect(screen.getAllByText('high').length).toBeGreaterThan(0);
    expect(screen.getByText('9.8')).toBeInTheDocument();
    expect(screen.getByText('7.5')).toBeInTheDocument();
  });

  it('shows — for empty note', async () => {
    api.get.mockResolvedValue({ data: ACCEPTANCES });
    renderPage();
    await waitFor(() => screen.getByText('CVE-2024-0002'));
    // CVE-2024-0002 has empty note — should show —
    const cells = screen.getAllByText('—');
    expect(cells.length).toBeGreaterThan(0);
  });

  it('shows page heading with org name', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText(/Accepted Vulnerabilities — Acme Corp/i)).toBeInTheDocument());
  });

  // ── remove button and confirmation dialog ──────────────────────────────────

  it('shows confirmation dialog when Remove is clicked', async () => {
    api.get.mockResolvedValue({ data: ACCEPTANCES });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => screen.getByText('CVE-2024-0001'));
    const removeButtons = screen.getAllByRole('button', { name: /^remove$/i });
    await user.click(removeButtons[0]);

    expect(screen.getByText('Remove risk acceptance?')).toBeInTheDocument();
    expect(screen.getAllByText(/CVE-2024-0001/).length).toBeGreaterThan(0);
  });

  it('closes dialog when Cancel is clicked', async () => {
    api.get.mockResolvedValue({ data: ACCEPTANCES });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => screen.getByText('CVE-2024-0001'));
    const removeButtons = screen.getAllByRole('button', { name: /^remove$/i });
    await user.click(removeButtons[0]);
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.queryByText('Remove risk acceptance?')).not.toBeInTheDocument();
  });

  it('calls DELETE and removes row on confirmation', async () => {
    api.get.mockResolvedValue({ data: ACCEPTANCES });
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => screen.getByText('CVE-2024-0001'));
    const removeButtons = screen.getAllByRole('button', { name: /^remove$/i });
    await user.click(removeButtons[0]);
    await user.click(screen.getByRole('button', { name: /confirm remove/i }));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/security/risk-acceptances/1/'));
    await waitFor(() => expect(screen.queryByText('CVE-2024-0001')).not.toBeInTheDocument());
    expect(screen.getByText('CVE-2024-0002')).toBeInTheDocument();
  });

  it('shows error message when DELETE fails', async () => {
    api.get.mockResolvedValue({ data: ACCEPTANCES });
    api.delete.mockRejectedValue({ response: { data: { detail: 'Permission denied.' } } });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => screen.getByText('CVE-2024-0001'));
    const removeButtons = screen.getAllByRole('button', { name: /^remove$/i });
    await user.click(removeButtons[0]);
    await user.click(screen.getByRole('button', { name: /confirm remove/i }));

    await waitFor(() => expect(screen.getByText('Permission denied.')).toBeInTheDocument());
  });

  it('fetches acceptances for the correct org', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/security/risk-acceptances/?org=acme'));
  });
});
