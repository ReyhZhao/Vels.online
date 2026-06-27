import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({ default: { get: vi.fn() } }));

const mockUseAuth = vi.fn(() => ({ user: { id: 1, username: 'mo', is_staff: false } }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

import api from '../lib/axios';
import ReportsPage from './ReportsPage';

const REPORTS = [
  {
    id: 10, reference_id: 'REP-2026-0001', template_name: 'Customer Brief', audience: 'customer',
    organization_name: 'Acme', incident_display_id: 'INC-2026-0001',
    generated_at: new Date().toISOString(),
  },
  {
    id: 11, reference_id: 'REP-2026-0002', template_name: 'Internal Tech', audience: 'internal',
    organization_name: 'Acme', incident_display_id: 'INC-2026-0002',
    generated_at: new Date().toISOString(),
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <ReportsPage />
    </MemoryRouter>
  );
}

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'mo', is_staff: false } });
  });

  it('loads and lists reports from the cross-incident endpoint', async () => {
    api.get.mockResolvedValue({ data: REPORTS });
    renderPage();
    await waitFor(() => screen.getByText('REP-2026-0001'));
    expect(api.get).toHaveBeenCalledWith('/api/incidents/reports/');
    expect(screen.getByText('Customer Brief')).toBeInTheDocument();
  });

  it('shows the audience column for staff but not for org members', async () => {
    api.get.mockResolvedValue({ data: REPORTS });
    const { unmount } = renderPage();
    await waitFor(() => screen.getByText('REP-2026-0001'));
    expect(screen.queryByText('Audience')).not.toBeInTheDocument();
    unmount();

    mockUseAuth.mockReturnValue({ user: { id: 2, username: 'sam', is_staff: true } });
    renderPage();
    await waitFor(() => screen.getByText('Audience'));
  });

  it('downloads a report via its incident-scoped endpoint', async () => {
    api.get.mockImplementation((url) => {
      if (url.endsWith('/download/')) return Promise.resolve({ data: { url: 'https://dl/x.pdf' } });
      return Promise.resolve({ data: REPORTS });
    });
    window.open = vi.fn();
    renderPage();
    await waitFor(() => screen.getByText('REP-2026-0001'));
    await userEvent.click(screen.getAllByText('Download')[0]);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/incidents/INC-2026-0001/reports/10/download/'
    ));
  });

  it('shows an empty state when there are no reports', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => screen.getByText('No reports found.'));
  });
});
