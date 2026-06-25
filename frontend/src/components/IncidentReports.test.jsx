import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const mockUseAuth = vi.fn(() => ({ user: { id: 1, username: 'mo', is_staff: false } }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

import api from '../lib/axios';
import IncidentReports from './IncidentReports';

const REPORT = {
  id: 10, reference_id: 'REP-2026-0001', template: 1, template_name: 'Customer Brief',
  audience: 'customer', tlp: 'green', incident_state: 'resolved',
  incident_display_id: 'INC-2026-0001', generated_by: 2, generated_by_username: 'sam',
  generated_at: new Date().toISOString(), size_bytes: 1234,
};

describe('IncidentReports', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'mo', is_staff: false } });
  });

  it('shows empty state when no reports', async () => {
    api.get.mockResolvedValue({ data: [] });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('No reports generated yet.'));
  });

  it('lists reports with reference id and audience', async () => {
    api.get.mockResolvedValue({ data: [REPORT] });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('REP-2026-0001'));
    expect(screen.getByText('Customer Brief')).toBeInTheDocument();
    expect(screen.getByText('customer')).toBeInTheDocument();
  });

  it('hides the generate control for non-staff org members', async () => {
    api.get.mockResolvedValue({ data: [REPORT] });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('REP-2026-0001'));
    expect(screen.queryByText('Generate report')).not.toBeInTheDocument();
  });

  it('staff can generate a report from a template', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 2, username: 'sam', is_staff: true } });
    api.get.mockImplementation((url) => {
      if (url.includes('report-templates')) {
        return Promise.resolve({ data: [{ id: 1, name: 'Customer Brief', audience: 'customer' }] });
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValue({ data: REPORT });

    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('Generate report'));
    await userEvent.click(screen.getByText('Generate report'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/api/incidents/INC-2026-0001/reports/',
        { template_id: 1 },
      )
    );
  });

  it('surfaces a generation error (e.g. customer report on TLP:RED)', async () => {
    mockUseAuth.mockReturnValue({ user: { id: 2, username: 'sam', is_staff: true } });
    api.get.mockImplementation((url) => {
      if (url.includes('report-templates')) {
        return Promise.resolve({ data: [{ id: 1, name: 'Brief', audience: 'customer' }] });
      }
      return Promise.resolve({ data: [] });
    });
    api.post.mockRejectedValue({
      response: { data: { detail: 'A customer report cannot be generated for a TLP:RED incident.' } },
    });

    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('Generate report'));
    await userEvent.click(screen.getByText('Generate report'));
    await waitFor(() => screen.getByText(/TLP:RED/));
  });
});
