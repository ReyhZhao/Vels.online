import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import AutomationsAdmin from './AutomationsAdmin';

const AUTOMATIONS = [
  { id: 1, name: 'Block IP', semaphore_template_id: 5, semaphore_template_name: 'Firewall Block', default_vars: null, incident_var_mappings: null, archived: false },
  { id: 2, name: 'Isolate Host', semaphore_template_id: 6, semaphore_template_name: 'EDR Isolate', default_vars: null, incident_var_mappings: null, archived: true },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <AutomationsAdmin />
    </MemoryRouter>
  );
}

// The component renders both a mobile card list and a desktop table in jsdom
// (no CSS media queries), so the desktop table is the deterministic surface.
function table() {
  return screen.getByRole('table');
}

describe('AutomationsAdmin', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders page heading', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => screen.getByText('Automations'));
  });

  it('shows empty state', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No automations yet.').length).toBeGreaterThan(0));
  });

  it('renders automation rows', async () => {
    api.get.mockResolvedValue({ data: AUTOMATIONS });
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    expect(within(table()).getByText('Isolate Host')).toBeInTheDocument();
    expect(within(table()).getByText('Firewall Block')).toBeInTheDocument();
    expect(within(table()).getByText('Active')).toBeInTheDocument();
    expect(within(table()).getByText('Archived')).toBeInTheDocument();
  });

  it('filters by search query (name or template)', async () => {
    api.get.mockResolvedValue({ data: AUTOMATIONS });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    await user.type(screen.getByLabelText('Search automations'), 'isolate');
    await waitFor(() => expect(within(table()).queryByText('Block IP')).not.toBeInTheDocument());
    expect(within(table()).getByText('Isolate Host')).toBeInTheDocument();
  });

  it('filters by status', async () => {
    api.get.mockResolvedValue({ data: AUTOMATIONS });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    await user.selectOptions(screen.getByLabelText('Status filter'), 'archived');
    await waitFor(() => expect(within(table()).queryByText('Block IP')).not.toBeInTheDocument());
    expect(within(table()).getByText('Isolate Host')).toBeInTheDocument();
  });

  it('sorts by name', async () => {
    api.get.mockResolvedValue({ data: AUTOMATIONS });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    // default name asc → Block IP before Isolate Host
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Block IP')).toBeInTheDocument();
    await user.click(within(table()).getByRole('button', { name: 'Sort by Name' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Isolate Host')).toBeInTheDocument();
  });

  it('bulk-archives selected automations', async () => {
    api.get.mockResolvedValue({ data: AUTOMATIONS });
    api.delete.mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    await user.click(within(table()).getByLabelText('Select Block IP'));
    await user.click(screen.getByRole('button', { name: 'Archive selected' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/automations/1/'));
  });
});
