import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import { LinkedAlertsPanel } from './IncidentDetail';

const ALERTS = [
  {
    display_id: 'AL-2026-0001', title: 'Brute force on web-01', severity: 'high',
    state: 'imported', source_kind: 'wazuh_event', agent_name: 'web-01',
    created_at: '2026-06-12T10:00:00Z', updated_at: '2026-06-12T10:05:00Z',
    description: 'many failed logins from 1.2.3.4', source_ref: { srcip: '1.2.3.4', level: 10 },
    pap: 'amber', tlp: 'green', acknowledged_by: null, acknowledged_at: null,
  },
  {
    display_id: 'AL-2026-0002', title: 'CVE-2026-1234 on db-01', severity: 'medium',
    state: 'new', source_kind: 'vulnerability', agent_name: 'db-01',
    created_at: '2026-06-12T11:00:00Z', updated_at: '2026-06-12T11:00:00Z',
    description: 'vulnerable package', source_ref: { cve: 'CVE-2026-1234' },
    pap: null, tlp: null, acknowledged_by: 'bob', acknowledged_at: '2026-06-12T12:00:00Z',
  },
];

describe('LinkedAlertsPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders linked alert rows', async () => {
    api.get.mockResolvedValue({ data: ALERTS });
    render(<LinkedAlertsPanel displayId="INC-2026-0001" linkedAlertCount={2} />);
    await waitFor(() => screen.getByText('Brute force on web-01'));
    expect(screen.getByText('CVE-2026-1234 on db-01')).toBeInTheDocument();
  });

  it('opens a detail modal with full info when a row is clicked', async () => {
    api.get.mockResolvedValue({ data: ALERTS });
    const user = userEvent.setup();
    render(<LinkedAlertsPanel displayId="INC-2026-0001" linkedAlertCount={2} />);
    await waitFor(() => screen.getByText('Brute force on web-01'));

    await user.click(screen.getByText('Brute force on web-01'));

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('many failed logins from 1.2.3.4');
    expect(dialog).toHaveTextContent('1.2.3.4'); // source_ref rendered
    expect(dialog).toHaveTextContent('source_ref');
  });

  it('filters rows by search text', async () => {
    api.get.mockResolvedValue({ data: ALERTS });
    const user = userEvent.setup();
    render(<LinkedAlertsPanel displayId="INC-2026-0001" linkedAlertCount={2} />);
    await waitFor(() => screen.getByText('Brute force on web-01'));

    await user.type(screen.getByPlaceholderText('Search alerts…'), 'brute');

    expect(screen.getByText('Brute force on web-01')).toBeInTheDocument();
    expect(screen.queryByText('CVE-2026-1234 on db-01')).not.toBeInTheDocument();
    expect(screen.getByText(/Showing 1 of 2/)).toBeInTheDocument();
  });

  it('filters rows by severity select', async () => {
    api.get.mockResolvedValue({ data: ALERTS });
    const user = userEvent.setup();
    render(<LinkedAlertsPanel displayId="INC-2026-0001" linkedAlertCount={2} />);
    await waitFor(() => screen.getByText('Brute force on web-01'));

    await user.selectOptions(screen.getByLabelText('Filter by severity'), 'medium');

    expect(screen.queryByText('Brute force on web-01')).not.toBeInTheDocument();
    expect(screen.getByText('CVE-2026-1234 on db-01')).toBeInTheDocument();
  });

  it('shows an empty-state when no alert matches the filters', async () => {
    api.get.mockResolvedValue({ data: ALERTS });
    const user = userEvent.setup();
    render(<LinkedAlertsPanel displayId="INC-2026-0001" linkedAlertCount={2} />);
    await waitFor(() => screen.getByText('Brute force on web-01'));

    await user.type(screen.getByPlaceholderText('Search alerts…'), 'zzz-nomatch');

    expect(screen.getByText('No alerts match the current filters.')).toBeInTheDocument();
  });

  it('keeps the header count at the total, not the filtered subset', async () => {
    api.get.mockResolvedValue({ data: ALERTS });
    const user = userEvent.setup();
    render(<LinkedAlertsPanel displayId="INC-2026-0001" linkedAlertCount={2} />);
    await waitFor(() => screen.getByText('Brute force on web-01'));

    await user.type(screen.getByPlaceholderText('Search alerts…'), 'brute');

    expect(screen.getByText('Linked Alerts (2)')).toBeInTheDocument();
  });
});
