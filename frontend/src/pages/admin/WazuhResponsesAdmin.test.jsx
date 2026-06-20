import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import WazuhResponsesAdmin from './WazuhResponsesAdmin';

function mkResponse(over = {}) {
  return {
    id: 1, name: 'Block IP', command: 'firewall-drop', platforms: ['linux'],
    default_args: '', timeout: 0, available_in_security_overview: true,
    requires_confirmation: false, autonomous_triage_approved: false,
    archived: false, created_by: null, created_at: null, updated_at: null,
    ...over,
  };
}

const RESPONSES = [
  mkResponse(),
  mkResponse({ id: 2, name: 'Isolate Host', command: 'host-deny', platforms: ['windows'], timeout: 60 }),
];

function renderPage() {
  return render(
    <MemoryRouter>
      <WazuhResponsesAdmin />
    </MemoryRouter>
  );
}

// Both mobile cards and the desktop table render in jsdom; the table is the
// deterministic surface for assertions.
function table() {
  return screen.getByRole('table');
}

describe('WazuhResponsesAdmin', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders page heading', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => screen.getByText('Wazuh Active Responses'));
  });

  it('shows empty state', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No Wazuh active responses configured.').length).toBeGreaterThan(0));
  });

  it('renders response rows', async () => {
    api.get.mockResolvedValue({ data: RESPONSES });
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    expect(within(table()).getByText('Isolate Host')).toBeInTheDocument();
    expect(within(table()).getByText('firewall-drop')).toBeInTheDocument();
  });

  it('filters by search query (name or command)', async () => {
    api.get.mockResolvedValue({ data: RESPONSES });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    await user.type(screen.getByLabelText('Search responses'), 'host-deny');
    await waitFor(() => expect(within(table()).queryByText('Block IP')).not.toBeInTheDocument());
    expect(within(table()).getByText('Isolate Host')).toBeInTheDocument();
  });

  it('filters by platform', async () => {
    api.get.mockResolvedValue({ data: RESPONSES });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    await user.selectOptions(screen.getByLabelText('Platform filter'), 'windows');
    await waitFor(() => expect(within(table()).queryByText('Block IP')).not.toBeInTheDocument());
    expect(within(table()).getByText('Isolate Host')).toBeInTheDocument();
  });

  it('filters by archived/active status (supersedes show archived)', async () => {
    api.get.mockResolvedValue({ data: [mkResponse(), mkResponse({ id: 2, name: 'Isolate Host', archived: true })] });
    const user = userEvent.setup();
    renderPage();
    // default status filter is Active → archived hidden
    await waitFor(() => within(table()).getByText('Block IP'));
    expect(within(table()).queryByText('Isolate Host')).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Status filter'), 'archived');
    await waitFor(() => expect(within(table()).queryByText('Block IP')).not.toBeInTheDocument());
    expect(within(table()).getByText('Isolate Host')).toBeInTheDocument();
  });

  it('sorts by name', async () => {
    api.get.mockResolvedValue({ data: RESPONSES });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Block IP')).toBeInTheDocument();
    await user.click(within(table()).getByRole('button', { name: 'Sort by Name' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Isolate Host')).toBeInTheDocument();
  });

  it('bulk-archives selected responses via DELETE', async () => {
    api.get.mockResolvedValue({ data: RESPONSES });
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Block IP'));
    await user.click(within(table()).getByLabelText('Select Block IP'));
    await user.click(screen.getByRole('button', { name: 'Archive selected' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/wazuh-responses/1/'));
  });
});
